"""Deterministic local acquisition, caching, and safe archive extraction.

Nothing is fetched unless a caller explicitly enables downloading. Every cache
entry records the URL, expected hash, observed hash, and size. Offline builds
only read from the cache or from explicitly configured local paths.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cyberlite.logging_utils import get_logger

logger = get_logger(__name__)

USER_AGENT = "CyberLite/0.1 (research; +https://github.com/braydos-h/CyberLite)"


class AcquisitionError(RuntimeError):
    """Raised when an input cannot be acquired safely."""


class CacheMissError(AcquisitionError):
    """Raised in offline mode when a required artifact is not cached."""


@dataclass
class FetchResult:
    path: Path
    sha256: str
    bytes: int
    from_cache: bool
    url: str = ""


def sha256_path(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_replace(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source, destination)


def _metadata_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".meta.json")


def _write_metadata(path: Path, payload: dict[str, Any]) -> None:
    _metadata_path(path).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _read_metadata(path: Path) -> dict[str, Any]:
    metadata_path = _metadata_path(path)
    if not metadata_path.is_file():
        return {}
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _retryable(exc: BaseException) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in {408, 425, 429, 500, 502, 503, 504}
    return isinstance(exc, (urllib.error.URLError, TimeoutError, OSError))


def _retry_delay(exc: BaseException, attempt: int, backoff: float) -> float:
    if isinstance(exc, urllib.error.HTTPError):
        retry_after = exc.headers.get("Retry-After") if exc.headers else None
        if retry_after:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                pass
    return backoff * (2**attempt)


def fetch_file(
    url: str,
    destination: str | Path,
    *,
    expected_sha256: str = "",
    force: bool = False,
    timeout: float = 60.0,
    retries: int = 4,
    backoff: float = 1.0,
    resume: bool = True,
    offline: bool = False,
    opener: Callable[..., Any] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> FetchResult:
    """Download *url* to *destination*, with retries, backoff, and resumption.

    A cached destination is reused unless ``force`` is set. When an expected
    SHA-256 is supplied it must match; a mismatch raises instead of silently
    caching corrupt input. ``offline=True`` never performs network I/O.
    """

    destination = Path(destination)
    if destination.is_file() and not force:
        observed = sha256_path(destination)
        if expected_sha256 and observed != expected_sha256:
            raise AcquisitionError(
                f"cached file {destination} does not match expected SHA-256 "
                f"{expected_sha256} (observed {observed})"
            )
        return FetchResult(
            path=destination,
            sha256=observed,
            bytes=destination.stat().st_size,
            from_cache=True,
            url=url,
        )
    if offline:
        raise CacheMissError(f"offline build requires a cached file at {destination}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.with_suffix(destination.suffix + ".part")
    open_url = opener or urllib.request.urlopen
    last_error: BaseException | None = None
    for attempt in range(retries + 1):
        try:
            if not resume and part.exists():
                part.unlink()
            headers = {"User-Agent": USER_AGENT}
            expected_start = part.stat().st_size if part.exists() and resume else 0
            if expected_start:
                headers["Range"] = f"bytes={expected_start}-"
            request = urllib.request.Request(url, headers=headers)
            logger.info("fetching", extra={"url": url, "destination": str(destination)})
            with open_url(request, timeout=timeout) as response:
                status = getattr(response, "status", 200)
                mode = "ab" if expected_start and status == 206 else "wb"
                if mode == "wb":
                    expected_start = 0
                with part.open(mode) as handle:
                    shutil.copyfileobj(response, handle, length=1024 * 1024)
            observed = sha256_path(part)
            if expected_sha256 and observed != expected_sha256:
                part.unlink(missing_ok=True)
                raise AcquisitionError(
                    f"downloaded file from {url} does not match expected SHA-256 "
                    f"{expected_sha256} (observed {observed})"
                )
            _atomic_replace(part, destination)
            size = destination.stat().st_size
            _write_metadata(
                destination,
                {
                    "url": url,
                    "sha256": observed,
                    "bytes": size,
                    "expected_sha256": expected_sha256,
                },
            )
            return FetchResult(
                path=destination,
                sha256=observed,
                bytes=size,
                from_cache=False,
                url=url,
            )
        except AcquisitionError:
            raise
        except Exception as exc:
            last_error = exc
            if not _retryable(exc) or attempt >= retries:
                break
            delay = _retry_delay(exc, attempt, backoff)
            logger.warning(
                "fetch retry",
                extra={"url": url, "attempt": attempt + 1, "delay": delay, "error": str(exc)},
            )
            sleep(delay)
    raise AcquisitionError(f"failed to fetch {url}: {last_error}") from last_error


def _safe_members_tar(archive: tarfile.TarFile, destination: Path) -> list[tarfile.TarInfo]:
    members: list[tarfile.TarInfo] = []
    root = destination.resolve()
    for member in archive.getmembers():
        target = (destination / member.name).resolve()
        if root not in target.parents and target != root:
            raise AcquisitionError(f"unsafe path in archive: {member.name}")
        if member.issym() or member.islnk():
            link = (destination / member.linkname).resolve()
            if root not in link.parents and link != root:
                raise AcquisitionError(f"unsafe link in archive: {member.name}")
        members.append(member)
    return members


def extract_archive(archive: str | Path, destination: str | Path) -> Path:
    """Extract a tar/zip archive, rejecting path traversal."""

    archive = Path(archive)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as handle:
            for member in handle.infolist():
                target = (destination / member.filename).resolve()
                if destination.resolve() not in target.parents and target != destination.resolve():
                    raise AcquisitionError(f"unsafe path in zip: {member.filename}")
            handle.extractall(destination)
        return destination
    try:
        with tarfile.open(archive, "r:*") as handle:
            handle.extractall(destination, members=_safe_members_tar(handle, destination))
    except tarfile.TarError as exc:
        raise AcquisitionError(f"unsupported or corrupt archive {archive}: {exc}") from exc
    return destination


def fetch_archive(
    url: str,
    cache_dir: str | Path,
    *,
    filename: str,
    expected_sha256: str = "",
    force: bool = False,
    offline: bool = False,
    timeout: float = 120.0,
    retries: int = 4,
    backoff: float = 1.0,
    opener: Callable[..., Any] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[Path, Path]:
    """Fetch and extract an archive into a content-addressed cache directory.

    Returns ``(archive_path, extracted_dir)``. The extraction directory name
    embeds the archive hash so a stale extraction is never reused.
    """

    cache_dir = Path(cache_dir)
    archive_path = cache_dir / "archives" / filename
    result = fetch_file(
        url,
        archive_path,
        expected_sha256=expected_sha256,
        force=force,
        offline=offline,
        timeout=timeout,
        retries=retries,
        backoff=backoff,
        opener=opener,
        sleep=sleep,
    )
    extracted = cache_dir / "extracted" / f"{archive_path.stem}-{result.sha256[:16]}"
    marker = extracted / ".cyberlite-extracted"
    if marker.is_file() and marker.read_text(encoding="utf-8").strip() == result.sha256:
        return archive_path, extracted
    if offline and not marker.is_file():
        raise CacheMissError(f"offline build requires an extracted archive at {extracted}")
    if extracted.exists():
        shutil.rmtree(extracted)
    extract_archive(archive_path, extracted)
    marker.write_text(result.sha256 + "\n", encoding="utf-8")
    return archive_path, extracted


def locate_extracted_root(path: Path) -> Path:
    """Return the single top-level directory of an extracted archive, if any."""

    entries = [entry for entry in path.iterdir() if entry.name != ".cyberlite-extracted"]
    directories = [entry for entry in entries if entry.is_dir()]
    if len(directories) == 1 and len(entries) == 1:
        return directories[0]
    return path

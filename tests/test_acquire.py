from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest
from cyberlite.data.acquire import (
    AcquisitionError,
    CacheMissError,
    fetch_archive,
    fetch_file,
)


class Response:
    def __init__(self, payload: bytes, status: int = 200, headers: dict | None = None) -> None:
        self._buffer = io.BytesIO(payload)
        self.status = status
        self.headers = headers or {}

    def read(self, size: int = -1) -> bytes:
        return self._buffer.read(size)

    def __enter__(self) -> Response:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_fetch_file_caches_and_reuses(tmp_path: Path) -> None:
    calls: list[str] = []

    def opener(request, timeout: float = 0) -> Response:
        calls.append(request.full_url)
        return Response(b"payload")

    destination = tmp_path / "file.txt"
    first = fetch_file("https://example.invalid/file.txt", destination, opener=opener)
    assert first.from_cache is False
    assert destination.read_bytes() == b"payload"
    second = fetch_file("https://example.invalid/file.txt", destination, opener=opener)
    assert second.from_cache is True
    assert len(calls) == 1


def test_fetch_file_offline_cache_miss(tmp_path: Path) -> None:
    with pytest.raises(CacheMissError, match="offline"):
        fetch_file(
            "https://example.invalid/missing.txt",
            tmp_path / "missing.txt",
            offline=True,
        )


def test_fetch_file_checksum_mismatch(tmp_path: Path) -> None:
    with pytest.raises(AcquisitionError, match="SHA-256"):
        fetch_file(
            "https://example.invalid/file.txt",
            tmp_path / "file.txt",
            expected_sha256="0" * 64,
            opener=lambda request, timeout=0: Response(b"payload"),
        )


def test_archive_extraction_and_cache(tmp_path: Path) -> None:
    archive_source = tmp_path / "source.tar.gz"
    with tarfile.open(archive_source, "w:gz") as handle:
        payload = b"# Title\n\nA defensive document with enough text.\n"
        info = tarfile.TarInfo("bundle/docs/guide.md")
        info.size = len(payload)
        handle.addfile(info, io.BytesIO(payload))

    def opener(request, timeout: float = 0) -> Response:
        return Response(archive_source.read_bytes())

    cache = tmp_path / "cache"
    archive, extracted = fetch_archive(
        "https://example.invalid/source.tar.gz",
        cache,
        filename="source.tar.gz",
        opener=opener,
    )
    assert archive.is_file()
    assert (extracted / "bundle" / "docs" / "guide.md").is_file()
    # A second call reuses the extraction marker and does not call the opener.
    archive2, extracted2 = fetch_archive(
        "https://example.invalid/source.tar.gz",
        cache,
        filename="source.tar.gz",
        opener=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network")),
    )
    assert archive2 == archive
    assert extracted2 == extracted


def test_archive_path_traversal_rejected(tmp_path: Path) -> None:
    archive_source = tmp_path / "bad.tar.gz"
    with tarfile.open(archive_source, "w:gz") as handle:
        payload = b"bad"
        info = tarfile.TarInfo("../escape.txt")
        info.size = len(payload)
        handle.addfile(info, io.BytesIO(payload))
    from cyberlite.data.acquire import extract_archive

    with pytest.raises(AcquisitionError, match="unsafe"):
        extract_archive(archive_source, tmp_path / "out")

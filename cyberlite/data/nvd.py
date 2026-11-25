"""NVD API 2.0 collection with pagination, retries, rate limits, and caching.

The collector never runs implicitly. It writes one cache file per API page plus
a resumable ``state.json`` so an interrupted build can continue without
re-downloading completed pages and an offline build can rebuild from cache.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cyberlite.logging_utils import get_logger

logger = get_logger(__name__)

NVD_API_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
USER_AGENT = "CyberLite/0.1 (research; +https://github.com/braydos-h/CyberLite)"
MAX_RANGE_DAYS = 120


class NvdError(RuntimeError):
    """Raised when NVD collection fails after retries or cache is missing."""


@dataclass
class NvdCollection:
    pages: list[Path] = field(default_factory=list)
    page_meta: list[dict[str, Any]] = field(default_factory=list)
    requests: int = 0
    cache_hits: int = 0
    records_seen: int = 0
    total_results: int = 0
    truncated: bool = False
    date_start: str = ""
    date_end: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "pages": [str(path) for path in self.pages],
            "page_meta": self.page_meta,
            "requests": self.requests,
            "cache_hits": self.cache_hits,
            "records_seen": self.records_seen,
            "total_results": self.total_results,
            "truncated": self.truncated,
            "date_start": self.date_start,
            "date_end": self.date_end,
        }


@dataclass
class NvdPage:
    start_index: int
    total_results: int
    vulnerabilities: list[dict[str, Any]]
    path: Path
    sha256: str
    from_cache: bool = False


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _normalize_date(value: str, *, end: bool = False) -> str:
    value = value.strip()
    if not value:
        raise ValueError("NVD date must not be empty")
    if len(value) == 10:
        suffix = "T23:59:59.999" if end else "T00:00:00.000"
        value = value + suffix
    elif "T" not in value:
        raise ValueError(f"unsupported NVD date format: {value!r}")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid NVD date: {value!r}") from exc
    return value


def _parse_date(value: str, *, end: bool = False) -> datetime:
    normalized = _normalize_date(value, end=end)
    parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


class NvdClient:
    """Small, testable NVD API 2.0 client.

    ``opener`` and ``sleep`` are injectable so unit tests can exercise retry,
    pagination, and rate-limit behavior without network access.
    """

    def __init__(
        self,
        cache_dir: str | Path,
        *,
        api_key: str | None = None,
        page_size: int = 2000,
        timeout: float = 60.0,
        max_retries: int = 5,
        backoff: float = 1.0,
        rate_limit_seconds: float | None = None,
        offline: bool = False,
        api_url: str = NVD_API_URL,
        opener: Callable[..., Any] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not 1 <= page_size <= 2000:
            raise ValueError("NVD page_size must be between 1 and 2000")
        self.cache_dir = Path(cache_dir)
        self.api_key = api_key if api_key is not None else os.environ.get("NVD_API_KEY", "")
        self.page_size = page_size
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff = backoff
        self.rate_limit_seconds = (
            rate_limit_seconds if rate_limit_seconds is not None else (0.7 if self.api_key else 6.0)
        )
        self.offline = offline
        self.api_url = api_url
        self.opener = opener or urllib.request.urlopen
        self.sleep = sleep
        self._last_request = 0.0
        self.requests = 0
        self.cache_hits = 0

    # -- cache paths ---------------------------------------------------
    @staticmethod
    def _slug(date_start: str, date_end: str, page_size: int) -> str:
        raw = f"{date_start}|{date_end}|{page_size}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def _range_dir(self, date_start: str, date_end: str) -> Path:
        return self.cache_dir / "nvd" / self._slug(date_start, date_end, self.page_size)

    # -- HTTP ----------------------------------------------------------
    def _build_url(self, date_start: str, date_end: str, start_index: int) -> str:
        params = {
            "pubStartDate": date_start,
            "pubEndDate": date_end,
            "resultsPerPage": str(self.page_size),
            "startIndex": str(start_index),
        }
        return f"{self.api_url}?{urllib.parse.urlencode(params)}"

    def _throttle(self) -> None:
        if self.rate_limit_seconds <= 0:
            return
        elapsed = time.monotonic() - self._last_request
        if self._last_request and elapsed < self.rate_limit_seconds:
            self.sleep(self.rate_limit_seconds - elapsed)
        self._last_request = time.monotonic()

    @staticmethod
    def _retry_delay(exc: BaseException, attempt: int, backoff: float) -> float:
        if isinstance(exc, urllib.error.HTTPError) and exc.headers:
            retry_after = exc.headers.get("Retry-After")
            if retry_after:
                try:
                    return max(0.0, float(retry_after))
                except ValueError:
                    pass
        return backoff * (2**attempt)

    @staticmethod
    def _retryable(exc: BaseException) -> bool:
        if isinstance(exc, urllib.error.HTTPError):
            return exc.code in {403, 408, 425, 429, 500, 502, 503, 504}
        return isinstance(exc, (urllib.error.URLError, TimeoutError, OSError, ValueError))

    def _request_page(self, date_start: str, date_end: str, start_index: int) -> bytes:
        if self.offline:
            raise NvdError("offline mode: NVD page is not cached")
        url = self._build_url(date_start, date_end, start_index)
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if self.api_key:
            headers["apiKey"] = self.api_key
        last_error: BaseException | None = None
        for attempt in range(self.max_retries + 1):
            self._throttle()
            request = urllib.request.Request(url, headers=headers)
            try:
                self.requests += 1
                with self.opener(request, timeout=self.timeout) as response:
                    payload = response.read()
                if not payload:
                    raise NvdError("NVD returned an empty response")
                parsed = json.loads(payload)
                if not isinstance(parsed, dict):
                    raise NvdError("NVD response is not a JSON object")
                if not isinstance(parsed.get("vulnerabilities"), list):
                    raise NvdError("NVD response is missing a vulnerabilities list")
                return payload
            except NvdError:
                raise
            except Exception as exc:
                last_error = exc
                if not self._retryable(exc) or attempt >= self.max_retries:
                    break
                delay = self._retry_delay(exc, attempt, self.backoff)
                logger.warning(
                    "NVD request retry",
                    extra={"attempt": attempt + 1, "delay": delay, "error": str(exc)},
                )
                self.sleep(delay)
                # A rate-limit response is a weak signal that the configured
                # interval is too aggressive; increase it for later calls.
                if isinstance(exc, urllib.error.HTTPError) and exc.code in {403, 429}:
                    self.rate_limit_seconds = max(self.rate_limit_seconds, 6.0)
        raise NvdError(f"NVD request failed after retries: {last_error}") from last_error

    def _cached_collection(
        self, state: dict[str, Any], start: str, end: str
    ) -> NvdCollection | None:
        """Rebuild a collection from recorded page metadata and cached files."""

        pages_meta = state.get("pages", [])
        if not isinstance(pages_meta, list) or not pages_meta:
            return None
        collection = NvdCollection(date_start=start, date_end=end)
        cache_hits = 0
        for meta in pages_meta:
            if not isinstance(meta, dict):
                continue
            path = Path(str(meta.get("path", "")))
            if not path.is_file():
                return None
            payload = path.read_bytes()
            parsed = self._validate_payload(payload)
            start_index = int(meta.get("start_index", 0))
            collection.pages.append(path)
            collection.page_meta.append(
                {
                    "path": str(path),
                    "sha256": _sha256_bytes(payload),
                    "start_index": start_index,
                    "total_results": int(parsed.get("totalResults", 0)),
                    "items": len(parsed["vulnerabilities"]),
                    "from_cache": True,
                    "url": self._build_url(start, end, start_index),
                }
            )
            collection.records_seen += len(parsed["vulnerabilities"])
            collection.total_results = max(
                collection.total_results, int(parsed.get("totalResults", 0))
            )
            cache_hits += 1
        self.cache_hits += cache_hits
        collection.cache_hits = cache_hits
        collection.truncated = bool(state.get("truncated", False))
        return collection

    # -- collection ----------------------------------------------------
    def collect(
        self,
        date_start: str,
        date_end: str,
        *,
        max_records: int | None = None,
        force: bool = False,
    ) -> NvdCollection:
        """Collect one publication-date range (at most 120 days)."""

        start = _normalize_date(date_start)
        end = _normalize_date(date_end, end=True)
        if _parse_date(start) > _parse_date(end):
            raise ValueError("NVD date_start must be before date_end")
        if (_parse_date(end) - _parse_date(start)).days > MAX_RANGE_DAYS:
            raise ValueError(
                f"NVD publication ranges must be <= {MAX_RANGE_DAYS} days; "
                "use collect_range() to chunk a longer interval"
            )
        if max_records is not None and max_records < 0:
            raise ValueError("max_records must be non-negative")

        range_dir = self._range_dir(start, end)
        range_dir.mkdir(parents=True, exist_ok=True)
        state_path = range_dir / "state.json"
        state = self._load_state(state_path)
        if force:
            state = {}
        collection = NvdCollection(date_start=start, date_end=end)
        if state and (self.offline or state.get("complete") or state.get("truncated")):
            cached_collection = self._cached_collection(state, start, end)
            if cached_collection is not None:
                return cached_collection
        start_index = int(state.get("next_index", 0)) if not force else 0
        total = int(state.get("total_results", 0))
        truncated = False
        seen = 0

        while True:
            page_path = range_dir / f"page-{start_index:06d}.json"
            page: NvdPage | None = None
            if page_path.is_file() and not force:
                payload = page_path.read_bytes()
                parsed = self._validate_payload(payload)
                page = NvdPage(
                    start_index=start_index,
                    total_results=int(parsed.get("totalResults", 0)),
                    vulnerabilities=parsed["vulnerabilities"],
                    path=page_path,
                    sha256=_sha256_bytes(payload),
                    from_cache=True,
                )
                self.cache_hits += 1
            else:
                payload = self._request_page(start, end, start_index)
                parsed = self._validate_payload(payload)
                page_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = page_path.with_suffix(".json.tmp")
                temporary.write_bytes(payload)
                os.replace(temporary, page_path)
                page = NvdPage(
                    start_index=start_index,
                    total_results=int(parsed.get("totalResults", 0)),
                    vulnerabilities=parsed["vulnerabilities"],
                    path=page_path,
                    sha256=_sha256_bytes(payload),
                )
                page_meta = {
                    "path": str(page_path),
                    "sha256": page.sha256,
                    "start_index": start_index,
                    "results_per_page": self.page_size,
                    "total_results": page.total_results,
                    "items": len(page.vulnerabilities),
                    "url": self._build_url(start, end, start_index),
                }
                state.setdefault("pages", []).append(page_meta)
                state_path.write_text(
                    json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                )

            total = page.total_results
            collection.pages.append(page.path)
            collection.page_meta.append(
                {
                    "path": str(page.path),
                    "sha256": page.sha256,
                    "start_index": page.start_index,
                    "total_results": page.total_results,
                    "items": len(page.vulnerabilities),
                    "from_cache": page.from_cache,
                    "url": self._build_url(start, end, page.start_index),
                }
            )
            seen += len(page.vulnerabilities)
            if max_records is not None and seen >= max_records:
                truncated = (
                    seen > (max_records or 0) or start_index + len(page.vulnerabilities) < total
                )
                break
            start_index += self.page_size
            if not page.vulnerabilities or start_index >= total:
                break

        state = {
            "date_start": start,
            "date_end": end,
            "page_size": self.page_size,
            "total_results": total,
            "next_index": start_index,
            "records_seen": seen,
            "complete": start_index >= total and not truncated,
            "truncated": truncated,
            "pages": state.get("pages", []),
        }
        state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        collection.records_seen = seen
        collection.total_results = total
        collection.truncated = truncated
        collection.requests = self.requests
        collection.cache_hits = self.cache_hits
        logger.info(
            "NVD range collected",
            extra={
                "start": start,
                "end": end,
                "pages": len(collection.pages),
                "records": seen,
                "total": total,
            },
        )
        return collection

    def collect_range(
        self,
        date_start: str,
        date_end: str,
        *,
        max_records: int | None = None,
        force: bool = False,
    ) -> NvdCollection:
        """Collect a range longer than 120 days by chunking publication dates."""

        cursor = _parse_date(date_start)
        end = _parse_date(date_end, end=True)
        if cursor > end:
            raise ValueError("NVD date_start must be before date_end")
        combined = NvdCollection(
            date_start=_normalize_date(date_start), date_end=_normalize_date(date_end, end=True)
        )
        remaining = max_records
        while cursor <= end:
            chunk_end = min(cursor + timedelta(days=MAX_RANGE_DAYS - 1), end)
            # Preserve the caller's end-of-day semantics for partial chunks.
            chunk_end_arg = (
                chunk_end.date().isoformat() if chunk_end < end else chunk_end.isoformat()
            )
            chunk = self.collect(
                cursor.isoformat(),
                chunk_end_arg,
                max_records=remaining,
                force=force,
            )
            combined.pages.extend(chunk.pages)
            combined.page_meta.extend(chunk.page_meta)
            combined.requests += chunk.requests
            combined.cache_hits += chunk.cache_hits
            combined.records_seen += chunk.records_seen
            combined.total_results += chunk.total_results
            combined.truncated = combined.truncated or chunk.truncated
            if remaining is not None:
                remaining -= chunk.records_seen
                if remaining <= 0:
                    combined.truncated = True
                    break
            cursor = chunk_end + timedelta(days=1)
        return combined

    @staticmethod
    def _validate_payload(payload: bytes) -> dict[str, Any]:
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise NvdError(f"cached NVD page is not valid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise NvdError("NVD page must be a JSON object")
        if not isinstance(parsed.get("vulnerabilities"), list):
            raise NvdError("NVD page is missing a vulnerabilities list")
        try:
            int(parsed.get("totalResults", 0))
        except (TypeError, ValueError) as exc:
            raise NvdError("NVD page has an invalid totalResults") from exc
        return parsed

    @staticmethod
    def _load_state(path: Path) -> dict[str, Any]:
        if not path.is_file():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

from __future__ import annotations

import json
import urllib.error
import urllib.parse
from pathlib import Path

import pytest
from cyberlite.data.nvd import NvdClient, NvdError


class FakeResponse:
    def __init__(self, payload: bytes, status: int = 200, headers: dict | None = None) -> None:
        self.payload = payload
        self.status = status
        self.headers = headers or {}

    def read(self) -> bytes:
        return self.payload

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


class FakeOpener:
    def __init__(self, pages: list[dict], *, failures: list[BaseException] | None = None) -> None:
        self.pages = pages
        self.failures = list(failures or [])
        self.urls: list[str] = []
        self.headers: list[dict[str, str]] = []

    def __call__(self, request, timeout: float = 0) -> FakeResponse:
        self.urls.append(request.full_url)
        self.headers.append(dict(request.header_items()))
        if self.failures:
            raise self.failures.pop(0)
        query = urllib.parse.parse_qs(urllib.parse.urlparse(request.full_url).query)
        start = int(query["startIndex"][0])
        page_size = int(query["resultsPerPage"][0])
        page = self.pages[start // page_size]
        return FakeResponse(json.dumps(page).encode())


def _page(start: int, total: int, items: list[str]) -> dict:
    return {
        "resultsPerPage": len(items),
        "startIndex": start,
        "totalResults": total,
        "vulnerabilities": [{"cve": {"id": item}} for item in items],
    }


def test_nvd_pagination_and_cache(tmp_path: Path) -> None:
    opener = FakeOpener([_page(0, 5, ["a", "b"]), _page(2, 5, ["c", "d"]), _page(4, 5, ["e"])])
    client = NvdClient(
        tmp_path, page_size=2, opener=opener, sleep=lambda _: None, rate_limit_seconds=0
    )
    collection = client.collect("2024-01-01", "2024-01-02")
    assert collection.records_seen == 5
    assert len(collection.pages) == 3
    assert len(opener.urls) == 3

    cached_client = NvdClient(
        tmp_path, page_size=2, opener=opener, sleep=lambda _: None, rate_limit_seconds=0
    )
    cached = cached_client.collect("2024-01-01", "2024-01-02")
    assert cached.records_seen == 5
    assert cached.cache_hits == 3
    assert len(opener.urls) == 3  # no new requests


def test_nvd_retries_with_backoff(tmp_path: Path) -> None:
    error = urllib.error.HTTPError(
        "https://example.invalid", 503, "busy", {"Retry-After": "0.25"}, None
    )
    opener = FakeOpener([_page(0, 1, ["a"])], failures=[error])
    delays: list[float] = []
    client = NvdClient(
        tmp_path,
        page_size=1,
        opener=opener,
        sleep=delays.append,
        max_retries=2,
        backoff=0.1,
        rate_limit_seconds=0,
    )
    collection = client.collect("2024-01-01", "2024-01-01")
    assert collection.records_seen == 1
    assert delays == [0.25]
    assert len(opener.urls) == 2


def test_nvd_rate_limit_is_increased_after_429(tmp_path: Path) -> None:
    error = urllib.error.HTTPError("https://example.invalid", 429, "slow down", {}, None)
    opener = FakeOpener([_page(0, 1, ["a"])], failures=[error])
    client = NvdClient(
        tmp_path,
        page_size=1,
        opener=opener,
        sleep=lambda _: None,
        max_retries=1,
        rate_limit_seconds=0.1,
    )
    client.collect("2024-01-01", "2024-01-01")
    assert client.rate_limit_seconds >= 6.0


def test_nvd_api_key_header(tmp_path: Path) -> None:
    opener = FakeOpener([_page(0, 1, ["a"])])
    client = NvdClient(
        tmp_path,
        page_size=1,
        api_key="test-key",
        opener=opener,
        sleep=lambda _: None,
        rate_limit_seconds=0,
    )
    client.collect("2024-01-01", "2024-01-01")
    assert any(
        key.lower() == "apikey" and value == "test-key" for key, value in opener.headers[0].items()
    )


def test_nvd_offline_uses_cache_and_misses_clearly(tmp_path: Path) -> None:
    opener = FakeOpener([_page(0, 1, ["a"])])
    NvdClient(
        tmp_path, page_size=1, opener=opener, sleep=lambda _: None, rate_limit_seconds=0
    ).collect("2024-01-01", "2024-01-01")
    offline = NvdClient(tmp_path, page_size=1, offline=True, opener=opener, sleep=lambda _: None)
    assert offline.collect("2024-01-01", "2024-01-01").records_seen == 1
    missing = NvdClient(tmp_path / "empty", page_size=1, offline=True, opener=opener)
    with pytest.raises(NvdError, match="offline"):
        missing.collect("2024-01-01", "2024-01-01")


def test_nvd_malformed_page_rejected(tmp_path: Path) -> None:
    class BadOpener:
        def __call__(self, request, timeout: float = 0) -> FakeResponse:
            return FakeResponse(b'{"totalResults": "not-a-number", "vulnerabilities": []}')

    client = NvdClient(
        tmp_path, page_size=1, opener=BadOpener(), sleep=lambda _: None, rate_limit_seconds=0
    )
    with pytest.raises(NvdError, match="totalResults"):
        client.collect("2024-01-01", "2024-01-01")


def test_nvd_max_records_truncates(tmp_path: Path) -> None:
    opener = FakeOpener([_page(0, 5, ["a", "b"])])
    client = NvdClient(
        tmp_path, page_size=2, opener=opener, sleep=lambda _: None, rate_limit_seconds=0
    )
    collection = client.collect("2024-01-01", "2024-01-02", max_records=2)
    assert collection.records_seen == 2
    assert collection.truncated is True
    assert len(opener.urls) == 1


def test_nvd_date_range_limit(tmp_path: Path) -> None:
    client = NvdClient(tmp_path, page_size=1, sleep=lambda _: None)
    with pytest.raises(ValueError, match="<= 120 days"):
        client.collect("2024-01-01", "2024-12-31")


def test_nvd_collect_range_chunks(tmp_path: Path) -> None:
    pages = [_page(0, 1, ["a"])]
    opener = FakeOpener(pages)
    client = NvdClient(
        tmp_path, page_size=1, opener=opener, sleep=lambda _: None, rate_limit_seconds=0
    )
    collection = client.collect_range("2024-01-01", "2024-10-01")
    assert collection.records_seen == 3
    assert len(opener.urls) == 3

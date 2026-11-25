from __future__ import annotations

from cyberlite.evaluation.benchmarks import (
    BENCHMARKS,
    check_local_benchmark,
    get_benchmark,
    list_benchmarks,
)


def test_benchmark_registry_has_licenses() -> None:
    assert {"cyberseceval", "seceval", "heldout"} <= set(BENCHMARKS)
    for spec in BENCHMARKS.values():
        assert spec.license
        assert spec.redistribution
        assert spec.access


def test_list_benchmarks_serializable() -> None:
    payload = list_benchmarks()
    assert isinstance(payload, list)
    assert all("license" in item for item in payload)


def test_unknown_benchmark() -> None:
    import pytest

    with pytest.raises(KeyError):
        get_benchmark("nope")


def test_local_benchmark_check(tmp_path) -> None:
    path = tmp_path / "missing.jsonl"
    result = check_local_benchmark("heldout", str(path))
    assert result["exists"] is False
    assert "does not download" in result["note"]

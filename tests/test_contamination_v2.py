from __future__ import annotations

import json
from pathlib import Path

import pytest
from cyberlite.data.contamination import (
    ContaminationIndexError,
    build_benchmark_index,
    check_contamination_v2,
    cross_split_leakage,
)
from cyberlite.data.schema import Record, write_jsonl


def _eval_file(path: Path, shared: str, *, benchmark: str, version: str) -> Path:
    path.write_text(
        json.dumps({"question": "q", "choices": [shared], "answer": "A"}) + "\n",
        encoding="utf-8",
    )
    path.with_suffix(".meta.json").write_text(
        json.dumps(
            {
                "benchmark": benchmark,
                "version": version,
                "license": "Evaluation-Only",
                "upstream_revision": version,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_per_benchmark_statistics(tmp_path: Path) -> None:
    first = " ".join(["credential", "exposure", "rotation"] * 30)
    second = " ".join(["firewall", "segmentation", "policy"] * 30)
    one = _eval_file(tmp_path / "one.jsonl", first, benchmark="bench-one", version="v1")
    two = _eval_file(tmp_path / "two.jsonl", second, benchmark="bench-two", version="v2")
    index = build_benchmark_index([one, two], n=13)
    record = Record(id="r", source="train", license="Synthetic", prompt="q", response=first)
    kept, findings, report = check_contamination_v2([record], index, threshold=0.2)
    assert not kept
    assert len(findings) == 1
    assert findings[0].benchmark == "bench-one"
    assert {item["name"] for item in report["sets"]} == {"bench-one", "bench-two"}
    assert report["total_indexed_ngrams"] > 0
    assert all(item["populated"] for item in report["sets"])


def test_empty_evaluation_index_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")
    with pytest.raises(ContaminationIndexError, match="empty"):
        build_benchmark_index([path])


def test_group_quarantine_removes_whole_document(tmp_path: Path) -> None:
    shared = " ".join(["credential", "exposure", "rotation"] * 30)
    eval_path = _eval_file(tmp_path / "bench.jsonl", shared, benchmark="b", version="v1")
    index = build_benchmark_index([eval_path])
    records = [
        Record(
            id="a",
            source="docs",
            license="Synthetic",
            prompt="q",
            response=shared,
            metadata={"group": "doc-1"},
        ),
        Record(
            id="b",
            source="docs",
            license="Synthetic",
            prompt="q",
            response="A different section about logging and monitoring. " * 5,
            metadata={"group": "doc-1"},
        ),
        Record(
            id="c",
            source="docs",
            license="Synthetic",
            prompt="q",
            response="An unrelated section about firewall policy. " * 5,
            metadata={"group": "doc-2"},
        ),
    ]
    kept, _findings, report = check_contamination_v2(records, index, group_quarantine=True)
    assert [record.id for record in kept] == ["c"]
    assert report["group_removed_ids"] == ["b"]


def test_cross_split_exact_and_near_leakage() -> None:
    text = "A stable sentence about authentication logging and verification. " * 6
    splits = {
        "train": [Record(id="t", source="s", license="Synthetic", prompt="q", response=text)],
        "validation": [],
        "test": [Record(id="e", source="s", license="Synthetic", prompt="q", response=text)],
    }
    findings = cross_split_leakage(splits, threshold=3)
    assert any(item.kind == "exact" for item in findings)
    assert not cross_split_leakage(splits, threshold=0) or all(
        item.kind == "exact" for item in cross_split_leakage(splits, threshold=0)
    )


def test_screening_does_not_mutate_unrelated_records(tmp_path: Path) -> None:
    eval_path = _eval_file(
        tmp_path / "bench.jsonl",
        " ".join(["unrelated", "benchmark", "text"] * 30),
        benchmark="b",
        version="v1",
    )
    index = build_benchmark_index([eval_path])
    record = Record(
        id="r",
        source="docs",
        license="Synthetic",
        prompt="q",
        response=" ".join(["firewall", "segmentation", "policy"] * 30),
    )
    kept, findings, _ = check_contamination_v2([record], index)
    assert kept == [record]
    assert findings == []
    write_jsonl([record], tmp_path / "roundtrip.jsonl")

from __future__ import annotations

import json
from pathlib import Path

from cyberlite.data.audit import audit_dataset
from cyberlite.data.prepare import PrepareOptions, prepare_records, write_prepared_dataset
from cyberlite.data.schema import Record


def _make_dataset(tmp_path: Path) -> tuple[Path, Path]:
    records = [
        Record(
            id=f"r{index}",
            source="unit",
            license="Synthetic",
            task="knowledge" if index % 2 else "detection",
            prompt=f"How should a defender verify control {index}?",
            response=(
                f"Verify control {index} by checking the configuration, testing the "
                "expected behavior, and recording the evidence. "
            )
            * 6,
            url="https://example.invalid/source",
            metadata={"source_version": "v1", "upstream_id": f"u{index}"},
        )
        for index in range(20)
    ]
    dataset_dir = tmp_path / "dataset"
    options = PrepareOptions(
        out_dir=dataset_dir,
        force=True,
        dedup_threshold=0,
        tokenizer="",
        dataset_name="audit-test",
    )
    dataset = prepare_records(records, options)
    write_prepared_dataset(dataset, options)
    eval_dir = tmp_path / "evaluation"
    eval_dir.mkdir()
    (eval_dir / "heldout.jsonl").write_text(
        json.dumps(
            {
                "id": "eval",
                "question": "q",
                "choices": [" ".join(["heldout", "evaluation", "item"] * 10)],
                "answer": "A",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return dataset_dir, eval_dir


def test_audit_reports_and_review_template(tmp_path: Path) -> None:
    dataset_dir, eval_dir = _make_dataset(tmp_path)
    result = audit_dataset(
        dataset_dir,
        out_dir=tmp_path / "audit",
        review_out=tmp_path / "review.jsonl",
        review_size=10,
        eval_dir=eval_dir,
        registry_path=tmp_path / "missing-sources.yaml",
    )
    report = result.report
    assert report["counts"]["accepted_records"] == 20
    assert report["counts"]["rejected_records"] == 0
    assert report["contamination"]["verified"] is True
    assert report["contamination"]["verified_removed"] == 0
    assert report["duplicate_analysis"]["exact_duplicates"] == 0
    assert report["manual_review"]["completed"] is False
    assert len(result.review_samples) == 10
    assert (tmp_path / "audit" / "audit.json").is_file()
    assert (tmp_path / "audit" / "audit.md").is_file()
    assert (tmp_path / "audit" / "quality_report.json").is_file()
    assert (tmp_path / "audit" / "contamination_report.json").is_file()
    assert (tmp_path / "audit" / "license_report.json").is_file()
    assert (tmp_path / "audit" / "review_template.md").is_file()
    assert (tmp_path / "audit" / "review_plan.json").is_file()
    assert (tmp_path / "review.jsonl").is_file()
    sample = json.loads((tmp_path / "review.jsonl").read_text().splitlines()[0])
    assert set(sample["review"]) >= {
        "accuracy",
        "relevance",
        "completeness",
        "provenance",
        "safety",
        "overall_quality",
    }
    assert sample["review"]["review_status"] == "pending"


def test_review_sampling_is_deterministic(tmp_path: Path) -> None:
    dataset_dir, eval_dir = _make_dataset(tmp_path)
    first = audit_dataset(
        dataset_dir,
        out_dir=tmp_path / "a",
        review_out=tmp_path / "a.jsonl",
        review_size=7,
        seed=9,
        eval_dir=eval_dir,
    )
    second = audit_dataset(
        dataset_dir,
        out_dir=tmp_path / "b",
        review_out=tmp_path / "b.jsonl",
        review_size=7,
        seed=9,
        eval_dir=eval_dir,
    )
    assert first.review_plan["sample_ids"] == second.review_plan["sample_ids"]
    assert [item["id"] for item in first.review_samples] == [
        item["id"] for item in second.review_samples
    ]


def test_audit_detects_manifest_hash_mismatch(tmp_path: Path) -> None:
    dataset_dir, eval_dir = _make_dataset(tmp_path)
    payload = {
        "id": "changed",
        "source": "unit",
        "license": "Synthetic",
        "prompt": "q",
        "response": "changed content " * 20,
    }
    (dataset_dir / "train.jsonl").write_text(json.dumps(payload) + "\n", encoding="utf-8")
    result = audit_dataset(
        dataset_dir,
        out_dir=tmp_path / "audit",
        review_out=tmp_path / "review.jsonl",
        review_size=1,
        eval_dir=eval_dir,
    )
    assert "train.jsonl" in result.report["manifest_file_hash_mismatches"]

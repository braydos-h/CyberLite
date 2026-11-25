from __future__ import annotations

import json
from pathlib import Path

from cyberlite.data.integrity import verify_dataset


def _verify(built: dict, **overrides):
    paths = built["paths"]
    kwargs = {
        "train_file": paths["train"],
        "validation_file": paths["validation"],
        "test_file": paths["test"],
        "manifest_file": built["manifest"],
        "expected_version": built["version"],
        "expected_split_counts": dict(built["manifest_data"]["split_counts"]),
        "profile": "research",
        "require_manifest": True,
        "require_provenance": True,
        "require_contamination_screen": False,
        "eval_dir": None,
        "base_dir": built["root"].parent,
    }
    kwargs.update(overrides)
    return verify_dataset(**kwargs)


def test_valid_frozen_manifest_passes(dataset_builder) -> None:
    built = dataset_builder()
    report = _verify(built)
    assert report.ok, report.to_dict()
    assert report.dataset_version == built["version"]
    assert report.split_counts == {"train": 1, "validation": 1, "test": 1}
    assert report.files["train"]["sha256"] == built["manifest_data"]["files"]["train"]["sha256"]
    assert report.duplicate_ids == []
    assert report.cross_split_leakage == []


def test_missing_dataset_file_is_detected(dataset_builder, tmp_path: Path) -> None:
    built = dataset_builder()
    Path(built["paths"]["train"]).unlink()
    report = _verify(built)
    assert not report.ok
    assert any(issue.check == "dataset_file_missing" for issue in report.errors)


def test_modified_dataset_hash_is_detected(dataset_builder) -> None:
    built = dataset_builder()
    path = Path(built["paths"]["train"])
    path.write_text(path.read_text() + '{"id": "injected"}\n', encoding="utf-8")
    report = _verify(built)
    assert not report.ok
    checks = {issue.check for issue in report.errors}
    assert "dataset_hash_mismatch" in checks
    assert "schema_invalid" in checks


def test_missing_manifest_is_detected(dataset_builder) -> None:
    built = dataset_builder()
    Path(built["manifest"]).unlink()
    report = _verify(built, manifest_file=None)
    assert not report.ok
    assert any(issue.check == "manifest_missing" for issue in report.errors)


def test_version_and_split_count_mismatch_are_detected(dataset_builder) -> None:
    built = dataset_builder()
    report = _verify(built, expected_version="cyberlite-data-other-000000000000")
    assert not report.ok
    assert any(issue.check == "dataset_version_mismatch" for issue in report.errors)

    report = _verify(
        built,
        expected_split_counts={"train": 999, "validation": 1, "test": 1},
    )
    assert not report.ok
    assert any(issue.check == "manifest_split_count_mismatch" for issue in report.errors)


def test_duplicate_ids_and_cross_split_leakage_are_detected(dataset_builder) -> None:
    records = {
        "train": [
            {
                "id": "duplicate",
                "source": "unit",
                "license": "Public-Domain",
                "task": "knowledge",
                "prompt": "shared prompt",
                "response": "shared response text used in both splits",
            }
        ],
        "validation": [
            {
                "id": "duplicate",
                "source": "unit",
                "license": "Public-Domain",
                "task": "knowledge",
                "prompt": "shared prompt",
                "response": "shared response text used in both splits",
            }
        ],
        "test": [],
    }
    built = dataset_builder(splits=records, name="leaky")
    report = _verify(built)
    assert not report.ok
    checks = {issue.check for issue in report.errors}
    assert "duplicate_record_id" in checks
    assert "cross_split_leakage" in checks
    assert report.duplicate_ids
    assert report.cross_split_leakage


def test_missing_provenance_is_rejected_for_research(dataset_builder) -> None:
    built = dataset_builder(provenance=False)
    report = _verify(built)
    assert not report.ok
    assert any(issue.check == "provenance_missing" for issue in report.errors)


def test_smoke_profile_uses_its_own_relaxed_path(dataset_builder) -> None:
    built = dataset_builder(name="smoke", license_id="Synthetic", provenance=False, version=None)
    report = _verify(
        built,
        profile="smoke",
        expected_version=None,
        expected_split_counts={},
        require_provenance=False,
        require_contamination_screen=False,
    )
    assert report.ok, report.to_dict()
    assert report.profile == "smoke"


def test_processed_manifest_mismatch_is_detected(dataset_builder) -> None:
    built = dataset_builder(name="processed-mismatch", manifest_dir="manifests")
    processed = built["root"] / "manifest.json"
    payload = json.loads(processed.read_text())
    payload["dataset_version"] = "cyberlite-data-stale-000000000000"
    processed.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    report = _verify(built)
    assert not report.ok
    assert any(issue.check == "processed_manifest_mismatch" for issue in report.errors)


def test_evaluation_only_metadata_is_rejected(dataset_builder) -> None:
    records = {
        "train": [
            {
                "id": "eval-only",
                "source": "unit",
                "license": "Public-Domain",
                "task": "knowledge",
                "prompt": "q",
                "response": "r",
                "metadata": {
                    "source_version": "v1",
                    "upstream_id": "u1",
                    "evaluation_only": True,
                },
            }
        ],
        "validation": [],
        "test": [],
    }
    built = dataset_builder(splits=records, name="eval-only")
    report = _verify(built)
    assert not report.ok
    assert any(issue.check == "evaluation_only_record" for issue in report.errors)


def test_benchmark_contamination_screen_detects_overlap(dataset_builder, tmp_path: Path) -> None:
    text = " ".join(f"distinct-token-{index}" for index in range(40))
    records = {
        "train": [
            {
                "id": "overlap",
                "source": "unit",
                "license": "Public-Domain",
                "task": "knowledge",
                "prompt": "Explain the following benchmark item.",
                "response": text,
            }
        ],
        "validation": [],
        "test": [],
    }
    built = dataset_builder(splits=records, name="contaminated")
    eval_dir = tmp_path / "evaluation"
    eval_dir.mkdir()
    (eval_dir / "bench.jsonl").write_text(
        json.dumps({"id": "bench-1", "question": text, "answer": "A"}) + "\n",
        encoding="utf-8",
    )
    report = _verify(
        built,
        require_contamination_screen=True,
        eval_dir=eval_dir,
    )
    assert not report.ok
    assert any(issue.check == "benchmark_contamination" for issue in report.errors)
    assert report.evaluation_contamination["checked"] is True
    assert report.evaluation_contamination["finding_count"] >= 1


def test_missing_evaluation_files_fail_closed(dataset_builder, tmp_path: Path) -> None:
    built = dataset_builder(name="no-eval")
    empty = tmp_path / "empty-eval"
    empty.mkdir()
    report = _verify(
        built,
        require_contamination_screen=True,
        eval_dir=empty,
    )
    assert not report.ok
    assert any(issue.check == "evaluation_files_missing" for issue in report.errors)

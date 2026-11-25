from __future__ import annotations

from pathlib import Path

import pytest
from cyberlite.data.prepare import (
    PrepareOptions,
    prepare_records,
    run_prepare,
    write_prepared_dataset,
)
from cyberlite.data.schema import Record, load_records
from cyberlite.data.splits import SplitRatios


def _record(
    prompt: str, response: str, *, license: str = "Synthetic", source: str = "unit"
) -> Record:
    return Record(id="", source=source, license=license, prompt=prompt, response=response)


def test_prepare_rejects_license_and_secrets(tmp_path: Path) -> None:
    records = [
        _record("q1", "A" * 200),
        _record("q2", "B" * 200, license="Proprietary"),
        _record("q3", "Use AKIAIOSFODNN7EXAMPLE for access " + "C" * 200),
    ]
    options = PrepareOptions(out_dir=tmp_path, smoke=True)
    dataset = prepare_records(records, options)
    assert dataset.manifest["output_records"] >= 2
    assert dataset.manifest["cleaning"]["redacted_secrets"] == 1
    assert any(item["reason"] == "license_not_allowed" for item in dataset.rejected)
    assert dataset.manifest["license_counts"].get("Proprietary") is None


def test_prepare_deduplicates(tmp_path: Path) -> None:
    text = "The same defensive guidance repeated in full. " * 12
    records = [_record("q", text), _record("q", text)]
    dataset = prepare_records(records, PrepareOptions(out_dir=tmp_path, smoke=True))
    assert dataset.manifest["output_records"] == 1
    assert dataset.manifest["cleaning"]["dedup"]["exact_duplicates"] == 1


def test_prepare_removes_contamination(tmp_path: Path) -> None:
    shared = (
        "Which command lists listening TCP sockets with owning processes on a Linux host? "
        "Use ss with the lntup flags and verify the binary path. " * 4
    )
    train = _record("q", shared)
    eval_record = _record("q", shared)
    eval_file = tmp_path / "eval.jsonl"
    from cyberlite.data.schema import write_jsonl

    write_jsonl([eval_record], eval_file)
    dataset = prepare_records(
        [train],
        PrepareOptions(out_dir=tmp_path, smoke=True),
        eval_files=[str(eval_file)],
    )
    assert dataset.manifest["output_records"] == 0
    assert dataset.manifest["contamination"]["removed"] == 1


def test_write_manifest_hashes(tmp_path: Path) -> None:
    records = [_record(f"q{i}", f"answer {i} " * 30) for i in range(200)]
    options = PrepareOptions(
        out_dir=tmp_path / "processed",
        smoke=False,
        ratios=SplitRatios(0.8, 0.1, 0.1),
        dedup_threshold=0,
    )
    dataset = prepare_records(records, options)
    manifest = write_prepared_dataset(dataset, options)
    assert manifest["dataset_version"].startswith("cyberlite-data-2.0.0-")
    for split in ("train", "validation", "test"):
        assert manifest["files"][split]["sha256"]
        assert load_records(tmp_path / "processed" / f"{split}.jsonl")
    assert (tmp_path / "processed" / "manifest.json").is_file()
    assert manifest["files"]["quarantine"]["records"] == 0


def test_write_refuses_overwrite(tmp_path: Path) -> None:
    options = PrepareOptions(out_dir=tmp_path, smoke=True)
    dataset = prepare_records([_record("q", "answer " * 40)], options)
    write_prepared_dataset(dataset, options)
    with pytest.raises(FileExistsError):
        write_prepared_dataset(dataset, options)


def test_run_prepare_smoke(repo_root: Path, tmp_path: Path) -> None:
    manifest = run_prepare(
        registry_path=repo_root / "data" / "sources.yaml",
        raw_dir=repo_root / "data" / "raw",
        eval_dir=repo_root / "data" / "evaluation",
        options=PrepareOptions(out_dir=tmp_path / "smoke", smoke=True, force=True),
        smoke_file=repo_root / "data" / "seed" / "smoke.jsonl",
    )
    assert manifest["split_counts"]["train"] > manifest["split_counts"]["test"]
    assert manifest["source_registry_sha256"]
    assert manifest["license_counts"] == {"Synthetic": 34}
    assert manifest["contamination"]["removed"] == 0


def test_run_prepare_without_inputs_fails_clearly(repo_root: Path, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="no local raw inputs"):
        run_prepare(
            registry_path=repo_root / "data" / "sources.yaml",
            raw_dir=tmp_path / "empty",
            eval_dir=tmp_path,
            options=PrepareOptions(out_dir=tmp_path / "out"),
        )


def test_prepare_output_is_deterministic(repo_root: Path, tmp_path: Path) -> None:
    first = run_prepare(
        registry_path=repo_root / "data" / "sources.yaml",
        raw_dir=repo_root / "data" / "raw",
        eval_dir=repo_root / "data" / "evaluation",
        options=PrepareOptions(out_dir=tmp_path / "a", smoke=True, force=True),
        smoke_file=repo_root / "data" / "seed" / "smoke.jsonl",
    )
    second = run_prepare(
        registry_path=repo_root / "data" / "sources.yaml",
        raw_dir=repo_root / "data" / "raw",
        eval_dir=repo_root / "data" / "evaluation",
        options=PrepareOptions(out_dir=tmp_path / "b", smoke=True, force=True),
        smoke_file=repo_root / "data" / "seed" / "smoke.jsonl",
    )
    assert first["dataset_version"] == second["dataset_version"]
    assert first["files"]["train"]["sha256"] == second["files"]["train"]["sha256"]

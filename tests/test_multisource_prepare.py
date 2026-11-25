from __future__ import annotations

import json
from pathlib import Path

from cyberlite.data.config import DatasetConfig
from cyberlite.data.prepare import run_config_prepare


def _records(count: int, prefix: str) -> list[dict]:
    return [
        {
            "id": f"{prefix}-{index}",
            "source": "alpha",
            "license": "Synthetic",
            "task": "knowledge",
            "prompt": f"Explain defensive control {prefix}-{index}.",
            "response": (
                f"Defensive control {prefix}-{index} requires verification, logging, "
                "and a documented rollback. "
            )
            * 4,
            "metadata": {"source_version": "v1", "upstream_id": f"{prefix}-{index}"},
        }
        for index in range(count)
    ]


def _build_workspace(tmp_path: Path) -> DatasetConfig:
    (tmp_path / "data").mkdir()
    (tmp_path / "evaluation").mkdir()
    alpha = _records(3, "alpha")
    beta = _records(2, "beta")
    # One exact cross-source duplicate.
    duplicate = dict(alpha[0])
    duplicate["source"] = "beta"
    duplicate["id"] = "beta-duplicate"
    beta.append(duplicate)
    (tmp_path / "data" / "alpha.jsonl").write_text(
        "\n".join(json.dumps(item) for item in alpha) + "\n", encoding="utf-8"
    )
    (tmp_path / "data" / "beta.jsonl").write_text(
        "\n".join(json.dumps(item) for item in beta) + "\n", encoding="utf-8"
    )
    (tmp_path / "evaluation" / "heldout.jsonl").write_text(
        json.dumps(
            {
                "id": "eval-1",
                "question": "q",
                "choices": [" ".join(["heldout", "evaluation", "item"] * 10)],
                "answer": "A",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "data" / "sources.yaml").write_text(
        """
schema_version: 1
sources:
  alpha:
    title: Alpha source
    kind: jsonl
    license: Synthetic
    enabled: true
    revision: v1
  beta:
    title: Beta source
    kind: jsonl
    license: Synthetic
    enabled: true
    revision: v1
  bad:
    title: Unlicensed source
    kind: jsonl
    license: See-source
    enabled: true
  missing:
    title: Missing source
    kind: jsonl
    license: Synthetic
    enabled: true
""",
        encoding="utf-8",
    )
    config_path = tmp_path / "configs" / "build.yaml"
    config_path.parent.mkdir()
    config_path.write_text(
        """
schema_version: 1
name: multisource-test
seed: 11
out_dir: processed
manifest_dir: manifests
raw_dir: raw
cache_dir: cache
eval_dir: evaluation
registry: data/sources.yaml
download: false
tokenizer: ""
split: {train: 0.8, validation: 0.1, test: 0.1}
sources:
  alpha:
    paths: [data/alpha.jsonl]
    max_records: 3
  beta:
    paths: [data/beta.jsonl]
    max_records: 3
  missing:
    paths: [data/missing.jsonl]
  bad:
    paths: [data/beta.jsonl]
""",
        encoding="utf-8",
    )
    return DatasetConfig.load(config_path)


def test_multisource_build_is_deterministic_and_global(tmp_path: Path) -> None:
    config = _build_workspace(tmp_path)
    first = run_config_prepare(config)
    assert first["source_counts"]["alpha"] == 3
    assert first["source_counts"]["beta"] == 2
    assert first["cleaning"]["cross_source_duplicates"] == 1
    assert first["output_records"] == 5
    assert first["files"]["train"]["sha256"]
    assert first["reports"]["quality_report"]["sha256"]
    assert (tmp_path / "manifests" / "quality_report.json").is_file()
    assert (tmp_path / "manifests" / "contamination_report.json").is_file()
    assert (tmp_path / "manifests" / "license_report.json").is_file()
    assert (tmp_path / "manifests" / "README.md").is_file()

    second = run_config_prepare(config)
    assert first["dataset_version"] == second["dataset_version"]
    assert first["files"]["train"]["sha256"] == second["files"]["train"]["sha256"]
    assert first["files"]["test"]["sha256"] == second["files"]["test"]["sha256"]


def test_source_limit_and_missing_source_are_reported(tmp_path: Path) -> None:
    config = _build_workspace(tmp_path)
    manifest = run_config_prepare(config)
    alpha = next(item for item in manifest["sources"] if item["name"] == "alpha")
    assert alpha["records"] == 3
    assert any(item["source"] == "missing" for item in manifest["source_errors"])
    missing = next(item for item in manifest["sources"] if item["name"] == "missing")
    assert missing["records"] == 0


def test_license_filtering_quarantines_source(tmp_path: Path) -> None:
    config = _build_workspace(tmp_path)
    config.include_sources = ["alpha", "bad"]
    manifest = run_config_prepare(config)
    bad = next(item for item in manifest["sources"] if item["name"] == "bad")
    assert bad["status"] == "quarantined"
    assert "alpha" in manifest["source_counts"]


def test_offline_local_rebuild_works(tmp_path: Path) -> None:
    config = _build_workspace(tmp_path)
    config.offline = True
    manifest = run_config_prepare(config)
    assert manifest["output_records"] == 5


def test_include_and_exclude(tmp_path: Path) -> None:
    config = _build_workspace(tmp_path)
    config.include_sources = ["alpha"]
    config.exclude_sources = []
    manifest = run_config_prepare(config)
    assert manifest["source_counts"] == {"alpha": 3}

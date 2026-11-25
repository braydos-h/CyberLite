from __future__ import annotations

from pathlib import Path

import pytest
from cyberlite.data.config import DatasetConfig, QualityThresholds


def _write_config(path: Path, extra: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """
schema_version: 1
name: test-build
seed: 7
out_dir: processed
manifest_dir: manifests
raw_dir: raw
cache_dir: cache
eval_dir: evaluation
registry: data/sources.yaml
download: false
tokenizer: ""
split:
  train: 0.8
  validation: 0.1
  test: 0.1
sources:
  alpha:
    include: true
    paths: [data/alpha.jsonl]
    max_records: 2
  beta:
    include: false
    paths: [data/beta.jsonl]
"""
        + extra,
        encoding="utf-8",
    )
    return path


def test_dataset_config_loads_and_hashes_stably(tmp_path: Path) -> None:
    path = _write_config(tmp_path / "configs" / "build.yaml")
    first = DatasetConfig.load(path)
    second = DatasetConfig.load(path)
    assert first.sha256() == second.sha256()
    assert first.base_dir == str(tmp_path)
    assert first.ratios.train == 0.8
    assert [source.name for source in first.resolve_sources()] == ["alpha"]
    assert first.resolve("processed") == tmp_path / "processed"


def test_config_hash_ignores_output_paths(tmp_path: Path) -> None:
    first = DatasetConfig.load(_write_config(tmp_path / "configs" / "a.yaml"))
    second = DatasetConfig.load(_write_config(tmp_path / "configs" / "b.yaml"))
    second.out_dir = "other-output"
    second.manifest_dir = "other-manifests"
    second.raw_dir = "other-raw"
    assert first.sha256() == second.sha256()


def test_include_and_exclude_conflict(tmp_path: Path) -> None:
    config = DatasetConfig.load(_write_config(tmp_path / "configs" / "build.yaml"))
    config.include_sources = ["alpha"]
    config.exclude_sources = ["alpha"]
    with pytest.raises(ValueError, match="both included and excluded"):
        config.resolve_sources()


def test_unknown_include_source_rejected(tmp_path: Path) -> None:
    config = DatasetConfig.load(_write_config(tmp_path / "configs" / "build.yaml"))
    config.include_sources = ["missing"]
    with pytest.raises(ValueError, match="unknown source"):
        config.resolve_sources()


def test_unknown_top_level_field_rejected(tmp_path: Path) -> None:
    path = _write_config(tmp_path / "configs" / "build.yaml", "unexpected: true\n")
    with pytest.raises(ValueError, match="unknown fields"):
        DatasetConfig.load(path)


def test_quality_validation() -> None:
    with pytest.raises(ValueError, match=r"sum to 1\.0"):
        from cyberlite.data.splits import SplitRatios

        SplitRatios(0.9, 0.2, 0.1)
    with pytest.raises(ValueError, match="between 0 and 1"):
        QualityThresholds(max_url_ratio=1.5)


def test_repository_pilot_config_is_valid(repo_root: Path) -> None:
    config = DatasetConfig.load(repo_root / "configs" / "dataset_pilot.yaml")
    names = {source.name for source in config.resolve_sources()}
    assert {"mitre_attack", "mitre_cwe", "nist_nvd", "owasp_cheatsheets"} <= names
    assert config.sha256()

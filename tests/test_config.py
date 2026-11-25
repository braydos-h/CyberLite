from __future__ import annotations

from pathlib import Path

import pytest
from cyberlite.config import (
    ExperimentConfig,
    load_config,
    parse_overrides,
)


def test_every_config_loads(repo_root: Path) -> None:
    # Dataset build configurations use a different schema and are validated
    # by tests/test_dataset_config.py.
    paths = sorted(
        path
        for path in (repo_root / "configs").glob("*.yaml")
        if not path.name.startswith("dataset_")
    )
    assert len(paths) >= 5
    for path in paths:
        config = load_config(path)
        assert isinstance(config, ExperimentConfig)
        assert config.model.id
        assert config.sha256()


def test_unknown_key_rejected(repo_root: Path, tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("run:\n  name: x\n  typo_key: true\n", encoding="utf-8")
    with pytest.raises(ValueError, match="typo_key"):
        load_config(path)


def test_overrides_are_typed_and_nested(repo_root: Path) -> None:
    config = load_config(
        repo_root / "configs" / "qlora.yaml",
        [
            "training.max_seq_length=512",
            "training.bf16=false",
            "run.tags=[smoke, test]",
        ],
    )
    assert config.training.max_seq_length == 512
    assert config.training.bf16 is False
    assert config.run.tags == ["smoke", "test"]


def test_parse_overrides_rejects_missing_equals() -> None:
    with pytest.raises(ValueError):
        parse_overrides(["training.max_seq_length"])


def test_quantized_training_requires_lora(repo_root: Path) -> None:
    with pytest.raises(ValueError, match=r"requires lora\.enabled"):
        load_config(
            repo_root / "configs" / "qlora.yaml",
            ["lora.enabled=false", "quantization.load_in_4bit=true"],
        )


def test_conflicting_precision_rejected(repo_root: Path) -> None:
    with pytest.raises(ValueError, match="mutually exclusive"):
        load_config(
            repo_root / "configs" / "lora.yaml",
            ["training.bf16=true", "training.fp16=true"],
        )


def test_config_hash_is_stable(repo_root: Path) -> None:
    first = load_config(repo_root / "configs" / "lora.yaml")
    second = load_config(repo_root / "configs" / "lora.yaml")
    assert first.sha256() == second.sha256()
    assert first.canonical_json() == second.canonical_json()


def test_invalid_sequence_length(repo_root: Path) -> None:
    with pytest.raises(ValueError):
        load_config(repo_root / "configs" / "lora.yaml", ["training.max_seq_length=8"])

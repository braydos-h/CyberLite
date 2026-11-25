from __future__ import annotations

import json
from pathlib import Path

import pytest
from cyberlite.config import load_config
from cyberlite.training.trainer import _resolve_resume_checkpoint


def _config(repo_root: Path, output_dir: Path):
    config = load_config(repo_root / "configs" / "qlora.yaml")
    config.run.output_dir = str(output_dir)
    return config


def test_resume_fingerprint_ignores_resume_bookkeeping(repo_root: Path, tmp_path: Path) -> None:
    config = _config(repo_root, tmp_path)
    first = config.training_fingerprint()
    config.training.resume_from_checkpoint = str(tmp_path / "checkpoint-1")
    assert config.training_fingerprint() == first


def test_resume_auto_resolves_and_checks_metadata(repo_root: Path, tmp_path: Path) -> None:
    config = _config(repo_root, tmp_path)
    checkpoint = tmp_path / "checkpoint-1"
    checkpoint.mkdir()
    (checkpoint / "trainer_state.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "run_metadata.json").write_text(
        json.dumps({"config_fingerprint": config.training_fingerprint()}),
        encoding="utf-8",
    )
    config.training.resume_from_checkpoint = "auto"
    assert _resolve_resume_checkpoint(config, tmp_path) == str(checkpoint)


def test_resume_rejects_changed_experiment(repo_root: Path, tmp_path: Path) -> None:
    config = _config(repo_root, tmp_path)
    checkpoint = tmp_path / "checkpoint-1"
    checkpoint.mkdir()
    (checkpoint / "trainer_state.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "run_metadata.json").write_text(
        json.dumps({"config_fingerprint": "different-experiment"}),
        encoding="utf-8",
    )
    config.training.resume_from_checkpoint = "auto"
    with pytest.raises(ValueError, match="resume configuration"):
        _resolve_resume_checkpoint(config, tmp_path)


def test_resume_rejects_incomplete_checkpoint(repo_root: Path, tmp_path: Path) -> None:
    config = _config(repo_root, tmp_path)
    checkpoint = tmp_path / "checkpoint-1"
    checkpoint.mkdir()
    config.training.resume_from_checkpoint = str(checkpoint)
    with pytest.raises(ValueError, match=r"trainer_state\.json"):
        _resolve_resume_checkpoint(config, tmp_path)


def test_resume_rejects_missing_checkpoint(repo_root: Path, tmp_path: Path) -> None:
    config = _config(repo_root, tmp_path)
    config.training.resume_from_checkpoint = str(tmp_path / "does-not-exist")
    with pytest.raises(FileNotFoundError, match="resume checkpoint not found"):
        _resolve_resume_checkpoint(config, tmp_path)

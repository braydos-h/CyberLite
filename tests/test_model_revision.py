from __future__ import annotations

from types import SimpleNamespace

import pytest
from cyberlite.config import (
    PINNED_QWEN35_REVISION,
    ExperimentConfig,
    load_config,
)
from cyberlite.training.model import (
    _verify_revision,
    checkpoint_revision,
    looks_like_commit,
    model_revision_info,
)


def test_research_configs_pin_the_baseline_revision(repo_root) -> None:
    for name in ("lora.yaml", "qlora.yaml", "low_vram.yaml", "distillation.yaml"):
        config = load_config(repo_root / "configs" / name)
        assert config.model.require_pinned_revision is True
        assert config.model.revision == PINNED_QWEN35_REVISION
        assert config.model.matched_baseline is True
        assert config.data.train_file.startswith("data/processed/")
        assert "pilot-v2" in config.data.train_file or name == "distillation.yaml"


def test_production_configs_use_pilot_v2_paths(repo_root) -> None:
    expected = {
        "train": "data/processed/pilot-v2/train.jsonl",
        "validation": "data/processed/pilot-v2/validation.jsonl",
        "test": "data/processed/pilot-v2/test.jsonl",
        "manifest": "data/manifests/pilot-v2/manifest.json",
    }
    for name in ("lora.yaml", "qlora.yaml", "low_vram.yaml"):
        config = load_config(repo_root / "configs" / name)
        assert config.data.train_file == expected["train"]
        assert config.data.validation_file == expected["validation"]
        assert config.data.test_file == expected["test"]
        assert config.data.manifest_file == expected["manifest"]
        assert config.data.dataset_version == "cyberlite-data-2.0.0-04b01b437805"
        assert config.data.expected_split_counts == {
            "train": 6351,
            "validation": 416,
            "test": 421,
        }

    distillation = load_config(repo_root / "configs" / "distillation.yaml")
    assert distillation.data.train_file == "data/processed/distill/train.jsonl"
    assert distillation.data.validation_file == "data/processed/distill/validation.jsonl"
    assert distillation.data.test_file == "data/processed/distill/test.jsonl"
    assert distillation.data.manifest_file == "data/processed/distill/manifest.json"

    smoke = load_config(repo_root / "configs" / "smoke.yaml")
    assert smoke.training.smoke is True
    assert smoke.data.train_file == "data/processed/smoke/train.jsonl"
    assert smoke.data.manifest_file == "data/processed/smoke/manifest.json"
    assert "pilot-v2" not in smoke.data.train_file


def test_config_rejects_conflicting_matched_baseline_revision(tmp_path) -> None:
    path = tmp_path / "wrong-revision.yaml"
    path.write_text(
        """
schema_version: 1
model:
  id: Qwen/Qwen3.5-0.8B
  revision: deadbeefdeadbeefdeadbeefdeadbeefdeadbeef
  require_pinned_revision: true
  matched_baseline: true
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="matched_baseline"):
        load_config(path)


def test_checkpoint_revision_reads_common_locations() -> None:
    assert checkpoint_revision(SimpleNamespace(_commit_hash="abc")) == "abc"
    assert checkpoint_revision({"init_kwargs": {"_commit_hash": "def"}}) == "def"
    assert checkpoint_revision(SimpleNamespace(init_kwargs={"revision": "tag"})) == "tag"
    assert checkpoint_revision(None) is None
    assert looks_like_commit(PINNED_QWEN35_REVISION)
    assert not looks_like_commit("main")


def test_model_revision_info_propagates_resolved_revision(repo_root) -> None:
    config = load_config(repo_root / "configs" / "qlora.yaml")
    model = SimpleNamespace(
        config=SimpleNamespace(_commit_hash=PINNED_QWEN35_REVISION),
    )
    tokenizer = SimpleNamespace(init_kwargs={"_commit_hash": PINNED_QWEN35_REVISION})
    info = model_revision_info(config, model, tokenizer)
    assert info["requested_revision"] == PINNED_QWEN35_REVISION
    assert info["resolved_revision"] == PINNED_QWEN35_REVISION
    assert info["tokenizer_revision"] == PINNED_QWEN35_REVISION
    assert info["revision_verified"] is True
    assert info["matches_baseline"] is True


def test_revision_mismatch_fails_closed(repo_root) -> None:
    config = load_config(repo_root / "configs" / "qlora.yaml")
    bad_model = SimpleNamespace(
        config=SimpleNamespace(_commit_hash="0" * 40),
    )
    tokenizer = SimpleNamespace(init_kwargs={"_commit_hash": PINNED_QWEN35_REVISION})
    with pytest.raises(RuntimeError, match="silently changed"):
        _verify_revision(config, bad_model, tokenizer)
    with pytest.raises(RuntimeError, match="tokenizer"):
        _verify_revision(
            config,
            SimpleNamespace(config=SimpleNamespace(_commit_hash=PINNED_QWEN35_REVISION)),
            SimpleNamespace(init_kwargs={"_commit_hash": "1" * 40}),
        )


def test_evaluation_info_records_revision_metadata() -> None:
    from cyberlite.inference.engine import InferenceEngine

    class Parameter:
        def numel(self) -> int:
            return 852_985_920

    class Model:
        config = SimpleNamespace(
            text_config=SimpleNamespace(hidden_size=1024, num_hidden_layers=24)
        )

        def parameters(self):
            return [Parameter()]

    engine = object.__new__(InferenceEngine)
    engine.model_id = "Qwen/Qwen3.5-0.8B"
    engine.revision = PINNED_QWEN35_REVISION
    engine.resolved_revision = PINNED_QWEN35_REVISION
    engine.tokenizer_revision = PINNED_QWEN35_REVISION
    engine.adapter_path = None
    engine.adapter_sha256 = None
    engine.auto_class = "AutoModelForImageTextToText"
    engine.device = "cpu"
    engine.dtype = "torch.float32"
    engine.quantized = False
    engine.max_context = 262_144
    engine.model = Model()
    info = engine.info()
    assert info["revision"] == PINNED_QWEN35_REVISION
    assert info["resolved_revision"] == PINNED_QWEN35_REVISION
    assert info["tokenizer_revision"] == PINNED_QWEN35_REVISION
    assert info["revision_verified"] is True


def test_matched_baseline_requires_a_revision() -> None:
    config = ExperimentConfig()
    with pytest.raises(RuntimeError, match="matched_baseline"):
        _verify_revision(
            config,
            SimpleNamespace(config=SimpleNamespace(_commit_hash=PINNED_QWEN35_REVISION)),
            SimpleNamespace(init_kwargs={}),
        )

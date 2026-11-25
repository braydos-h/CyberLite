"""Typed experiment configuration with fail-fast validation.

Configuration is deliberately explicit: every training run records the full
effective configuration and a SHA-256 hash so that results can be traced back to
the exact settings that produced them.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator

SCHEMA_VERSION = 1

# The E0 SecEval baseline in results/baseline/e0-instruct-seceval/README.md was
# produced from this exact checkpoint. Matched-comparison configs pin it so a
# changed upstream revision cannot silently change the starting model.
PINNED_QWEN35_MODEL_ID = "Qwen/Qwen3.5-0.8B"
PINNED_QWEN35_REVISION = "2fc06364715b967f1860aea9cf38778875588b17"

# Production pilot-v2 artifact. Splits are generated locally and ignored by Git;
# the frozen manifest under data/manifests/ is the integrity reference.
PILOT_V2_DATASET_VERSION = "cyberlite-data-2.0.0-04b01b437805"
PILOT_V2_SPLIT_COUNTS = {"train": 6351, "validation": 416, "test": 421}


class StrictModel(BaseModel):
    """Base model that rejects unknown keys to catch configuration typos."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class RunConfig(StrictModel):
    name: str = "cyberlite-lora"
    seed: int = 42
    output_dir: str = "runs/cyberlite-lora"
    tags: list[str] = Field(default_factory=list)
    notes: str = ""


class ModelConfig(StrictModel):
    id: str = PINNED_QWEN35_MODEL_ID
    revision: str | None = None
    # Research configs set this true so a missing revision is a hard error.
    require_pinned_revision: bool = False
    # A matched experiment must use the same checkpoint as its reference run.
    # Set false only for a deliberately separate model/revision experiment.
    matched_baseline: bool = True
    dtype: Literal["auto", "float32", "float16", "bfloat16"] = "bfloat16"
    device: Literal["auto", "cpu", "cuda", "mps"] = "auto"
    attn_implementation: Literal["auto", "sdpa", "eager", "flash_attention_2"] = "sdpa"
    trust_remote_code: bool = False
    freeze_vision: bool = True
    use_cache: bool = False
    # Planning hint used by --estimate-only before weights are downloaded.
    # Set this when testing a control model whose size is not in its name.
    parameters_b: float | None = Field(default=None, gt=0)
    max_memory: dict[str, str] | None = None

    @field_validator("id")
    @classmethod
    def _non_empty_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("model.id must be a non-empty Hugging Face model identifier")
        return value.strip()

    @model_validator(mode="after")
    def _revision_policy(self) -> ModelConfig:
        if self.require_pinned_revision and not self.revision:
            raise ValueError(
                "model.require_pinned_revision=true requires model.revision; "
                f"use {PINNED_QWEN35_REVISION} for the registered baseline checkpoint"
            )
        if (
            self.matched_baseline
            and self.id == PINNED_QWEN35_MODEL_ID
            and self.revision is not None
            and self.revision != PINNED_QWEN35_REVISION
        ):
            raise ValueError(
                "model.matched_baseline=true requires the registered revision "
                f"{PINNED_QWEN35_REVISION}; set model.matched_baseline=false for a "
                "deliberately separate checkpoint experiment"
            )
        return self


class QuantizationConfig(StrictModel):
    load_in_4bit: bool = False
    load_in_8bit: bool = False
    bnb_4bit_quant_type: Literal["nf4", "fp4"] = "nf4"
    bnb_4bit_use_double_quant: bool = True
    bnb_4bit_compute_dtype: Literal["bfloat16", "float16", "float32"] = "bfloat16"

    @model_validator(mode="after")
    def _one_mode(self) -> QuantizationConfig:
        if self.load_in_4bit and self.load_in_8bit:
            raise ValueError("choose at most one of quantization.load_in_4bit / load_in_8bit")
        return self

    @property
    def enabled(self) -> bool:
        return self.load_in_4bit or self.load_in_8bit


class LoraConfig(StrictModel):
    enabled: bool = True
    r: int = Field(default=16, ge=1, le=512)
    alpha: int = Field(default=32, ge=1)
    dropout: float = Field(default=0.05, ge=0.0, lt=1.0)
    target_modules: Literal["auto"] | list[str] = "auto"
    bias: Literal["none", "all", "lora_only"] = "none"
    task_type: Literal["CAUSAL_LM", "FEATURE_EXTRACTION"] = "CAUSAL_LM"
    modules_to_save: list[str] | None = None


class TrainingConfig(StrictModel):
    epochs: float = Field(default=1.0, gt=0)
    max_steps: int = -1
    per_device_batch_size: int = Field(default=1, ge=1)
    gradient_accumulation_steps: int = Field(default=8, ge=1)
    learning_rate: float = Field(default=2e-4, gt=0)
    weight_decay: float = Field(default=0.01, ge=0)
    warmup_ratio: float = Field(default=0.03, ge=0, le=1)
    lr_scheduler_type: str = "cosine"
    max_seq_length: int = Field(default=1024, ge=64, le=262_144)
    gradient_checkpointing: bool = True
    optim: Literal[
        "adamw_torch",
        "adamw_torch_fused",
        "adamw_8bit",
        "paged_adamw_8bit",
        "adafactor",
    ] = "adamw_torch"
    bf16: bool = True
    fp16: bool = False
    tf32: bool = True
    logging_steps: int = Field(default=10, ge=1)
    save_steps: int = Field(default=100, ge=1)
    eval_steps: int = Field(default=100, ge=1)
    save_total_limit: int = Field(default=3, ge=1)
    dataloader_num_workers: int = Field(default=0, ge=0)
    report_to: list[str] = Field(default_factory=list)
    resume_from_checkpoint: str | None = None
    smoke: bool = False

    @model_validator(mode="after")
    def _precision(self) -> TrainingConfig:
        if self.bf16 and self.fp16:
            raise ValueError("training.bf16 and training.fp16 are mutually exclusive")
        return self


class DataConfig(StrictModel):
    # Production defaults point at the expanded pilot. Smoke and distillation
    # configs override every path explicitly.
    train_file: str = "data/processed/pilot-v2/train.jsonl"
    validation_file: str | None = "data/processed/pilot-v2/validation.jsonl"
    test_file: str | None = "data/processed/pilot-v2/test.jsonl"
    format: Literal["auto", "chat", "completion", "fim"] = "auto"
    system_prompt: str | None = (
        "You are CyberLite, a defensive cybersecurity assistant. Prefer verifiable, "
        "safe guidance. Never claim to have executed commands or accessed systems."
    )
    chat_template_kwargs: dict[str, Any] = Field(default_factory=lambda: {"enable_thinking": False})
    max_train_samples: int | None = Field(default=None, ge=1)
    max_eval_samples: int | None = Field(default=256, ge=1)

    # --- Dataset identity and integrity -------------------------------------
    manifest_file: str | None = "data/manifests/pilot-v2/manifest.json"
    dataset_version: str | None = PILOT_V2_DATASET_VERSION
    expected_split_counts: dict[str, int] = Field(
        default_factory=lambda: dict(PILOT_V2_SPLIT_COUNTS)
    )
    require_manifest: bool = True
    verify_integrity: bool = True
    require_provenance: bool = True
    require_validation: bool = True
    # Run the local 13-gram screen against data/evaluation during preflight and
    # before training. Missing evaluation files are reported, not silently
    # treated as a pass.
    require_contamination_screen: bool = True

    # --- Licensing ----------------------------------------------------------
    require_license: bool = True
    allowed_licenses: list[str] = Field(
        default_factory=lambda: [
            "Apache-2.0",
            "MIT",
            "BSD-2-Clause",
            "BSD-3-Clause",
            "CC-BY-4.0",
            "CC-BY-SA-4.0",
            "CC0-1.0",
            "Public-Domain",
            "Synthetic",
        ]
    )
    # Fail closed on licenses whose guidance still contains unresolved
    # questions. A specific license may be opted into only by naming it here;
    # there is deliberately no blanket "accept everything" switch.
    require_resolved_licenses: bool = True
    allow_unresolved_licenses: list[str] = Field(default_factory=list)

    # --- Tokenization -------------------------------------------------------
    # "truncate" keeps the first max_seq_length tokens and reserves one for EOS;
    # "drop" discards an over-length example instead. Neither changes the
    # configured sequence length.
    truncation_policy: Literal["truncate", "drop"] = "truncate"
    min_supervised_tokens: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def _license_and_path_policy(self) -> DataConfig:
        if self.require_license and not self.allowed_licenses:
            raise ValueError(
                "data.require_license=true requires a non-empty data.allowed_licenses list"
            )
        if self.require_validation and not self.validation_file:
            raise ValueError(
                "data.require_validation=true requires data.validation_file; "
                "set data.require_validation=false only for non-research runs"
            )
        unknown_splits = set(self.expected_split_counts) - {"train", "validation", "test"}
        if unknown_splits:
            raise ValueError(
                f"unknown split names in data.expected_split_counts: {sorted(unknown_splits)}"
            )
        if any(value < 0 for value in self.expected_split_counts.values()):
            raise ValueError("data.expected_split_counts values must be non-negative")
        paths = [
            ("train", self.train_file),
            ("validation", self.validation_file),
            ("test", self.test_file),
        ]
        resolved: dict[str, str] = {}
        for name, value in paths:
            if not value:
                continue
            normalized = str(Path(value).expanduser().resolve())
            for other_name, other_path in resolved.items():
                if normalized == other_path:
                    raise ValueError(
                        f"data.{name}_file and data.{other_name}_file must be distinct; "
                        "training, validation, and test isolation require separate files"
                    )
            resolved[name] = normalized
        return self


class DistillationConfig(StrictModel):
    """Offline sequence-level distillation from a larger local teacher.

    The teacher is only used by ``scripts/generate_distillation_data.py``; the
    generated corpus is reviewed, filtered, and versioned before training.
    """

    enabled: bool = False
    teacher_model_id: str = "Qwen/Qwen3.5-4B"
    teacher_revision: str | None = None
    prompts_file: str = "data/processed/distill_prompts.jsonl"
    output_file: str = "data/processed/distill_generated.jsonl"
    temperature: float = Field(default=0.8, ge=0.0, le=2.0)
    top_p: float = Field(default=0.95, gt=0.0, le=1.0)
    max_new_tokens: int = Field(default=768, ge=1)
    min_response_chars: int = Field(default=80, ge=1)
    max_samples: int | None = Field(default=None, ge=1)


class ReportingConfig(StrictModel):
    json_logs: bool = False
    # Cost is only reported when the user supplies an explicit assumption.
    # This prevents misleading "cost" figures based on invented prices.
    cost_per_gpu_hour_usd: float | None = Field(default=None, ge=0)
    electricity_cost_per_kwh_usd: float | None = Field(default=None, ge=0)
    hardware_watts: float | None = Field(default=None, gt=0)


class ExperimentConfig(StrictModel):
    _source_path: str | None = PrivateAttr(default=None)

    schema_version: int = SCHEMA_VERSION
    run: RunConfig = Field(default_factory=RunConfig)
    model: ModelConfig = Field(default_factory=ModelConfig)
    quantization: QuantizationConfig = Field(default_factory=QuantizationConfig)
    lora: LoraConfig = Field(default_factory=LoraConfig)
    training: TrainingConfig = Field(default_factory=TrainingConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    distillation: DistillationConfig = Field(default_factory=DistillationConfig)
    reporting: ReportingConfig = Field(default_factory=ReportingConfig)

    @model_validator(mode="after")
    def _cross_field(self) -> ExperimentConfig:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"unsupported schema_version={self.schema_version}; expected {SCHEMA_VERSION}"
            )
        q = self.quantization
        if q.enabled and not self.lora.enabled:
            raise ValueError("quantized training requires lora.enabled=true (QLoRA)")
        return self

    def canonical_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def training_fingerprint(self) -> str:
        """Hash of the experiment definition, excluding resume bookkeeping.

        Resuming must not look like a different experiment merely because
        ``training.resume_from_checkpoint`` changed from null to a path.
        """

        payload = self.model_dump(mode="json")
        training = payload.get("training", {})
        training["resume_from_checkpoint"] = None
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


def _deep_set(payload: dict[str, Any], dotted_key: str, value: Any) -> None:
    parts = dotted_key.split(".")
    cursor = payload
    for part in parts[:-1]:
        node = cursor.get(part)
        if node is None:
            node = {}
            cursor[part] = node
        if not isinstance(node, dict):
            raise ValueError(f"cannot set nested key through non-mapping: {part}")
        cursor = node
    cursor[parts[-1]] = value


def parse_overrides(overrides: list[str]) -> dict[str, Any]:
    """Parse ``key=value`` overrides, using YAML scalar typing."""

    payload: dict[str, Any] = {}
    for item in overrides:
        if "=" not in item:
            raise ValueError(f"override must look like key=value, got: {item!r}")
        key, raw = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"empty override key in {item!r}")
        try:
            value = yaml.safe_load(raw)
        except yaml.YAMLError:
            value = raw
        _deep_set(payload, key, value)
    return payload


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def load_config(path: str | Path, overrides: list[str] | None = None) -> ExperimentConfig:
    """Load, merge, validate, and return an experiment configuration."""

    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError(f"configuration not found: {config_path}")
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"configuration root must be a mapping: {config_path}")
    if overrides:
        raw = _deep_merge(raw, parse_overrides(overrides))
    config = ExperimentConfig.model_validate(raw)
    # Keep the source path for provenance without making it a validated field.
    config._source_path = str(config_path.resolve())
    return config


def dump_effective_config(config: ExperimentConfig, path: str | Path) -> None:
    """Write the effective configuration next to run artifacts."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

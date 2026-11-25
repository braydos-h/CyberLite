"""Training orchestration for supervised fine-tuning, LoRA, and QLoRA."""

from __future__ import annotations

import json
import math
import platform
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any

import torch
from transformers import TrainerCallback

from cyberlite import __version__
from cyberlite.config import ExperimentConfig, dump_effective_config
from cyberlite.hardware import (
    HardwareInfo,
    detect_hardware,
    estimate_cost,
    estimate_inference_memory_gb,
    estimate_training_memory_gb,
    peak_memory_report,
    recommend_tier,
)
from cyberlite.logging_utils import configure_logging, get_logger, log_event
from cyberlite.training.dataset import DataCollatorForCausalLM, build_datasets
from cyberlite.training.lora import apply_lora, count_trainable, prepare_for_training
from cyberlite.training.model import (
    freeze_vision_tower,
    load_base_model,
    model_summary,
    parse_parameters_b,
    resolve_device,
)

logger = get_logger(__name__)


@dataclass
class TrainingPlan:
    device: str
    parameters_b: float
    quantization_bits: int
    training_memory: dict[str, float]
    inference_memory: dict[str, float]
    fit_by_vram: dict[str, bool]
    recommendation: dict[str, Any]
    cost_assumptions: dict[str, Any]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "device": self.device,
            "parameters_b": self.parameters_b,
            "quantization_bits": self.quantization_bits,
            "training_memory": self.training_memory,
            "inference_memory": self.inference_memory,
            "fit_by_vram": self.fit_by_vram,
            "recommendation": self.recommendation,
            "cost_assumptions": self.cost_assumptions,
            "warnings": self.warnings,
        }


def _quantization_bits(config: ExperimentConfig) -> int:
    if config.quantization.load_in_4bit:
        return 4
    if config.quantization.load_in_8bit:
        return 8
    # Planning estimate: fp32 CPU runs need twice the memory of a bf16 run.
    return 32 if config.model.dtype == "float32" else 16


def build_plan(config: ExperimentConfig, hardware: HardwareInfo) -> TrainingPlan:
    device = resolve_device(config, hardware)
    parameters_b = parse_parameters_b(config.model.id, config.model.parameters_b)
    bits = _quantization_bits(config)
    training_memory = estimate_training_memory_gb(
        parameters_b,
        bits=bits,
        batch_size=config.training.per_device_batch_size,
        seq_length=config.training.max_seq_length,
        gradient_checkpointing=config.training.gradient_checkpointing,
    )
    inference_memory = estimate_inference_memory_gb(
        parameters_b, bits=bits, context_tokens=config.training.max_seq_length
    )
    fit_by_vram = {
        f"{tier}gb": training_memory["estimated_peak_gb"] <= tier * 0.9
        for tier in (4, 6, 8, 12, 16)
    }
    warnings: list[str] = []
    if bits < 16 and device != "cuda":
        warnings.append(
            "This configuration requests bitsandbytes quantization, which requires CUDA "
            "in this pipeline; the run will fail on the selected device."
        )
    if config.model.attn_implementation == "flash_attention_2" and device != "cuda":
        warnings.append("flash_attention_2 requires a compatible CUDA GPU; use sdpa or eager.")
    return TrainingPlan(
        device=device,
        parameters_b=parameters_b,
        quantization_bits=bits,
        training_memory=training_memory,
        inference_memory=inference_memory,
        fit_by_vram=fit_by_vram,
        recommendation=recommend_tier(hardware),
        cost_assumptions={
            "cost_per_gpu_hour_usd": config.reporting.cost_per_gpu_hour_usd,
            "electricity_cost_per_kwh_usd": config.reporting.electricity_cost_per_kwh_usd,
            "hardware_watts": config.reporting.hardware_watts,
        },
        warnings=warnings,
    )


def _git_metadata() -> dict[str, Any]:
    result: dict[str, Any] = {}
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True, timeout=5
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain"], stderr=subprocess.DEVNULL, text=True, timeout=5
        )
        result = {"commit": commit, "dirty": bool(status.strip())}
    except (OSError, subprocess.SubprocessError):
        result = {"commit": None, "dirty": None}
    return result


def _package_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in (
        "torch",
        "transformers",
        "peft",
        "accelerate",
        "datasets",
        "numpy",
        "bitsandbytes",
    ):
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = "not-installed"
    return versions


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")


class RunMetricsCallback(TrainerCallback):
    """Minimal callback that records duration, peak memory, and cost."""

    def __init__(
        self,
        *,
        config: ExperimentConfig,
        hardware: HardwareInfo,
        device: str,
        model_stats: dict[str, Any],
        dataset_stats: dict[str, Any],
        output_dir: Path,
    ) -> None:
        self.config = config
        self.hardware = hardware
        self.device = device
        self.model_stats = model_stats
        self.dataset_stats = dataset_stats
        self.output_dir = output_dir
        self.started_at = 0.0
        self.peak_allocated_gb = 0.0
        self.peak_reserved_gb = 0.0
        self.last_metrics: dict[str, Any] = {}

    # TrainerCallback-compatible duck typing; importing TrainerCallback at module
    # import time is avoided so configuration tools work without transformers.
    def on_train_begin(self, args: Any, state: Any, control: Any, **kwargs: Any) -> None:
        self.started_at = time.perf_counter()

    def on_step_end(self, args: Any, state: Any, control: Any, **kwargs: Any) -> None:
        if self.device == "cuda" and torch.cuda.is_available():
            self.peak_allocated_gb = max(
                self.peak_allocated_gb, torch.cuda.max_memory_allocated() / 1024**3
            )
            self.peak_reserved_gb = max(
                self.peak_reserved_gb, torch.cuda.max_memory_reserved() / 1024**3
            )

    def on_log(
        self, args: Any, state: Any, control: Any, logs: dict[str, Any] | None = None, **kwargs: Any
    ) -> None:
        if logs:
            self.last_metrics.update(
                {key: value for key, value in logs.items() if isinstance(value, (int, float))}
            )

    def on_train_end(self, args: Any, state: Any, control: Any, **kwargs: Any) -> None:
        duration = time.perf_counter() - self.started_at if self.started_at else 0.0
        steps = int(getattr(state, "global_step", 0))
        batch_tokens = (
            self.config.training.per_device_batch_size
            * self.config.training.gradient_accumulation_steps
            * self.config.training.max_seq_length
        )
        cost = estimate_cost(
            duration,
            cost_per_hour_usd=self.config.reporting.cost_per_gpu_hour_usd,
            watts=self.config.reporting.hardware_watts,
            electricity_cost_per_kwh_usd=self.config.reporting.electricity_cost_per_kwh_usd,
        )
        payload = {
            "status": "completed",
            "duration_seconds": round(duration, 3),
            "global_steps": steps,
            "approx_tokens_processed": steps * batch_tokens,
            "approx_tokens_per_second": round(steps * batch_tokens / duration, 2)
            if duration > 0
            else None,
            "peak_vram_allocated_gb": round(self.peak_allocated_gb, 3),
            "peak_vram_reserved_gb": round(self.peak_reserved_gb, 3),
            "memory": peak_memory_report(),
            "device": self.device,
            "hardware": self.hardware.to_dict(),
            "model": self.model_stats,
            "dataset": self.dataset_stats,
            "last_logged_metrics": self.last_metrics,
            "cost": cost,
            "note": "approx_tokens_processed is a step-based estimate, not a token counter.",
        }
        _write_json(self.output_dir / "training_metrics.json", payload)
        _write_json(
            self.output_dir / "trainer_log_history.json",
            list(getattr(state, "log_history", [])),
        )
        log_event(
            logger,
            "training_completed",
            duration_seconds=payload["duration_seconds"],
            peak_vram_gb=payload["peak_vram_allocated_gb"],
            steps=steps,
        )


def _effective_for_smoke(config: ExperimentConfig) -> ExperimentConfig:
    if not config.training.smoke:
        return config
    smoke = config.model_copy(deep=True)
    smoke.training.max_steps = (
        2 if smoke.training.max_steps < 0 else min(2, smoke.training.max_steps)
    )
    smoke.training.max_seq_length = min(smoke.training.max_seq_length, 256)
    smoke.training.per_device_batch_size = min(smoke.training.per_device_batch_size, 1)
    smoke.training.gradient_accumulation_steps = min(smoke.training.gradient_accumulation_steps, 2)
    smoke.training.logging_steps = 1
    smoke.training.save_steps = 2
    smoke.data.max_train_samples = min(smoke.data.max_train_samples or 8, 8)
    smoke.data.max_eval_samples = min(smoke.data.max_eval_samples or 4, 4)
    return smoke


def _training_arguments(
    config: ExperimentConfig,
    *,
    device: str,
    output_dir: Path,
    has_validation: bool,
    train_size: int,
    warmup_steps: int,
) -> Any:
    from transformers import TrainingArguments

    bf16 = config.training.bf16 and device == "cuda"
    fp16 = config.training.fp16 and device == "cuda" and not bf16
    if device == "cuda" and config.training.bf16 and not torch.cuda.is_bf16_supported():
        logger.warning("bfloat16 requested but unsupported on this GPU; disabling bf16")
        bf16 = False
    if config.training.optim in {"adamw_8bit", "paged_adamw_8bit"}:
        try:
            import bitsandbytes  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                f"training.optim={config.training.optim} requires bitsandbytes. "
                "Install requirements-optional.txt and verify CUDA support, or use adamw_torch."
            ) from exc

    args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=config.training.epochs,
        max_steps=config.training.max_steps,
        per_device_train_batch_size=config.training.per_device_batch_size,
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=config.training.gradient_accumulation_steps,
        learning_rate=config.training.learning_rate,
        weight_decay=config.training.weight_decay,
        warmup_steps=warmup_steps,
        lr_scheduler_type=config.training.lr_scheduler_type,
        optim=config.training.optim,
        bf16=bf16,
        fp16=fp16,
        tf32=config.training.tf32 and device == "cuda",
        logging_steps=config.training.logging_steps,
        logging_first_step=True,
        save_steps=config.training.save_steps,
        save_total_limit=config.training.save_total_limit,
        eval_strategy="steps" if has_validation else "no",
        save_strategy="steps",
        load_best_model_at_end=False,
        remove_unused_columns=False,
        label_names=["labels"],
        dataloader_num_workers=config.training.dataloader_num_workers,
        dataloader_pin_memory=device == "cuda",
        report_to=config.training.report_to,
        run_name=config.run.name,
        seed=config.run.seed,
        data_seed=config.run.seed,
        use_cpu=device == "cpu",
        gradient_checkpointing=False,  # enabled explicitly on the model for PEFT
        disable_tqdm=False,
    )
    if has_validation:
        args.eval_steps = config.training.eval_steps
    if train_size == 0:
        raise ValueError("training dataset is empty")
    return args


def estimate_steps(config: ExperimentConfig, train_size: int) -> int:
    if config.training.max_steps > 0:
        return config.training.max_steps
    batches = math.ceil(
        train_size
        / max(
            1, config.training.per_device_batch_size * config.training.gradient_accumulation_steps
        )
    )
    return max(1, int(batches * config.training.epochs))


def run_training(
    config: ExperimentConfig,
    *,
    force: bool = False,
    estimate_only: bool = False,
) -> dict[str, Any]:
    """Run a training job or emit a planning estimate."""

    configure_logging(
        level="INFO",
        json_logs=config.reporting.json_logs,
    )
    config = _effective_for_smoke(config)
    hardware = detect_hardware()
    plan = build_plan(config, hardware)
    output_dir = Path(config.run.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    dump_effective_config(config, output_dir / "config.effective.yaml")

    log_event(
        logger,
        "run_plan",
        run=config.run.name,
        model=config.model.id,
        config_sha256=config.sha256(),
        device=plan.device,
        estimated_peak_gb=plan.training_memory["estimated_peak_gb"],
    )
    if estimate_only:
        plan_payload = {
            "config_sha256": config.sha256(),
            "model_id": config.model.id,
            "plan": plan.to_dict(),
            "hardware": hardware.to_dict(),
            "note": "Planning estimate only. No model was downloaded and no training ran.",
        }
        _write_json(output_dir / "run_plan.json", plan_payload)
        log_event(logger, "estimate_only_complete", path=str(output_dir / "run_plan.json"))
        return plan_payload

    if not force and not config.training.resume_from_checkpoint:
        existing = [
            path for path in output_dir.iterdir() if path.name not in {"config.effective.yaml"}
        ]
        if existing:
            raise FileExistsError(
                f"output directory is not empty: {output_dir}. Use --force or "
                "training.resume_from_checkpoint to continue."
            )

    train_path = Path(config.data.train_file)
    if not train_path.is_file():
        raise FileNotFoundError(
            f"training data not found: {train_path}. Run "
            "`python scripts/prepare_dataset.py --smoke` for the tiny validation set."
        )

    from transformers import Trainer, set_seed

    set_seed(config.run.seed)
    device = plan.device
    if device == "cuda":
        torch.cuda.reset_peak_memory_stats()

    model, tokenizer, auto_class = load_base_model(
        config, for_training=True, device=device, hardware=hardware
    )
    model_class = type(model).__name__
    if config.quantization.enabled:
        from peft import prepare_model_for_kbit_training

        model = prepare_model_for_kbit_training(
            model,
            use_gradient_checkpointing=config.training.gradient_checkpointing,
            gradient_checkpointing_kwargs={"use_reentrant": False},
        )
    if config.model.freeze_vision:
        freeze_vision_tower(model)
    if config.lora.enabled:
        model = apply_lora(model, config.lora)
    model = prepare_for_training(model, config)
    total_params, trainable_params = count_trainable(model)

    train_dataset, validation_dataset = build_datasets(
        tokenizer,
        train_file=train_path,
        validation_file=config.data.validation_file,
        max_seq_length=config.training.max_seq_length,
        format=config.data.format,
        system_prompt=config.data.system_prompt,
        template_kwargs=config.data.chat_template_kwargs,
        max_train_samples=config.data.max_train_samples,
        max_eval_samples=config.data.max_eval_samples,
    )
    collator = DataCollatorForCausalLM(tokenizer)
    total_steps = estimate_steps(config, len(train_dataset))
    warmup_steps = int(total_steps * config.training.warmup_ratio)
    args = _training_arguments(
        config,
        device=device,
        output_dir=output_dir,
        has_validation=validation_dataset is not None,
        train_size=len(train_dataset),
        warmup_steps=warmup_steps,
    )

    model_stats = {
        **model_summary(model),
        "auto_class": auto_class,
        "loaded_class": model_class,
        "total_parameters": total_params,
        "trainable_parameters": trainable_params,
        "trainable_percent": round(100 * trainable_params / total_params, 4)
        if total_params
        else 0.0,
        "quantized": config.quantization.enabled,
    }
    dataset_stats = {
        "train": train_dataset.stats.to_dict(),
        "validation": validation_dataset.stats.to_dict() if validation_dataset else None,
    }
    callback = RunMetricsCallback(
        config=config,
        hardware=hardware,
        device=device,
        model_stats=model_stats,
        dataset_stats=dataset_stats,
        output_dir=output_dir,
    )

    metadata = {
        "cyberlite_version": __version__,
        "created_at": datetime.now(tz=UTC).isoformat(),
        "config": config.model_dump(mode="json"),
        "config_sha256": config.sha256(),
        "config_source": getattr(config, "_source_path", None),
        "model": model_stats,
        "dataset": dataset_stats,
        "hardware": hardware.to_dict(),
        "packages": _package_versions(),
        "git": _git_metadata(),
        "python": platform.python_version(),
        "command": " ".join(sys.argv),
        "plan": plan.to_dict(),
    }
    dataset_manifest = train_path.parent / "manifest.json"
    if dataset_manifest.is_file():
        try:
            manifest_data = json.loads(dataset_manifest.read_text(encoding="utf-8"))
            metadata["dataset_manifest"] = {
                "path": str(dataset_manifest),
                "dataset_version": manifest_data.get("dataset_version"),
                "split_counts": manifest_data.get("split_counts"),
                "files": manifest_data.get("files", {}).get("train"),
            }
        except json.JSONDecodeError:
            metadata["dataset_manifest"] = {"path": str(dataset_manifest), "error": "invalid JSON"}
    _write_json(output_dir / "run_metadata.json", metadata)

    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=train_dataset,
        eval_dataset=validation_dataset,
        data_collator=collator,
        callbacks=[callback],
    )
    resume = config.training.resume_from_checkpoint
    resume_arg: str | bool | None = True if resume == "auto" else resume
    log_event(
        logger,
        "training_start",
        examples=len(train_dataset),
        steps=total_steps,
        trainable_parameters=trainable_params,
        resume=resume,
    )
    trainer.train(resume_from_checkpoint=resume_arg)
    trainer.save_model(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))
    from cyberlite.data.schema import sha256_file

    artifact_paths = sorted(output_dir.glob("adapter_model.*")) + sorted(
        output_dir.glob("adapter_config.json")
    )
    metadata["artifacts"] = {
        path.name: sha256_file(path) for path in artifact_paths if path.is_file()
    }
    metadata["finished_at"] = datetime.now(tz=UTC).isoformat()
    _write_json(output_dir / "run_metadata.json", metadata)

    summary = {
        "status": "completed",
        "output_dir": str(output_dir),
        "model": model_stats,
        "dataset": dataset_stats,
        "duration_file": str(output_dir / "training_metrics.json"),
        "config_sha256": config.sha256(),
        "plan": plan.to_dict(),
    }
    log_event(logger, "run_finished", output_dir=str(output_dir))
    return summary

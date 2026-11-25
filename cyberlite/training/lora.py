"""LoRA/QLoRA adapter construction and parameter accounting."""

from __future__ import annotations

from typing import Any

from cyberlite.config import LoraConfig as CyberLiteLoraConfig
from cyberlite.logging_utils import get_logger

logger = get_logger(__name__)

# Qwen3.5 combines gated full-attention layers with Gated DeltaNet linear
# attention layers. Targeting only q_proj/v_proj would leave most of the
# recurrent projections untrained, so the default set covers both block types.
QWEN_TARGET_MODULES = [
    "q_proj",
    "k_proj",
    "v_proj",
    "o_proj",
    "in_proj_qkv",
    "in_proj_z",
    "in_proj_b",
    "in_proj_a",
    "out_proj",
    "gate_proj",
    "up_proj",
    "down_proj",
]

GENERIC_FALLBACK_TARGETS = [
    "q_proj",
    "k_proj",
    "v_proj",
    "o_proj",
    "gate_proj",
    "up_proj",
    "down_proj",
]


def available_target_modules(model: Any) -> set[str]:
    names: set[str] = set()
    for module_name, _ in model.named_modules():
        names.add(module_name.rsplit(".", 1)[-1])
    return names


def resolve_target_modules(model: Any, configured: str | list[str]) -> list[str]:
    available = available_target_modules(model)
    if isinstance(configured, list):
        missing = [name for name in configured if name not in available]
        if missing:
            raise ValueError(
                f"LoRA target modules not present in model: {missing}. "
                f"Available linear projections include: {sorted(available)[:30]}..."
            )
        return configured
    selected = [name for name in QWEN_TARGET_MODULES if name in available]
    if not selected:
        selected = [name for name in GENERIC_FALLBACK_TARGETS if name in available]
    if not selected:
        raise ValueError(
            "could not infer LoRA target modules for this architecture; set "
            "lora.target_modules explicitly to a list of module names"
        )
    return selected


def build_lora_config(config: CyberLiteLoraConfig, model: Any) -> Any:
    from peft import LoraConfig as PeftLoraConfig

    targets = resolve_target_modules(model, config.target_modules)
    logger.info("LoRA targets resolved", extra={"targets": targets, "r": config.r})
    return PeftLoraConfig(
        r=config.r,
        lora_alpha=config.alpha,
        lora_dropout=config.dropout,
        bias=config.bias,
        target_modules=targets,
        task_type=config.task_type,
        modules_to_save=config.modules_to_save,
    )


def apply_lora(model: Any, config: CyberLiteLoraConfig) -> Any:
    from peft import get_peft_model

    if not config.enabled:
        return model
    peft_config = build_lora_config(config, model)
    peft_model = get_peft_model(model, peft_config)
    total, trainable = count_trainable(peft_model)
    logger.info(
        "adapter attached",
        extra={
            "trainable_parameters": trainable,
            "total_parameters": total,
            "trainable_percent": round(100 * trainable / total, 4) if total else 0.0,
        },
    )
    return peft_model


def count_trainable(model: Any) -> tuple[int, int]:
    total = sum(parameter.numel() for parameter in model.parameters())
    trainable = sum(
        parameter.numel() for parameter in model.parameters() if parameter.requires_grad
    )
    return total, trainable


def prepare_for_training(model: Any, config: Any) -> Any:
    """Enable gradient checkpointing and input gradients for PEFT training."""

    if config.training.gradient_checkpointing:
        try:
            # transformers >= 5 names this activation checkpointing.
            model.activation_checkpointing_enable(
                activation_checkpointing_kwargs={"use_reentrant": False}
            )
        except (AttributeError, TypeError):
            try:
                model.gradient_checkpointing_enable(
                    gradient_checkpointing_kwargs={"use_reentrant": False}
                )
            except TypeError:
                model.gradient_checkpointing_enable()
        if hasattr(model, "enable_input_require_grads"):
            model.enable_input_require_grads()
    return model

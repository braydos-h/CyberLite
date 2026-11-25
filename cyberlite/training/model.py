"""Model loading with architecture-aware handling.

Qwen3.5 checkpoints are multimodal hybrid models (``Qwen3_5ForConditionalGeneration``)
with linear-attention layers and a vision tower. Loading them through a plain
``AutoModelForCausalLM`` is not valid. This module inspects the checkpoint config
and selects an appropriate auto class, and it records the choice in run metadata.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from cyberlite.config import ExperimentConfig
from cyberlite.logging_utils import get_logger

logger = get_logger(__name__)

_DTYPE_MAP = {
    "float32": "float32",
    "float16": "float16",
    "bfloat16": "bfloat16",
    "auto": "auto",
}


@dataclass
class ModelBundle:
    model: Any
    tokenizer: Any
    model_class: str
    parameter_count: int
    trainable_parameters: int
    vision_frozen: bool
    device: str


def parse_parameters_b(model_id: str, override: float | None = None) -> float:
    """Infer a planning parameter count from the model name."""

    if override is not None:
        return override
    match = re.search(r"(\d+(?:\.\d+)?)\s*[bB](?:\b|-)", model_id)
    if match:
        return float(match.group(1))
    logger.warning(
        "could not infer parameter count from model id; using 0.8B planning default "
        "(set model.parameters_b to correct this)",
        extra={"model_id": model_id},
    )
    return 0.8


def resolve_device(config: ExperimentConfig, hardware: Any) -> str:
    requested = config.model.device
    if requested == "auto":
        return hardware.recommended_device
    if requested == "cuda" and not hardware.cuda_available:
        raise RuntimeError("model.device=cuda but no CUDA device is available")
    if requested == "mps" and not hardware.mps_available:
        raise RuntimeError("model.device=mps but MPS is not available")
    return requested


def load_tokenizer(config: ExperimentConfig) -> Any:
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        config.model.id,
        revision=config.model.revision,
        trust_remote_code=config.model.trust_remote_code,
        use_fast=True,
    )
    if tokenizer.pad_token_id is None:
        if tokenizer.eos_token_id is None:
            raise ValueError("tokenizer defines neither pad_token_id nor eos_token_id")
        tokenizer.pad_token = tokenizer.eos_token
    return tokenizer


def _is_multimodal(config: Any) -> bool:
    architectures = getattr(config, "architectures", None) or []
    if any("ConditionalGeneration" in str(architecture) for architecture in architectures):
        return True
    return hasattr(config, "vision_config") and getattr(config, "vision_config", None) is not None


def load_base_model(
    config: ExperimentConfig,
    *,
    for_training: bool,
    device: str,
    hardware: Any,
) -> tuple[Any, Any, str]:
    """Load a model and tokenizer, returning ``(model, tokenizer, class_name)``."""

    from transformers import (
        AutoConfig,
        AutoModelForCausalLM,
        AutoModelForImageTextToText,
    )

    model_config = AutoConfig.from_pretrained(
        config.model.id,
        revision=config.model.revision,
        trust_remote_code=config.model.trust_remote_code,
    )
    multimodal = _is_multimodal(model_config)
    auto_class = AutoModelForImageTextToText if multimodal else AutoModelForCausalLM
    class_name = "AutoModelForImageTextToText" if multimodal else "AutoModelForCausalLM"
    logger.info(
        "loading model",
        extra={
            "model_id": config.model.id,
            "auto_class": class_name,
            "architecture": getattr(model_config, "architectures", None),
            "for_training": for_training,
            "device": device,
        },
    )

    dtype = _DTYPE_MAP[config.model.dtype]
    if for_training and device == "cpu":
        # CPU training in reduced precision is not reliably supported across
        # kernels; use fp32 and measure before changing this.
        dtype = "float32"

    kwargs: dict[str, Any] = {
        "revision": config.model.revision,
        "trust_remote_code": config.model.trust_remote_code,
        "low_cpu_mem_usage": True,
        **_dtype_kwargs(dtype),
    }
    if config.model.attn_implementation != "auto":
        kwargs["attn_implementation"] = config.model.attn_implementation
    if config.quantization.enabled:
        from transformers import BitsAndBytesConfig

        if device != "cuda":
            raise RuntimeError(
                "bitsandbytes 4/8-bit loading requires CUDA in this pipeline; "
                "use GGUF/CPU quantization for CPU-only deployment (see scripts/quantize.py)."
            )
        kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=config.quantization.load_in_4bit,
            load_in_8bit=config.quantization.load_in_8bit,
            bnb_4bit_quant_type=config.quantization.bnb_4bit_quant_type,
            bnb_4bit_use_double_quant=config.quantization.bnb_4bit_use_double_quant,
            bnb_4bit_compute_dtype=_torch_dtype(config.quantization.bnb_4bit_compute_dtype),
        )
        if for_training:
            kwargs["device_map"] = {"": 0}
    elif not for_training and device == "cuda" and hardware.gpus:
        kwargs["device_map"] = "auto"
    if config.model.max_memory:
        kwargs["max_memory"] = config.model.max_memory

    model: Any
    try:
        model = auto_class.from_pretrained(config.model.id, **kwargs)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            f"failed to load {config.model.id} with {class_name}. Verify the installed "
            "transformers version supports this architecture (Qwen3.5 requires a recent "
            "transformers release; see docs/architecture.md). "
            f"Original error: {exc}"
        ) from exc

    if for_training:
        model.config.use_cache = config.model.use_cache
        if device != "cuda" and not config.quantization.enabled:
            model.to(device)

    tokenizer = load_tokenizer(config)
    return model, tokenizer, class_name


def _dtype_kwargs(dtype: str) -> dict[str, Any]:
    """Use the dtype keyword supported by the installed Transformers major."""

    import transformers

    major = int(transformers.__version__.split(".", 1)[0])
    return {"dtype": dtype} if major >= 5 else {"torch_dtype": dtype}


def _torch_dtype(name: str) -> Any:
    import torch

    return {
        "float32": torch.float32,
        "float16": torch.float16,
        "bfloat16": torch.bfloat16,
    }[name]


def freeze_vision_tower(model: Any) -> tuple[int, int]:
    """Freeze vision parameters; return (frozen_params, total_params)."""

    frozen = 0
    total = 0
    for name, parameter in model.named_parameters():
        total += parameter.numel()
        lowered = name.lower()
        if any(marker in lowered for marker in (".visual.", "vision_tower", ".vision_model.")):
            parameter.requires_grad_(False)
            frozen += parameter.numel()
    if frozen:
        logger.info(
            "vision tower frozen",
            extra={"frozen_parameters": frozen, "total_parameters": total},
        )
    return frozen, total


def count_parameters(model: Any) -> tuple[int, int]:
    total = sum(parameter.numel() for parameter in model.parameters())
    trainable = sum(
        parameter.numel() for parameter in model.parameters() if parameter.requires_grad
    )
    return total, trainable


def model_summary(model: Any) -> dict[str, Any]:
    config = getattr(model, "config", None)
    text_config = getattr(config, "text_config", config)
    return {
        "class": type(model).__name__,
        "parameters": count_parameters(model)[0],
        "hidden_size": getattr(text_config, "hidden_size", None),
        "layers": getattr(text_config, "num_hidden_layers", None),
        "vocab_size": getattr(text_config, "vocab_size", None),
        "dtype": str(getattr(model, "dtype", "unknown")),
        "multimodal": _is_multimodal(config) if config is not None else None,
    }

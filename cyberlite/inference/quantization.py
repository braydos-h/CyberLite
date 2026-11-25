"""Quantization backends and explicit export planning.

Bitsandbytes 4/8-bit is the validated GPU path used by QLoRA and inference.
GGUF export is delegated to llama.cpp and never installed automatically.
TorchAO and dynamic INT8 are documented as experimental because support varies
by model architecture and library version.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cyberlite.hardware import estimate_inference_memory_gb, estimate_weights_memory_gb
from cyberlite.logging_utils import configure_logging, get_logger

logger = get_logger(__name__)


@dataclass
class QuantizationPlan:
    model_id: str
    backend: str
    bits: int
    parameters_b: float
    estimated_weights_gb: float
    estimated_inference_gb: float
    supported_here: bool
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_plan(
    model_id: str, *, backend: str, bits: int, parameters_b: float = 0.8
) -> QuantizationPlan:
    notes: list[str] = []
    supported = True
    if backend == "bitsandbytes":
        try:
            import bitsandbytes  # noqa: F401
            import torch

            supported = torch.cuda.is_available()
            if not supported:
                notes.append("bitsandbytes requires a CUDA device in this pipeline.")
        except ImportError:
            supported = False
            notes.append("bitsandbytes is not installed (requirements-optional.txt).")
        if bits not in {4, 8}:
            raise ValueError("bitsandbytes supports 4-bit or 8-bit quantization")
    elif backend == "torchao":
        try:
            import torchao  # noqa: F401

            supported = True
        except ImportError:
            supported = False
            notes.append("torchao is not installed; install requirements-optional.txt.")
        if bits != 8:
            raise ValueError("this pipeline's torchao path supports int8 weight-only quantization")
        notes.append(
            "Experimental: verify reload and accuracy on the exact transformers/torchao versions."
        )
    elif backend == "gguf":
        notes.append(
            "GGUF conversion uses llama.cpp scripts. CyberLite does not download or build "
            "llama.cpp; pass --llama-cpp-dir to a local checkout."
        )
        supported = False
    elif backend == "dynamic-int8":
        notes.append(
            "Dynamic INT8 uses torch.ao quantization on Linear layers only. It is experimental "
            "for hybrid Qwen3.5 checkpoints and may not preserve quality or reload cleanly."
        )
        import torch

        supported = hasattr(torch.ao.quantization, "quantize_dynamic")
        if bits != 8:
            raise ValueError("dynamic INT8 supports 8-bit weights")
    else:
        raise ValueError(f"unknown backend: {backend}")
    inference = estimate_inference_memory_gb(
        parameters_b, bits=bits if bits in {4, 8} else 16, context_tokens=4096
    )
    return QuantizationPlan(
        model_id=model_id,
        backend=backend,
        bits=bits,
        parameters_b=parameters_b,
        estimated_weights_gb=estimate_weights_memory_gb(parameters_b, bits=bits),
        estimated_inference_gb=inference["estimated_peak_gb"],
        supported_here=supported,
        notes=notes,
    )


def _manifest(path: Path, plan: QuantizationPlan, model: Any | None) -> None:
    size = sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
    payload = {
        "created_at": datetime.now(tz=UTC).isoformat(),
        "plan": plan.to_dict(),
        "bytes_on_disk": size,
        "model_class": type(model).__name__ if model is not None else None,
        "note": "Quantization artifact; benchmark before deployment. No accuracy claim is implied.",
    }
    (path / "quantization_manifest.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )


def quantize_bitsandbytes(model_id: str, output: Path, *, bits: int) -> Any:
    import torch
    from transformers import (
        AutoConfig,
        AutoModelForCausalLM,
        AutoModelForImageTextToText,
        BitsAndBytesConfig,
    )

    if not torch.cuda.is_available():
        raise RuntimeError("bitsandbytes quantization requires CUDA")
    config = AutoConfig.from_pretrained(model_id)
    multimodal = hasattr(config, "vision_config") or any(
        "ConditionalGeneration" in str(arch) for arch in (config.architectures or [])
    )
    auto_class = AutoModelForImageTextToText if multimodal else AutoModelForCausalLM
    quantization = BitsAndBytesConfig(
        load_in_4bit=bits == 4,
        load_in_8bit=bits == 8,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
    )
    model = auto_class.from_pretrained(
        model_id,
        quantization_config=quantization,
        device_map="auto",
        dtype=torch.bfloat16,
    )
    model.save_pretrained(output, safe_serialization=True)
    return model


def quantize_torchao(model_id: str, output: Path) -> Any:
    import torch
    from transformers import AutoConfig, AutoModelForCausalLM, AutoModelForImageTextToText

    try:
        from torchao.quantization import Int8WeightOnlyConfig, quantize_
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("torchao is not installed") from exc
    config = AutoConfig.from_pretrained(model_id)
    multimodal = hasattr(config, "vision_config") or any(
        "ConditionalGeneration" in str(arch) for arch in (config.architectures or [])
    )
    auto_class = AutoModelForImageTextToText if multimodal else AutoModelForCausalLM
    model = auto_class.from_pretrained(model_id, dtype=torch.bfloat16, device_map="auto")
    quantize_(model, Int8WeightOnlyConfig())
    model.save_pretrained(output, safe_serialization=True)
    return model


def quantize_dynamic_int8(model_id: str, output: Path) -> Any:
    import torch
    from transformers import AutoConfig, AutoModelForCausalLM, AutoModelForImageTextToText

    config = AutoConfig.from_pretrained(model_id)
    multimodal = hasattr(config, "vision_config") or any(
        "ConditionalGeneration" in str(arch) for arch in (config.architectures or [])
    )
    auto_class = AutoModelForImageTextToText if multimodal else AutoModelForCausalLM
    model = auto_class.from_pretrained(model_id, dtype=torch.float32)
    model = torch.ao.quantization.quantize_dynamic(model, {torch.nn.Linear}, dtype=torch.qint8)
    # Quantized dynamic modules are not always reloadable with from_pretrained;
    # save both the state dict and a manifest so the limitation is explicit.
    torch.save(model.state_dict(), output / "pytorch_model_dynamic_int8.pt")
    (output / "README_QUANTIZED.txt").write_text(
        "Dynamic INT8 checkpoint. Reload requires constructing the base model and applying "
        "torch.ao.quantization.quantize_dynamic before loading the state dict. This backend is "
        "experimental for hybrid architectures; validate outputs against the fp32 baseline.\n",
        encoding="utf-8",
    )
    return model


def export_gguf(
    model_id: str,
    output: Path,
    *,
    llama_cpp_dir: str | None,
    quant_type: str = "Q4_K_M",
) -> dict[str, Any]:
    if not llama_cpp_dir:
        raise ValueError(
            "GGUF export requires --llama-cpp-dir pointing to a local llama.cpp checkout"
        )
    root = Path(llama_cpp_dir)
    converter = root / "convert_hf_to_gguf.py"
    quantizer = root / "build" / "bin" / "llama-quantize"
    if not converter.is_file():
        raise FileNotFoundError(f"converter not found: {converter}")
    if not quantizer.is_file():
        raise FileNotFoundError(
            f"llama-quantize not found: {quantizer}; build llama.cpp or place the binary there"
        )
    output.mkdir(parents=True, exist_ok=True)
    f16 = output / "model-f16.gguf"
    final = output / f"model-{quant_type.lower()}.gguf"
    subprocess.run(
        [sys.executable, str(converter), model_id, "--outfile", str(f16), "--outtype", "f16"],
        check=True,
    )
    subprocess.run([str(quantizer), str(f16), str(final), quant_type], check=True)
    f16.unlink(missing_ok=True)
    return {"output": str(final), "bytes": final.stat().st_size, "quant_type": quant_type}


def build_parser():
    import argparse

    parser = argparse.ArgumentParser(description="Quantize or export a CyberLite checkpoint.")
    parser.add_argument("--model", default="Qwen/Qwen3.5-0.8B")
    parser.add_argument("--output", default="models/cyberlite-quantized")
    parser.add_argument(
        "--backend",
        default="bitsandbytes",
        choices=["bitsandbytes", "torchao", "gguf", "dynamic-int8"],
    )
    parser.add_argument("--bits", type=int, default=4, choices=[4, 8])
    parser.add_argument("--parameters-b", type=float, default=0.8)
    parser.add_argument("--llama-cpp-dir", default=None)
    parser.add_argument("--quant-type", default="Q4_K_M")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json-logs", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(json_logs=args.json_logs)
    output = Path(args.output)
    try:
        plan = build_plan(
            args.model,
            backend=args.backend,
            bits=args.bits,
            parameters_b=args.parameters_b,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.dry_run:
        print(json.dumps(plan.to_dict(), indent=2))
        print("dry run complete; no model was loaded and no artifact was written")
        return 0
    output.mkdir(parents=True, exist_ok=True)
    try:
        if args.backend == "bitsandbytes":
            model = quantize_bitsandbytes(args.model, output, bits=args.bits)
        elif args.backend == "torchao":
            model = quantize_torchao(args.model, output)
        elif args.backend == "dynamic-int8":
            model = quantize_dynamic_int8(args.model, output)
        else:
            result = export_gguf(
                args.model,
                output,
                llama_cpp_dir=args.llama_cpp_dir,
                quant_type=args.quant_type,
            )
            print(json.dumps(result, indent=2))
            return 0
    except (RuntimeError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    _manifest(output, plan, model)
    print(f"quantized model written to {output}")
    print(json.dumps(plan.to_dict(), indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

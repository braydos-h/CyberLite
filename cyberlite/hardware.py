"""Hardware detection and planning estimates.

These estimates are intentionally conservative and are not a substitute for a
measured run. The training pipeline records measured peak VRAM and wall-clock
time alongside the estimate so that planning error can be quantified.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from cyberlite.logging_utils import get_logger

logger = get_logger(__name__)

GIB = 1024**3
TIERS_GB = (4, 6, 8, 12, 16)


@dataclass(frozen=True)
class GpuInfo:
    index: int
    name: str
    total_vram_gb: float
    backend: str = "cuda"
    compute_capability: str | None = None


@dataclass
class HardwareInfo:
    platform: str
    system: str
    release: str
    python_version: str
    cpu_count: int
    cpu_model: str
    ram_gb: float
    gpus: list[GpuInfo] = field(default_factory=list)
    mps_available: bool = False
    torch_version: str | None = None
    torch_cuda_version: str | None = None

    @property
    def cuda_available(self) -> bool:
        return any(gpu.backend == "cuda" for gpu in self.gpus)

    @property
    def max_vram_gb(self) -> float:
        return max((gpu.total_vram_gb for gpu in self.gpus), default=0.0)

    @property
    def recommended_device(self) -> str:
        if self.cuda_available:
            return "cuda"
        if self.mps_available:
            return "mps"
        return "cpu"

    @property
    def tier(self) -> str:
        if not self.gpus:
            return "cpu"
        vram = self.max_vram_gb
        supported = [tier for tier in TIERS_GB if vram + 0.5 >= tier]
        return f"{max(supported)}gb" if supported else "<4gb"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _cpu_model() -> str:
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        for line in cpuinfo.read_text(errors="ignore").splitlines():
            if line.lower().startswith("model name"):
                return line.split(":", 1)[1].strip()
    if sys.platform == "darwin":
        try:
            return subprocess.check_output(
                ["sysctl", "-n", "machdep.cpu.brand_string"], text=True, timeout=3
            ).strip()
        except (OSError, subprocess.SubprocessError):
            pass
    return platform.processor() or "unknown"


def _total_ram_gb() -> float:
    # Linux
    meminfo = Path("/proc/meminfo")
    if meminfo.is_file():
        for line in meminfo.read_text(errors="ignore").splitlines():
            if line.startswith("MemTotal:"):
                kib = float(line.split()[1])
                return round(kib / 1024**2, 2)
    # macOS
    if sys.platform == "darwin":
        try:
            bytes_total = int(
                subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True, timeout=3)
            )
            return round(bytes_total / GIB, 2)
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    # Windows
    if os.name == "nt":
        try:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(stat)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))  # type: ignore[attr-defined]
            return round(stat.ullTotalPhys / GIB, 2)
        except (AttributeError, OSError):
            pass
    return 0.0


def _nvidia_smi_gpus() -> list[GpuInfo]:
    if not shutil.which("nvidia-smi"):
        return []
    try:
        output = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    gpus: list[GpuInfo] = []
    for line in output.strip().splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 3:
            continue
        try:
            gpus.append(
                GpuInfo(
                    index=int(parts[0]),
                    name=parts[1],
                    total_vram_gb=round(float(parts[2]) / 1024, 2),
                    backend="cuda",
                )
            )
        except ValueError:
            continue
    return gpus


def detect_hardware() -> HardwareInfo:
    """Detect CPU, RAM, CUDA and Apple MPS capabilities."""

    gpus: list[GpuInfo] = []
    mps_available = False
    torch_version: str | None = None
    torch_cuda: str | None = None
    try:
        import torch

        torch_version = torch.__version__
        if torch.cuda.is_available():
            torch_cuda = torch.version.cuda
            for index in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(index)
                gpus.append(
                    GpuInfo(
                        index=index,
                        name=props.name,
                        total_vram_gb=round(props.total_memory / GIB, 2),
                        backend="cuda",
                        compute_capability=f"{props.major}.{props.minor}",
                    )
                )
        mps_available = bool(
            getattr(torch.backends, "mps", None) and torch.backends.mps.is_available()
        )
    except Exception as exc:  # pragma: no cover - torch is optional for this helper
        logger.debug("torch hardware probe failed", extra={"error": str(exc)})

    if not gpus:
        gpus = _nvidia_smi_gpus()

    return HardwareInfo(
        platform=platform.platform(),
        system=platform.system(),
        release=platform.release(),
        python_version=platform.python_version(),
        cpu_count=os.cpu_count() or 1,
        cpu_model=_cpu_model(),
        ram_gb=_total_ram_gb(),
        gpus=gpus,
        mps_available=mps_available,
        torch_version=torch_version,
        torch_cuda_version=torch_cuda,
    )


def recommend_tier(hardware: HardwareInfo) -> dict[str, Any]:
    """Return a coarse, documented recommendation for the detected hardware."""

    tier = hardware.tier
    notes: list[str] = []
    if tier == "cpu":
        notes.append("CPU-only: use 4-bit GGUF or a small quantized checkpoint for inference.")
        notes.append("CPU LoRA training is possible but slow; run a smoke test before scaling.")
        quantization = "gguf-q4 (inference); fp32/bf16 LoRA (training)"
        max_seq = 512
    elif tier in {"<4gb", "4gb"}:
        notes.append("4 GB class: QLoRA with short sequences; expect tight memory margins.")
        quantization = "4-bit QLoRA or GGUF q4"
        max_seq = 512
    elif tier == "6gb":
        notes.append("6 GB class: QLoRA is the recommended default.")
        quantization = "4-bit QLoRA or GGUF q4/q5"
        max_seq = 1024
    elif tier == "8gb":
        notes.append("8 GB class: QLoRA at 1024 tokens; LoRA may fit at very short sequences.")
        quantization = "4-bit QLoRA; GGUF q5/q8 inference"
        max_seq = 1024
    elif tier == "12gb":
        notes.append("12 GB class: QLoRA comfortable; bf16 LoRA feasible at short sequences.")
        quantization = "QLoRA training; bf16 or GGUF inference"
        max_seq = 2048
    else:
        notes.append("16 GB+ class: bf16 LoRA and larger control models become practical.")
        quantization = "bf16 LoRA; bf16/GGUF inference"
        max_seq = 4096
    return {
        "tier": tier,
        "recommended_device": hardware.recommended_device,
        "quantization": quantization,
        "suggested_max_seq_length": max_seq,
        "notes": notes,
    }


def estimate_weights_memory_gb(parameters_b: float, bits: int = 16) -> float:
    """Approximate weight memory in GiB (decimal parameter count)."""

    if parameters_b <= 0:
        raise ValueError("parameters_b must be positive")
    if bits not in {4, 8, 16, 32}:
        raise ValueError("bits must be one of 4, 8, 16, 32")
    return round(parameters_b * 1e9 * bits / 8 / GIB, 3)


def estimate_training_memory_gb(
    parameters_b: float,
    *,
    bits: int = 16,
    lora: bool = True,
    batch_size: int = 1,
    seq_length: int = 1024,
    gradient_checkpointing: bool = True,
    hidden_size: int = 1024,
    layers: int = 24,
) -> dict[str, float]:
    """Coarse planner for peak training memory.

    The activation term follows the usual ``batch * seq * hidden * layers``
    heuristic with a checkpointing discount. Real memory depends on attention
    kernels, allocator fragmentation, optimizer choice, and framework versions,
    so treat the output as a starting point and measure the real value.
    """

    weights = estimate_weights_memory_gb(parameters_b, bits)
    # LoRA adapters and their optimizer state are small relative to weights.
    adapter = max(0.05, parameters_b * 0.01) if lora else 0.0
    # 16 bytes/token/layer/feature is a deliberately conservative activation proxy
    # (forward + backward tensors); checkpointing trades compute for memory.
    activation_bytes = float(16 * batch_size * seq_length * hidden_size * layers)
    if gradient_checkpointing:
        activation_bytes *= 0.25
    activations = activation_bytes / GIB
    overhead = 0.75 + 0.10 * weights
    total = weights + adapter + activations + overhead
    return {
        "weights_gb": round(weights, 3),
        "adapters_and_optimizer_gb": round(adapter, 3),
        "activations_gb": round(activations, 3),
        "framework_overhead_gb": round(overhead, 3),
        "estimated_peak_gb": round(total, 3),
    }


def estimate_inference_memory_gb(
    parameters_b: float,
    *,
    bits: int = 16,
    context_tokens: int = 4096,
    kv_bytes_per_token: float = 16_384.0,
) -> dict[str, float]:
    """Coarse inference memory planner (weights + KV cache + overhead)."""

    weights = estimate_weights_memory_gb(parameters_b, bits)
    kv_cache = context_tokens * kv_bytes_per_token / GIB
    overhead = 0.5 + 0.05 * weights
    return {
        "weights_gb": round(weights, 3),
        "kv_cache_gb": round(kv_cache, 3),
        "framework_overhead_gb": round(overhead, 3),
        "estimated_peak_gb": round(weights + kv_cache + overhead, 3),
    }


def estimate_cost(
    duration_seconds: float,
    *,
    cost_per_hour_usd: float | None = None,
    watts: float | None = None,
    electricity_cost_per_kwh_usd: float | None = None,
) -> dict[str, Any]:
    """Estimate cost from explicit assumptions; never invents a price."""

    hours = max(0.0, duration_seconds) / 3600
    result: dict[str, Any] = {"duration_hours": round(hours, 4)}
    if cost_per_hour_usd is not None:
        result["compute_cost_usd"] = round(hours * cost_per_hour_usd, 4)
        result["compute_rate_usd_per_hour"] = cost_per_hour_usd
    if watts is not None and electricity_cost_per_kwh_usd is not None:
        kwh = hours * watts / 1000
        result["energy_kwh"] = round(kwh, 4)
        result["energy_cost_usd"] = round(kwh * electricity_cost_per_kwh_usd, 4)
        result["electricity_rate_usd_per_kwh"] = electricity_cost_per_kwh_usd
    if len(result) == 1:
        result["note"] = "no cost rates configured; cost not estimated"
    return result


def peak_memory_report() -> dict[str, Any]:
    """Read current and peak memory counters without requiring CUDA."""

    report: dict[str, Any] = {}
    try:
        import torch

        if torch.cuda.is_available():
            report["cuda_allocated_gb"] = round(torch.cuda.memory_allocated() / GIB, 3)
            report["cuda_reserved_gb"] = round(torch.cuda.memory_reserved() / GIB, 3)
            report["cuda_peak_allocated_gb"] = round(torch.cuda.max_memory_allocated() / GIB, 3)
            report["cuda_peak_reserved_gb"] = round(torch.cuda.max_memory_reserved() / GIB, 3)
        report["device"] = "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:  # pragma: no cover
        report["device"] = "unknown"
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Linux reports KiB, macOS reports bytes.
        report["process_peak_rss_gb"] = round(
            usage / GIB if sys.platform == "darwin" else usage / 1024**2, 3
        )
    except Exception:  # pragma: no cover - platform dependent
        pass
    return report


def reset_peak_memory() -> None:
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
    except Exception:  # pragma: no cover
        pass


def summary_lines(hardware: HardwareInfo) -> list[str]:
    lines = [
        f"Platform       : {hardware.system} {hardware.release}",
        f"CPU            : {hardware.cpu_model} ({hardware.cpu_count} threads)",
        f"RAM            : {hardware.ram_gb:.1f} GiB",
        f"PyTorch        : {hardware.torch_version or 'not installed'}",
        f"CUDA           : {hardware.torch_cuda_version or 'not available'}",
        f"Apple MPS      : {'available' if hardware.mps_available else 'not available'}",
    ]
    if hardware.gpus:
        for gpu in hardware.gpus:
            lines.append(
                f"GPU {gpu.index}          : {gpu.name} ({gpu.total_vram_gb:.1f} GiB VRAM)"
            )
    else:
        lines.append("GPU            : none detected")
    recommendation = recommend_tier(hardware)
    lines.append(f"Hardware tier  : {recommendation['tier']}")
    for note in recommendation["notes"]:
        lines.append(f"  - {note}")
    return lines


def main() -> int:
    """CLI entry point used by ``scripts/check_hardware.py``."""

    import argparse

    parser = argparse.ArgumentParser(description="Detect hardware and estimate model fit.")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--parameters-b", type=float, default=0.8, help="model size in billions")
    parser.add_argument("--bits", type=int, default=16, choices=[4, 8, 16, 32])
    parser.add_argument("--seq-length", type=int, default=1024)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--no-grad-checkpointing", action="store_true")
    args = parser.parse_args()

    hardware = detect_hardware()
    estimate = estimate_training_memory_gb(
        args.parameters_b,
        bits=args.bits,
        batch_size=args.batch_size,
        seq_length=args.seq_length,
        gradient_checkpointing=not args.no_grad_checkpointing,
    )
    payload = {
        "hardware": hardware.to_dict(),
        "recommendation": recommend_tier(hardware),
        "training_estimate": estimate,
        "inference_estimate": estimate_inference_memory_gb(args.parameters_b, bits=args.bits),
        "peak_memory": peak_memory_report(),
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print("\n".join(summary_lines(hardware)))
        print()
        print("Training memory estimate (conservative):")
        for key, value in estimate.items():
            print(f"  {key:28s} {value:.2f} GiB")
        print()
        print("These are planning estimates. Measure with scripts/train.py --estimate-only.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

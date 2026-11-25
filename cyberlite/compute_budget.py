"""Planning estimates for GPU compute and cost.

Every number produced here is an **estimate derived from explicit
assumptions**, never a measurement. The estimator exists so that a compute
request can be reproduced and challenged instead of asserted.

Model
-----
Training FLOPs use the standard approximation ``6 * N * D`` (forward plus
backward, dense-equivalent). LoRA/QLoRA still run the full forward and backward
pass through the frozen weights, so the approximation is appropriate for
budgeting; it does not model attention-kernel efficiency.

Wall-clock time is ``FLOPs / effective_TFLOPs``. ``effective_tflops`` is a
measured-throughput assumption supplied by the caller, not a datasheet peak.
Replace the default with a number from ``docs/gpu-bringup.md`` as soon as one
exists.

Token generation (distillation, evaluation) is memory-bandwidth bound, so it is
modelled from tokens/second rather than from FLOPs.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from cyberlite.config import ExperimentConfig, load_config

FLOPS_PER_PARAM_TOKEN = 6.0
SECONDS_PER_HOUR = 3600.0
TFLOP = 1e12

# Defaults are planning assumptions, not measurements. See docs/compute-budget.md.
DEFAULT_EFFECTIVE_TFLOPS = 30.0
# Notional amortised hardware rate: a ~$1,500 card over ~3,000 hours plus
# electricity. This is not a rental price and no cloud spend is assumed.
DEFAULT_GPU_HOUR_USD = 0.60
DEFAULT_CONTINGENCY = 0.30
DEFAULT_TRAIN_TOKENS = 30_000_000
DEFAULT_INFERENCE_TOKENS_PER_SECOND = 120.0
DEFAULT_TEACHER_TOKENS_PER_SECOND = 30.0


@dataclass(frozen=True)
class ComputeAssumptions:
    """Caller-supplied planning assumptions."""

    effective_tflops: float = DEFAULT_EFFECTIVE_TFLOPS
    gpu_hour_usd: float = DEFAULT_GPU_HOUR_USD
    contingency: float = DEFAULT_CONTINGENCY
    train_tokens_per_epoch: int = DEFAULT_TRAIN_TOKENS
    inference_tokens_per_second: float = DEFAULT_INFERENCE_TOKENS_PER_SECOND
    teacher_tokens_per_second: float = DEFAULT_TEACHER_TOKENS_PER_SECOND

    def __post_init__(self) -> None:
        if self.effective_tflops <= 0:
            raise ValueError("effective_tflops must be positive")
        if self.gpu_hour_usd < 0:
            raise ValueError("gpu_hour_usd cannot be negative")
        if not 0 <= self.contingency <= 5:
            raise ValueError("contingency must be between 0 and 5")
        if self.train_tokens_per_epoch < 0:
            raise ValueError("train_tokens_per_epoch cannot be negative")
        if self.inference_tokens_per_second <= 0:
            raise ValueError("inference_tokens_per_second must be positive")
        if self.teacher_tokens_per_second <= 0:
            raise ValueError("teacher_tokens_per_second must be positive")


@dataclass(frozen=True)
class TrainingEstimate:
    name: str
    config: str
    parameters_b: float
    epochs: float
    tokens_per_epoch: int
    total_tokens: int
    steps_per_epoch: int
    flops: float
    gpu_hours: float
    cost_usd: float


@dataclass
class ComputeReport:
    assumptions: ComputeAssumptions
    training: list[TrainingEstimate] = field(default_factory=list)
    distillation: dict[str, Any] | None = None
    evaluation: dict[str, Any] | None = None
    totals: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "assumptions": asdict(self.assumptions),
            "training": [asdict(row) for row in self.training],
            "distillation": self.distillation,
            "evaluation": self.evaluation,
            "totals": self.totals,
            "notes": self.notes,
        }


def training_flops(parameters_b: float, tokens: int | float) -> float:
    """Dense-equivalent forward+backward FLOPs for ``tokens`` tokens."""

    if parameters_b <= 0:
        raise ValueError("parameters_b must be positive")
    if tokens < 0:
        raise ValueError("tokens cannot be negative")
    return FLOPS_PER_PARAM_TOKEN * parameters_b * 1e9 * float(tokens)


def gpu_hours_from_flops(flops: float, effective_tflops: float) -> float:
    if effective_tflops <= 0:
        raise ValueError("effective_tflops must be positive")
    return flops / (effective_tflops * TFLOP * SECONDS_PER_HOUR)


def generation_gpu_hours(tokens: int | float, tokens_per_second: float) -> float:
    if tokens_per_second <= 0:
        raise ValueError("tokens_per_second must be positive")
    return float(tokens) / tokens_per_second / SECONDS_PER_HOUR


def estimate_training_run(
    config: ExperimentConfig,
    *,
    config_path: str,
    assumptions: ComputeAssumptions,
    epochs: float | None = None,
    parameters_b: float | None = None,
) -> TrainingEstimate:
    """Estimate one training configuration from its effective settings."""

    params = parameters_b or config.model.parameters_b
    if params is None:
        raise ValueError(
            f"{config_path}: set model.parameters_b or pass parameters_b to estimate compute"
        )
    run_epochs = float(epochs if epochs is not None else config.training.epochs)
    tokens_per_epoch = int(assumptions.train_tokens_per_epoch)
    total_tokens = round(tokens_per_epoch * run_epochs)
    flops = training_flops(params, total_tokens)
    hours = gpu_hours_from_flops(flops, assumptions.effective_tflops)
    tokens_per_step = (
        config.training.per_device_batch_size
        * config.training.gradient_accumulation_steps
        * config.training.max_seq_length
    )
    steps_per_epoch = tokens_per_epoch // tokens_per_step if tokens_per_step else 0
    return TrainingEstimate(
        name=config.run.name,
        config=config_path,
        parameters_b=float(params),
        epochs=run_epochs,
        tokens_per_epoch=tokens_per_epoch,
        total_tokens=total_tokens,
        steps_per_epoch=steps_per_epoch,
        flops=flops,
        gpu_hours=round(hours, 2),
        cost_usd=round(hours * assumptions.gpu_hour_usd, 2),
    )


def estimate_distillation(
    *,
    teacher_parameters_b: float,
    generated_tokens: int,
    assumptions: ComputeAssumptions,
) -> dict[str, Any]:
    """Estimate teacher generation time for offline distillation."""

    hours = generation_gpu_hours(generated_tokens, assumptions.teacher_tokens_per_second)
    return {
        "teacher_parameters_b": teacher_parameters_b,
        "generated_tokens": generated_tokens,
        "tokens_per_second": assumptions.teacher_tokens_per_second,
        "gpu_hours": round(hours, 2),
        "cost_usd": round(hours * assumptions.gpu_hour_usd, 2),
    }


def estimate_evaluation(
    *,
    conditions: int,
    items_per_condition: int,
    tokens_per_item: int,
    assumptions: ComputeAssumptions,
) -> dict[str, Any]:
    """Estimate evaluation inference time for the experimental matrix."""

    total_tokens = conditions * items_per_condition * tokens_per_item
    hours = generation_gpu_hours(total_tokens, assumptions.inference_tokens_per_second)
    return {
        "conditions": conditions,
        "items_per_condition": items_per_condition,
        "tokens_per_item": tokens_per_item,
        "total_tokens": total_tokens,
        "tokens_per_second": assumptions.inference_tokens_per_second,
        "gpu_hours": round(hours, 2),
        "cost_usd": round(hours * assumptions.gpu_hour_usd, 2),
    }


def build_report(
    config_paths: list[str | Path],
    *,
    assumptions: ComputeAssumptions | None = None,
    epochs: float | None = None,
    parameters_b: float | None = None,
    distillation_tokens: int = 0,
    teacher_parameters_b: float = 4.0,
    eval_conditions: int = 0,
    eval_items: int = 4000,
    eval_tokens_per_item: int = 200,
) -> ComputeReport:
    """Build a planning report for a list of training configurations."""

    active = assumptions or ComputeAssumptions()
    report = ComputeReport(assumptions=active)

    for path in config_paths:
        config = load_config(path)
        report.training.append(
            estimate_training_run(
                config,
                config_path=str(path),
                assumptions=active,
                epochs=epochs,
                parameters_b=parameters_b,
            )
        )

    if distillation_tokens > 0:
        report.distillation = estimate_distillation(
            teacher_parameters_b=teacher_parameters_b,
            generated_tokens=distillation_tokens,
            assumptions=active,
        )

    if eval_conditions > 0:
        report.evaluation = estimate_evaluation(
            conditions=eval_conditions,
            items_per_condition=eval_items,
            tokens_per_item=eval_tokens_per_item,
            assumptions=active,
        )

    base_hours = sum(row.gpu_hours for row in report.training)
    if report.distillation:
        base_hours += float(report.distillation["gpu_hours"])
    if report.evaluation:
        base_hours += float(report.evaluation["gpu_hours"])
    contingency_hours = base_hours * active.contingency
    total_hours = base_hours + contingency_hours

    report.totals = {
        "base_gpu_hours": round(base_hours, 2),
        "contingency_gpu_hours": round(contingency_hours, 2),
        "total_gpu_hours": round(total_hours, 2),
        "base_cost_usd": round(base_hours * active.gpu_hour_usd, 2),
        "contingency_cost_usd": round(contingency_hours * active.gpu_hour_usd, 2),
        "total_cost_usd": round(total_hours * active.gpu_hour_usd, 2),
    }
    report.notes = [
        "All values are planning estimates derived from the stated assumptions.",
        "training FLOPs use 6*N*D; LoRA/QLoRA do not reduce the forward/backward pass.",
        "Replace effective_tflops with a measured value from docs/gpu-bringup.md before quoting.",
        "The dollar column is a notional amortised hardware rate, not a cloud or rental price.",
        "Distillation and evaluation are modelled from tokens/second, not FLOPs.",
        "Hardware purchase, electricity, storage, and human review time are excluded.",
    ]
    return report


def render_markdown(report: ComputeReport) -> str:
    """Render a report as a Markdown fragment suitable for the docs."""

    a = report.assumptions
    lines = [
        "### Assumptions",
        "",
        "| Assumption | Value |",
        "|---|---:|",
        f"| Effective training throughput | {a.effective_tflops:g} TFLOP/s |",
        f"| Training tokens per epoch | {a.train_tokens_per_epoch:,} |",
        f"| Notional GPU-hour rate | ${a.gpu_hour_usd:.2f}/GPU-hour |",
        f"| Inference throughput | {a.inference_tokens_per_second:g} tokens/s |",
        f"| Teacher generation throughput | {a.teacher_tokens_per_second:g} tokens/s |",
        f"| Contingency | {a.contingency:.0%} |",
        "",
        "### Training runs",
        "",
        "| Run | Config | Params (B) | Epochs | Total tokens | Steps/epoch | GPU-hours | Cost (USD) |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report.training:
        lines.append(
            f"| {row.name} | `{row.config}` | {row.parameters_b:g} | {row.epochs:g} | "
            f"{row.total_tokens:,} | {row.steps_per_epoch:,} | {row.gpu_hours:.2f} | "
            f"${row.cost_usd:,.2f} |"
        )
    if report.distillation:
        d = report.distillation
        lines += [
            "",
            "### Distillation generation",
            "",
            "| Item | Value |",
            "|---|---:|",
            f"| Teacher parameters | {d['teacher_parameters_b']:g} B |",
            f"| Generated tokens | {d['generated_tokens']:,} |",
            f"| Teacher throughput | {d['tokens_per_second']:g} tokens/s |",
            f"| GPU-hours | {d['gpu_hours']:.2f} |",
            f"| Cost (USD) | ${d['cost_usd']:,.2f} |",
        ]
    if report.evaluation:
        e = report.evaluation
        lines += [
            "",
            "### Evaluation",
            "",
            "| Item | Value |",
            "|---|---:|",
            f"| Conditions | {e['conditions']} |",
            f"| Items per condition | {e['items_per_condition']:,} |",
            f"| Tokens per item | {e['tokens_per_item']:,} |",
            f"| Total generated tokens | {e['total_tokens']:,} |",
            f"| GPU-hours | {e['gpu_hours']:.2f} |",
            f"| Cost (USD) | ${e['cost_usd']:,.2f} |",
        ]
    t = report.totals
    lines += [
        "",
        "### Totals",
        "",
        "| Item | GPU-hours | Cost (USD) |",
        "|---|---:|---:|",
        f"| Base | {t['base_gpu_hours']:.2f} | ${t['base_cost_usd']:,.2f} |",
        f"| Contingency | {t['contingency_gpu_hours']:.2f} | ${t['contingency_cost_usd']:,.2f} |",
        f"| **Total** | **{t['total_gpu_hours']:.2f}** | **${t['total_cost_usd']:,.2f}** |",
        "",
        "### Notes",
        "",
    ]
    lines += [f"- {note}" for note in report.notes]
    return "\n".join(lines) + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Estimate GPU-hours and cost for a CyberLite experiment matrix."
    )
    parser.add_argument(
        "--config",
        action="append",
        default=[],
        help="training configuration to include; repeat for each run (default: configs/lora.yaml)",
    )
    parser.add_argument("--train-tokens", type=int, default=DEFAULT_TRAIN_TOKENS)
    parser.add_argument("--epochs", type=float, default=None, help="override config epochs")
    parser.add_argument(
        "--parameters-b",
        type=float,
        default=None,
        help="override model.parameters_b, for planning a hypothetical control model",
    )
    parser.add_argument("--effective-tflops", type=float, default=DEFAULT_EFFECTIVE_TFLOPS)
    parser.add_argument(
        "--gpu-hour-usd",
        type=float,
        default=DEFAULT_GPU_HOUR_USD,
        help="notional amortised hardware rate, not a rental price",
    )
    parser.add_argument("--contingency", type=float, default=DEFAULT_CONTINGENCY)
    parser.add_argument(
        "--inference-tokens-per-second",
        type=float,
        default=DEFAULT_INFERENCE_TOKENS_PER_SECOND,
    )
    parser.add_argument(
        "--teacher-tokens-per-second",
        type=float,
        default=DEFAULT_TEACHER_TOKENS_PER_SECOND,
    )
    parser.add_argument("--distill-tokens", type=int, default=0)
    parser.add_argument("--teacher-params-b", type=float, default=4.0)
    parser.add_argument("--eval-conditions", type=int, default=0)
    parser.add_argument("--eval-items", type=int, default=4000)
    parser.add_argument("--eval-tokens-per-item", type=int, default=200)
    parser.add_argument("--markdown", action="store_true", help="render Markdown instead of JSON")
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable JSON (the default; kept for symmetry)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    configs = args.config or ["configs/lora.yaml"]
    report = build_report(
        configs,
        assumptions=ComputeAssumptions(
            effective_tflops=args.effective_tflops,
            gpu_hour_usd=args.gpu_hour_usd,
            contingency=args.contingency,
            train_tokens_per_epoch=args.train_tokens,
            inference_tokens_per_second=args.inference_tokens_per_second,
            teacher_tokens_per_second=args.teacher_tokens_per_second,
        ),
        epochs=args.epochs,
        parameters_b=args.parameters_b,
        distillation_tokens=args.distill_tokens,
        teacher_parameters_b=args.teacher_params_b,
        eval_conditions=args.eval_conditions,
        eval_items=args.eval_items,
        eval_tokens_per_item=args.eval_tokens_per_item,
    )
    if args.markdown:
        print(render_markdown(report), end="")
    else:
        print(json.dumps(report.to_dict(), indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

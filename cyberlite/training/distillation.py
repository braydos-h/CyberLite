"""Offline sequence-level knowledge distillation from a local teacher model.

The teacher runs locally; no paid API is required. Generated responses are
filtered, deduplicated, redacted, and then passed through the standard dataset
preparation pipeline before they can be used for student training.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cyberlite.data.cleaning import Deduplicator, normalize_text, redact_secrets
from cyberlite.logging_utils import get_logger
from cyberlite.training.dataset import render_chat

logger = get_logger(__name__)


@dataclass
class DistillationStats:
    prompts: int
    generated: int
    kept: int
    rejected_short: int
    rejected_duplicate: int

    def to_dict(self) -> dict[str, int]:
        return {
            "prompts": self.prompts,
            "generated": self.generated,
            "kept": self.kept,
            "rejected_short": self.rejected_short,
            "rejected_duplicate": self.rejected_duplicate,
        }


def load_prompts(path: str | Path) -> list[dict[str, Any]]:
    prompts: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(f"{path}:{line_number}: prompt must be an object")
            if not payload.get("prompt") and not payload.get("messages"):
                raise ValueError(f"{path}:{line_number}: prompt or messages is required")
            prompts.append(payload)
    if not prompts:
        raise ValueError(f"no prompts found in {path}")
    return prompts


def generate_distillation_data(
    *,
    engine: Any,
    prompts: list[dict[str, Any]],
    output_file: str | Path,
    max_new_tokens: int = 768,
    temperature: float = 0.8,
    top_p: float = 0.95,
    min_response_chars: int = 80,
    seed: int = 42,
) -> DistillationStats:
    from cyberlite.inference.engine import GenerationSettings

    deduplicator = Deduplicator(threshold=3)
    stats = DistillationStats(
        prompts=len(prompts), generated=0, kept=0, rejected_short=0, rejected_duplicate=0
    )
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for index, item in enumerate(prompts):
            if item.get("messages"):
                prompt_text = render_chat(
                    engine.tokenizer, item["messages"], add_generation_prompt=True
                )
            else:
                prompt_text = str(item["prompt"])
            settings = GenerationSettings(
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                top_p=top_p,
                seed=seed + index,
            )
            result = engine.complete(prompt_text, settings)
            stats.generated += 1
            response = normalize_text(result.text)
            response, _ = redact_secrets(response)
            if len(response) < min_response_chars:
                stats.rejected_short += 1
                continue
            duplicate, _ = deduplicator.is_duplicate(response)
            if duplicate:
                stats.rejected_duplicate += 1
                continue
            record = {
                "id": f"distill-{index:06d}",
                "source": "teacher-distillation",
                "license": "Synthetic",
                "task": "distillation",
                "prompt": prompt_text,
                "response": response,
                "metadata": {
                    "teacher_model": getattr(engine, "model_id", "unknown"),
                    "prompt_id": item.get("id"),
                    "seed": seed + index,
                    "temperature": temperature,
                    "note": "Teacher-generated; verify teacher model license before redistribution.",
                },
            }
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            stats.kept += 1
            if index % 20 == 0:
                logger.info(
                    "distillation progress",
                    extra={"completed": index + 1, "total": len(prompts), "kept": stats.kept},
                )
    logger.info("distillation generated", extra=stats.to_dict())
    return stats


def build_parser():
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate offline distillation data from a local teacher model."
    )
    parser.add_argument("--teacher", required=True, help="teacher model ID or local path")
    parser.add_argument("--prompts", required=True, help="JSONL prompts")
    parser.add_argument("--output", required=True)
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda", "mps"])
    parser.add_argument(
        "--dtype", default="auto", choices=["auto", "float32", "float16", "bfloat16"]
    )
    parser.add_argument("--load-in-4bit", action="store_true")
    parser.add_argument("--max-new-tokens", type=int, default=768)
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--top-p", type=float, default=0.95)
    parser.add_argument("--min-response-chars", type=int, default=80)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--json-logs", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    from cyberlite.hardware import detect_hardware
    from cyberlite.inference.engine import InferenceEngine
    from cyberlite.logging_utils import configure_logging

    args = build_parser().parse_args(argv)
    configure_logging(json_logs=args.json_logs)
    try:
        prompts = load_prompts(args.prompts)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    hardware = detect_hardware()
    if args.device == "auto" and not hardware.cuda_available and args.load_in_4bit:
        print("error: --load-in-4bit requires CUDA in this pipeline", file=sys.stderr)
        return 2
    try:
        engine = InferenceEngine(
            args.teacher,
            device=args.device,
            dtype=args.dtype,
            load_in_4bit=args.load_in_4bit,
        )
        stats = generate_distillation_data(
            engine=engine,
            prompts=prompts,
            output_file=args.output,
            max_new_tokens=args.max_new_tokens,
            temperature=args.temperature,
            top_p=args.top_p,
            min_response_chars=args.min_response_chars,
            seed=args.seed,
        )
    except (RuntimeError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(stats.to_dict(), indent=2))
    print(f"distillation data written to {args.output}")
    print(
        "Next: prepare_dataset.py --source teacher-distillation --input "
        f"{args.output} --out data/processed/distill"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

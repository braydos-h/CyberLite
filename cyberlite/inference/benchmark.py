"""Inference benchmark with explicit measurement definitions."""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cyberlite.hardware import detect_hardware, estimate_cost, peak_memory_report
from cyberlite.inference.engine import GenerationSettings, InferenceEngine
from cyberlite.logging_utils import configure_logging, get_logger
from cyberlite.repro import environment_snapshot, write_json

logger = get_logger(__name__)


def _prompt_for_length(target_tokens: int, tokenizer: Any) -> str:
    """Build a deterministic synthetic prompt near a target token length."""

    block = (
        "A defender reviews authentication logs for unusual login patterns and documents "
        "verification steps before escalating an incident. "
    )
    text = ""
    while len(tokenizer(text, add_special_tokens=False)["input_ids"]) < target_tokens:
        text += block
    encoded = tokenizer(text, add_special_tokens=False)["input_ids"]
    return tokenizer.decode(encoded[:target_tokens])


def benchmark_engine(
    engine: InferenceEngine,
    *,
    prompt_lengths: list[int],
    max_new_tokens: int,
    runs: int,
    temperature: float = 0.0,
    cost_per_hour_usd: float | None = None,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for prompt_length in prompt_lengths:
        prompt = _prompt_for_length(prompt_length, engine.tokenizer)
        actual_prompt_tokens = len(engine.tokenizer(prompt, add_special_tokens=False)["input_ids"])
        for run in range(runs):
            settings = GenerationSettings(
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                seed=42 + run,
            )
            start = time.perf_counter()
            first_chunk_at: float | None = None
            chunks: list[str] = []
            try:
                for chunk in engine.stream(prompt, settings):
                    if first_chunk_at is None:
                        first_chunk_at = time.perf_counter() - start
                    chunks.append(chunk)
            except Exception as exc:  # pragma: no cover - runtime dependent
                raise RuntimeError(f"streaming benchmark failed: {exc}") from exc
            total = time.perf_counter() - start
            text = "".join(chunks)
            generated_tokens = len(engine.tokenizer(text, add_special_tokens=False)["input_ids"])
            results.append(
                {
                    "prompt_tokens": actual_prompt_tokens,
                    "run": run,
                    "ttft_seconds": round(first_chunk_at or 0.0, 4),
                    "total_latency_seconds": round(total, 4),
                    "generated_tokens": generated_tokens,
                    "tokens_per_second": round(generated_tokens / total, 2) if total > 0 else 0.0,
                    "peak_memory": peak_memory_report(),
                }
            )
            logger.info(
                "benchmark run",
                extra={
                    "prompt_tokens": actual_prompt_tokens,
                    "run": run,
                    "tps": results[-1]["tokens_per_second"],
                },
            )
    grouped: dict[str, Any] = {}
    for item in results:
        grouped.setdefault(str(item["prompt_tokens"]), []).append(item)
    summary_by_prompt = {
        prompt_tokens: {
            "runs": len(items),
            "ttft_seconds_mean": round(statistics.fmean(item["ttft_seconds"] for item in items), 4),
            "tokens_per_second_mean": round(
                statistics.fmean(item["tokens_per_second"] for item in items), 2
            ),
            "tokens_per_second_stdev": round(
                statistics.pstdev([item["tokens_per_second"] for item in items]), 2
            )
            if len(items) > 1
            else 0.0,
            "total_latency_seconds_mean": round(
                statistics.fmean(item["total_latency_seconds"] for item in items), 4
            ),
            "peak_vram_allocated_gb": max(
                item["peak_memory"].get("cuda_peak_allocated_gb", 0.0) for item in items
            ),
            "process_peak_rss_gb": max(
                item["peak_memory"].get("process_peak_rss_gb", 0.0) for item in items
            ),
        }
        for prompt_tokens, items in grouped.items()
    }
    total_generated = sum(item["generated_tokens"] for item in results)
    total_seconds = sum(item["total_latency_seconds"] for item in results)
    payload = {
        "created_at": datetime.now(tz=UTC).isoformat(),
        "model": engine.info(),
        "definition": {
            "ttft_seconds": "time from generation start to the first decoded stream chunk",
            "tokens_per_second": "tokenizer tokens in generated text divided by total wall time",
            "note": "Synthetic prompts; results are hardware- and version-specific.",
        },
        "config": {
            "prompt_lengths": prompt_lengths,
            "max_new_tokens": max_new_tokens,
            "runs": runs,
            "temperature": temperature,
        },
        "results": results,
        "summary_by_prompt_tokens": summary_by_prompt,
        "aggregate": {
            "tokens_per_second": round(total_generated / total_seconds, 2)
            if total_seconds > 0
            else 0.0,
            "generated_tokens": total_generated,
            "cost": estimate_cost(total_seconds, cost_per_hour_usd=cost_per_hour_usd),
        },
        "hardware": detect_hardware().to_dict(),
        "environment": environment_snapshot(),
        "platform": platform.platform(),
    }
    return payload


def build_parser():
    parser = argparse.ArgumentParser(description="Benchmark local CyberLite inference.")
    parser.add_argument("--model", default="Qwen/Qwen3.5-0.8B")
    parser.add_argument("--adapter", default=None)
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda", "mps"])
    parser.add_argument(
        "--dtype", default="auto", choices=["auto", "float32", "float16", "bfloat16"]
    )
    parser.add_argument("--load-in-4bit", action="store_true")
    parser.add_argument("--prompt-lengths", default="128,512")
    parser.add_argument("--max-new-tokens", type=int, default=64)
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--out", default=None)
    parser.add_argument("--cost-per-hour-usd", type=float, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json-logs", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(json_logs=args.json_logs)
    try:
        prompt_lengths = [int(item) for item in args.prompt_lengths.split(",") if item.strip()]
    except ValueError:
        print("error: --prompt-lengths must be comma-separated integers", file=sys.stderr)
        return 2
    if not prompt_lengths or any(length < 8 for length in prompt_lengths):
        print("error: prompt lengths must be >= 8", file=sys.stderr)
        return 2
    if args.max_new_tokens < 1 or args.runs < 1:
        print("error: --max-new-tokens and --runs must be positive", file=sys.stderr)
        return 2
    if args.dry_run:
        print(
            json.dumps(
                {
                    "model": args.model,
                    "prompt_lengths": prompt_lengths,
                    "max_new_tokens": args.max_new_tokens,
                    "runs": args.runs,
                    "dry_run": True,
                },
                indent=2,
            )
        )
        return 0
    try:
        engine = InferenceEngine(
            args.model,
            adapter_path=args.adapter,
            device=args.device,
            dtype=args.dtype,
            load_in_4bit=args.load_in_4bit,
        )
    except (RuntimeError, OSError, ValueError) as exc:
        print(f"error: could not load model: {exc}", file=sys.stderr)
        return 2
    payload = benchmark_engine(
        engine,
        prompt_lengths=prompt_lengths,
        max_new_tokens=args.max_new_tokens,
        runs=args.runs,
        temperature=args.temperature,
        cost_per_hour_usd=args.cost_per_hour_usd,
    )
    out = (
        Path(args.out)
        if args.out
        else Path(
            f"results/benchmarks/inference-{datetime.now(tz=UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
        )
    )
    write_json(out, payload)
    print(f"benchmark written to {out}")
    print(json.dumps(payload["summary_by_prompt_tokens"], indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

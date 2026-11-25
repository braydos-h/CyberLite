"""Reproducible evaluation harness over local JSONL task files.

Supported tasks: ``mcq``, ``classification``, ``generation``, ``completion``.
The harness records predictions, metrics, latency, memory, dataset hashes, and
environment metadata. It does not download benchmarks and does not execute
generated code.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cyberlite import __version__
from cyberlite.autocomplete.engine import AutocompleteEngine
from cyberlite.evaluation import metrics
from cyberlite.evaluation.benchmarks import list_benchmarks
from cyberlite.hardware import detect_hardware, estimate_cost, peak_memory_report
from cyberlite.inference.engine import GenerationSettings, InferenceEngine
from cyberlite.logging_utils import configure_logging, get_logger
from cyberlite.repro import environment_snapshot, sha256_json, write_json

logger = get_logger(__name__)

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
TASK_ALIASES = {
    "mcq": "mcq",
    "multiple_choice": "mcq",
    "multiple-choice": "mcq",
    "classification": "classification",
    "vulnerability_classification": "classification",
    "generation": "generation",
    "qa": "generation",
    "completion": "completion",
    "secure_code_completion": "completion",
    "autocomplete": "completion",
}
SYSTEM_PROMPT = (
    "You are CyberLite, a defensive cybersecurity research assistant. Be technically precise, "
    "state uncertainty, and never claim to have executed commands or accessed systems."
)


@dataclass
class EvalExample:
    id: str
    task: str
    source: str = "local"
    question: str | None = None
    choices: list[str] = field(default_factory=list)
    answer_index: int | None = None
    text: str | None = None
    label: str | None = None
    labels: list[str] = field(default_factory=list)
    prompt: str | None = None
    reference: str | None = None
    prefix: str | None = None
    suffix: str = ""
    language: str = "python"
    evidence: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> EvalExample:
        if not isinstance(payload, dict):
            raise ValueError("evaluation example must be an object")
        raw_task = str(payload.get("task", "")).lower()
        if raw_task not in TASK_ALIASES:
            raise ValueError(f"unsupported task {raw_task!r}")
        task = TASK_ALIASES[raw_task]
        identifier = str(payload.get("id") or "")
        if not identifier:
            identifier = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[
                :16
            ]
        source = str(payload.get("source", "local"))
        metadata = dict(payload.get("metadata", {}))
        if task == "mcq":
            question = str(payload.get("question", "")).strip()
            choices = payload.get("choices")
            if not question or not isinstance(choices, list) or len(choices) < 2:
                raise ValueError(f"{identifier}: mcq requires question and >=2 choices")
            choices = [str(choice) for choice in choices]
            answer = payload.get("answer", payload.get("answer_index"))
            answer_index = _resolve_answer(answer, choices)
            return cls(
                id=identifier,
                task=task,
                source=source,
                question=question,
                choices=choices,
                answer_index=answer_index,
                metadata=metadata,
            )
        if task == "classification":
            text = str(payload.get("text", "")).strip()
            label = str(payload.get("label", "")).strip()
            labels = [str(item) for item in payload.get("labels", [])]
            if not text or not label or len(labels) < 2:
                raise ValueError(f"{identifier}: classification requires text, label, labels")
            if label not in labels:
                raise ValueError(f"{identifier}: label {label!r} not present in labels")
            return cls(
                id=identifier,
                task=task,
                source=source,
                text=text,
                label=label,
                labels=labels,
                metadata=metadata,
            )
        if task == "generation":
            prompt = str(payload.get("prompt", payload.get("question", ""))).strip()
            reference = str(payload.get("reference", payload.get("answer", ""))).strip()
            if not prompt or not reference:
                raise ValueError(f"{identifier}: generation requires prompt and reference")
            return cls(
                id=identifier,
                task=task,
                source=source,
                prompt=prompt,
                reference=reference,
                evidence=payload.get("evidence"),
                metadata=metadata,
            )
        completion_prefix = payload.get("prefix")
        completion_reference = payload.get("reference", payload.get("middle"))
        if (
            not isinstance(completion_prefix, str)
            or not isinstance(completion_reference, str)
            or not completion_reference
        ):
            raise ValueError(f"{identifier}: completion requires prefix and reference")
        return cls(
            id=identifier,
            task=task,
            source=source,
            prefix=completion_prefix,
            suffix=str(payload.get("suffix", "")),
            reference=completion_reference,
            language=str(payload.get("language", "python")),
            metadata=metadata,
        )


def _resolve_answer(answer: Any, choices: Sequence[str]) -> int:
    if isinstance(answer, int):
        if 0 <= answer < len(choices):
            return answer
        raise ValueError(f"answer index {answer} out of range")
    if isinstance(answer, str):
        stripped = answer.strip()
        if stripped.upper() in LETTERS[: len(choices)] and len(stripped) == 1:
            return LETTERS.index(stripped.upper())
        normalized = metrics.normalize_answer(stripped)
        for index, choice in enumerate(choices):
            if normalized == metrics.normalize_answer(choice):
                return index
        if stripped.isdigit() and 0 <= int(stripped) < len(choices):
            return int(stripped)
    raise ValueError(f"could not resolve answer {answer!r}")


def load_examples(path: str | Path, *, limit: int | None = None) -> list[EvalExample]:
    examples: list[EvalExample] = []
    seen: set[str] = set()
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                example = EvalExample.from_dict(payload)
            except (json.JSONDecodeError, ValueError) as exc:
                raise ValueError(f"{path}:{line_number}: {exc}") from exc
            if example.id in seen:
                raise ValueError(f"{path}:{line_number}: duplicate id {example.id!r}")
            seen.add(example.id)
            examples.append(example)
            if limit is not None and len(examples) >= limit:
                break
    if not examples:
        raise ValueError(f"no evaluation examples found in {path}")
    return examples


def _mcq_prompt(example: EvalExample) -> str:
    choices = "\n".join(
        f"{LETTERS[index]}. {choice}" for index, choice in enumerate(example.choices)
    )
    return (
        f"Question:\n{example.question}\n\nChoices:\n{choices}\n\n"
        "Answer with only the letter of the correct choice."
    )


def _classification_prompt(example: EvalExample) -> str:
    labels = ", ".join(example.labels)
    return (
        f"Classify the following security-relevant text.\n\nValid labels: {labels}\n\n"
        f"Text:\n{example.text}\n\nAnswer with exactly one valid label."
    )


def build_prompt(example: EvalExample) -> str:
    if example.task == "mcq":
        return _mcq_prompt(example)
    if example.task == "classification":
        return _classification_prompt(example)
    if example.task == "generation":
        return example.prompt or ""
    if example.task == "completion":
        return example.prefix or ""
    raise ValueError(f"unsupported task: {example.task}")


def _messages(example: EvalExample) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_prompt(example)},
    ]


def parse_classification(text: str, labels: Sequence[str]) -> str | None:
    normalized = metrics.normalize_answer(text)
    for label in sorted(labels, key=len, reverse=True):
        if normalized == metrics.normalize_answer(label):
            return label
    pattern = re.compile(r"\b(?:label|classification|answer)\s*[:\-]\s*([^\n,.;]+)", re.I)
    match = pattern.search(text)
    if match:
        candidate = metrics.normalize_answer(match.group(1))
        for label in labels:
            if candidate == metrics.normalize_answer(label):
                return label
    # Last resort: first label mentioned in the output.
    positions = [
        (text.lower().find(label.lower()), label)
        for label in labels
        if label.lower() in text.lower()
    ]
    if positions:
        positions.sort()
        return positions[0][1]
    return None


def _task_max_tokens(task: str) -> int:
    return {"mcq": 32, "classification": 32, "generation": 512, "completion": 128}[task]


def _prompt_style(requested: str, model_id: str) -> str:
    if requested != "auto":
        return requested
    lowered = model_id.lower()
    return "raw" if lowered.rstrip("/").endswith("-base") else "chat"


@dataclass
class EvaluationHarness:
    engine: Any
    examples: list[EvalExample]
    seed: int = 42
    temperature: float = 0.0
    prompt_style: str = "chat"
    max_new_tokens: int | None = None
    positive_label: str | None = None
    cost_per_hour_usd: float | None = None

    def __post_init__(self) -> None:
        self.autocomplete = (
            AutocompleteEngine(self.engine) if hasattr(self.engine, "tokenizer") else None
        )
        self.predictions: list[dict[str, Any]] = []
        self.peak_memory: dict[str, Any] = {}

    def _generate(self, example: EvalExample, index: int) -> tuple[str, dict[str, Any]]:
        max_tokens = self.max_new_tokens or _task_max_tokens(example.task)
        if example.task == "completion":
            if self.autocomplete is None:
                raise RuntimeError("completion evaluation requires an inference engine tokenizer")
            result = self.autocomplete.complete(
                example.prefix or "",
                suffix=example.suffix,
                language=example.language,
                max_new_tokens=max_tokens,
                temperature=max(self.temperature, 0.0),
            )
            return result.completion, {
                "latency_seconds": result.latency_seconds,
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "mode": result.mode,
            }
        settings = GenerationSettings(
            max_new_tokens=max_tokens,
            temperature=max(self.temperature, 0.0),
            seed=self.seed + index,
        )
        if self.prompt_style == "chat":
            try:
                result = self.engine.chat(_messages(example), settings)
            except (TypeError, ValueError):
                result = self.engine.complete(build_prompt(example), settings)
        else:
            result = self.engine.complete(build_prompt(example), settings)
        return result.text, {
            "latency_seconds": result.latency_seconds,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "mode": self.prompt_style,
        }

    def _score(self, example: EvalExample, output: str) -> dict[str, Any]:
        if example.task == "mcq":
            predicted_index = metrics.parse_mcq_answer(output, example.choices)
            return {
                "predicted_index": predicted_index,
                "predicted": LETTERS[predicted_index] if predicted_index is not None else None,
                "correct": predicted_index == example.answer_index,
                "invalid": predicted_index is None,
            }
        if example.task == "classification":
            predicted_label = parse_classification(output, example.labels)
            return {
                "predicted_label": predicted_label,
                "correct": predicted_label == example.label,
                "invalid": predicted_label is None,
            }
        if example.task == "generation":
            evidence = example.evidence or example.reference or ""
            return {
                "exact_match": metrics.normalize_answer(output)
                == metrics.normalize_answer(example.reference or ""),
                "token_f1": metrics.token_f1(output, example.reference or ""),
                "refusal": bool(metrics.refusal_rate([output])),
                "execution_claim": bool(metrics.execution_claim_rate([output])),
                "unsupported_token_rate_proxy": metrics.unsupported_token_rate(output, evidence),
            }
        prediction = output
        if example.prefix and prediction.startswith(example.prefix):
            prediction = prediction[len(example.prefix) :]
        return {
            "exact_match": metrics.normalize_answer(prediction)
            == metrics.normalize_answer(example.reference or ""),
            "token_f1": metrics.token_f1(prediction, example.reference or ""),
            "edit_similarity": metrics.edit_similarity(prediction, example.reference or ""),
            "syntax_valid": metrics.syntax_valid_rate([prediction], example.language),
        }

    def run(self) -> dict[str, Any]:
        started = time.perf_counter()
        for index, example in enumerate(self.examples):
            output, runtime = self._generate(example, index)
            score = self._score(example, output)
            record = {
                "id": example.id,
                "task": example.task,
                "source": example.source,
                "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
                "output": output,
                "score": score,
                **{key: value for key, value in runtime.items()},
            }
            self.predictions.append(record)
            if index % 10 == 0:
                logger.info(
                    "evaluation progress",
                    extra={"completed": index + 1, "total": len(self.examples)},
                )
        self.peak_memory = peak_memory_report()
        return self.summarize(started)

    def summarize(self, started: float) -> dict[str, Any]:
        by_task: dict[str, list[dict[str, Any]]] = {}
        for prediction in self.predictions:
            by_task.setdefault(prediction["task"], []).append(prediction)
        metrics_payload: dict[str, Any] = {}
        if "mcq" in by_task:
            rows = by_task["mcq"]
            preds: list[Any] = [row["score"]["predicted_index"] for row in rows]
            refs: list[Any] = [
                self.examples[index].answer_index
                for index in range(len(self.examples))
                if self.predictions[index]["task"] == "mcq"
            ]
            metrics_payload["mcq"] = {
                "examples": len(rows),
                "accuracy": metrics.accuracy(preds, refs),
                "invalid_rate": sum(row["score"]["invalid"] for row in rows) / len(rows),
                "accuracy_95ci": metrics.bootstrap_accuracy_ci(preds, refs, seed=self.seed),
            }
        if "classification" in by_task:
            rows = by_task["classification"]
            class_preds = [row["score"]["predicted_label"] or "__invalid__" for row in rows]
            class_refs = [
                self.examples[index].label or ""
                for index in range(len(self.examples))
                if self.predictions[index]["task"] == "classification"
            ]
            labels = sorted({label for example in self.examples for label in example.labels})
            positive = self.positive_label
            if positive is None:
                positive = next(
                    (label for label in ("malicious", "vulnerable") if label in labels),
                    labels[-1] if labels else None,
                )
            fpr = (
                metrics.false_positive_rate(class_preds, class_refs, positive_label=positive)
                if positive and len(labels) == 2
                else None
            )
            metrics_payload["classification"] = {
                "examples": len(rows),
                "labels": labels,
                "accuracy": metrics.accuracy(class_preds, class_refs),
                "macro_f1": metrics.macro_f1(class_preds, class_refs),
                "invalid_rate": sum(row["score"]["invalid"] for row in rows) / len(rows),
                "per_class": metrics.per_class_counts(class_preds, class_refs),
                "positive_label": positive if fpr is not None else None,
                "false_positive_rate": fpr,
            }
        if "generation" in by_task:
            rows = by_task["generation"]
            outputs = [row["output"] for row in rows]
            references = [
                self.examples[index].reference or ""
                for index in range(len(self.examples))
                if self.predictions[index]["task"] == "generation"
            ]
            metrics_payload["generation"] = {
                "examples": len(rows),
                "exact_match": metrics.exact_match(outputs, references),
                "token_f1": metrics.mean_token_f1(outputs, references),
                "refusal_rate": metrics.refusal_rate(outputs),
                "execution_claim_rate": metrics.execution_claim_rate(outputs),
                "unsupported_token_rate_proxy": sum(
                    row["score"]["unsupported_token_rate_proxy"] for row in rows
                )
                / len(rows),
                "note": "unsupported_token_rate_proxy is lexical, not a factual hallucination rate.",
            }
        if "completion" in by_task:
            rows = by_task["completion"]
            outputs = [row["output"] for row in rows]
            references = [
                self.examples[index].reference or ""
                for index in range(len(self.examples))
                if self.predictions[index]["task"] == "completion"
            ]
            syntax_values = [
                row["score"]["syntax_valid"]
                for row in rows
                if row["score"]["syntax_valid"] is not None
            ]
            metrics_payload["completion"] = {
                "examples": len(rows),
                "exact_match": metrics.exact_match(outputs, references),
                "token_f1": metrics.mean_token_f1(outputs, references),
                "mean_edit_similarity": sum(row["score"]["edit_similarity"] for row in rows)
                / len(rows),
                "syntax_valid_rate": (
                    sum(bool(value) for value in syntax_values) / len(syntax_values)
                    if syntax_values
                    else None
                ),
                "note": "Syntax validation uses ast.parse; generated code is never executed.",
            }

        latencies = [row["latency_seconds"] for row in self.predictions]
        completion_tokens = [row["completion_tokens"] for row in self.predictions]
        total_seconds = sum(latencies)
        cost = estimate_cost(total_seconds, cost_per_hour_usd=self.cost_per_hour_usd)
        parameters = None
        model_info = self.engine.info() if hasattr(self.engine, "info") else {}
        if isinstance(model_info, dict):
            parameters = model_info.get("parameters")
        performance = {}
        if parameters:
            parameters_b = parameters / 1e9
            for task, payload in metrics_payload.items():
                if "accuracy" in payload:
                    performance[f"{task}_accuracy_points_per_billion"] = (
                        metrics.performance_per_billion(payload["accuracy"], parameters_b)
                    )
            if "completion_tokens_per_second" not in performance and total_seconds > 0:
                performance["tokens_per_second"] = sum(completion_tokens) / total_seconds
        if cost.get("compute_cost_usd"):
            for task, payload in metrics_payload.items():
                if "accuracy" in payload:
                    performance[f"{task}_accuracy_points_per_usd"] = metrics.performance_per_dollar(
                        payload["accuracy"], cost["compute_cost_usd"]
                    )
        summary = {
            "run": {
                "name": f"cyberlite-eval-{datetime.now(tz=UTC).strftime('%Y%m%dT%H%M%SZ')}",
                "cyberlite_version": __version__,
                "created_at": datetime.now(tz=UTC).isoformat(),
                "seed": self.seed,
                "temperature": self.temperature,
                "prompt_style": self.prompt_style,
                "max_new_tokens": self.max_new_tokens,
                "examples": len(self.examples),
                "wall_clock_seconds": round(time.perf_counter() - started, 3),
                "research_status": "experimental; results require review before publication",
            },
            "model": model_info,
            "task_counts": _counts([example.task for example in self.examples]),
            "source_counts": _counts([example.source for example in self.examples]),
            "metrics": metrics_payload,
            "operational": {
                "latency_seconds": metrics.summarize_numeric(latencies),
                "generated_tokens": int(sum(completion_tokens)),
                "tokens_per_second": (
                    sum(completion_tokens) / total_seconds if total_seconds > 0 else None
                ),
                "peak_memory": self.peak_memory,
                "cost": cost,
            },
            "derived": performance,
            "reproducibility": environment_snapshot(),
            "hardware": detect_hardware().to_dict(),
            "limitations": [
                "No result is a claim of state-of-the-art performance.",
                "unsupported_token_rate_proxy measures lexical overlap, not truth.",
                "Generated code is syntax-checked only; it is never executed by this harness.",
                "Benchmark licenses and versions must be reported with any published result.",
            ],
        }
        summary["run_sha256"] = sha256_json(summary)
        return summary


def _counts(values: Sequence[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _dataset_hash(examples: list[EvalExample]) -> str:
    payload = [example.__dict__ for example in examples]
    return sha256_json(payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate a local CyberLite checkpoint.")
    parser.add_argument("--model", default="Qwen/Qwen3.5-0.8B")
    parser.add_argument("--adapter", default=None)
    parser.add_argument("--dataset", required=True, help="JSONL evaluation file")
    parser.add_argument("--out", default=None, help="output directory")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-new-tokens", type=int, default=None)
    parser.add_argument("--prompt-style", choices=["auto", "chat", "raw"], default="auto")
    parser.add_argument("--positive-label", default=None)
    parser.add_argument("--cost-per-hour-usd", type=float, default=None)
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda", "mps"])
    parser.add_argument(
        "--dtype", default="auto", choices=["auto", "float32", "float16", "bfloat16"]
    )
    parser.add_argument("--load-in-4bit", action="store_true")
    parser.add_argument("--load-in-8bit", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="validate the dataset only")
    parser.add_argument("--list-benchmarks", action="store_true")
    parser.add_argument("--json-logs", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(json_logs=args.json_logs)
    if args.list_benchmarks:
        print(json.dumps(list_benchmarks(), indent=2))
        return 0
    try:
        examples = load_examples(args.dataset, limit=args.limit)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.dry_run:
        print(f"dataset        : {args.dataset}")
        print(f"sha256         : {_dataset_hash(examples)}")
        print(f"examples       : {len(examples)}")
        print(f"tasks          : {_counts([example.task for example in examples])}")
        print(f"sources        : {_counts([example.source for example in examples])}")
        print("dry run complete; no model was loaded and no results were written")
        return 0

    style = _prompt_style(args.prompt_style, args.model)
    try:
        engine = InferenceEngine(
            args.model,
            adapter_path=args.adapter,
            device=args.device,
            dtype=args.dtype,
            load_in_4bit=args.load_in_4bit,
            load_in_8bit=args.load_in_8bit,
        )
    except (RuntimeError, OSError, ValueError) as exc:
        print(f"error: could not load model: {exc}", file=sys.stderr)
        return 2
    harness = EvaluationHarness(
        engine,
        examples,
        seed=args.seed,
        temperature=args.temperature,
        prompt_style=style,
        max_new_tokens=args.max_new_tokens,
        positive_label=args.positive_label,
        cost_per_hour_usd=args.cost_per_hour_usd,
    )
    summary = harness.run()
    summary["dataset"] = {
        "path": str(Path(args.dataset).resolve()),
        "sha256": _dataset_hash(examples),
        "examples": len(examples),
    }
    out_dir = (
        Path(args.out)
        if args.out
        else Path(
            f"results/evaluation/{Path(args.dataset).stem}-{datetime.now(tz=UTC).strftime('%Y%m%dT%H%M%SZ')}"
        )
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "summary.json", summary)
    with (out_dir / "predictions.jsonl").open("w", encoding="utf-8") as handle:
        for prediction in harness.predictions:
            handle.write(json.dumps(prediction, ensure_ascii=False) + "\n")
    print(f"results written to {out_dir}")
    print(json.dumps(summary["metrics"], indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

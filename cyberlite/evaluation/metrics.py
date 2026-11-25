"""Evaluation metrics with explicit definitions and uncertainty estimates.

No metric in this module is a substitute for human review. In particular,
``unsupported_token_rate`` is a lexical grounding proxy, not a factual
hallucination detector.
"""

from __future__ import annotations

import difflib
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from typing import Any

import numpy as np

_REFUSAL_RE = re.compile(
    r"\b(?:i can(?:'|no)t|i cannot|i'm unable|i am unable|i won't|i will not|"
    r"not able to (?:help|assist|provide)|cannot (?:help|assist|provide))\b",
    re.IGNORECASE,
)
_EXECUTION_CLAIM_RE = re.compile(
    r"\b(?:i (?:have )?(?:ran|executed|scanned|exploited|accessed|logged into)|"
    r"(?:the )?command (?:was|has been) (?:run|executed))\b",
    re.IGNORECASE,
)
_ANSWER_LABEL_RE = re.compile(
    r"\b(?:answer|choice|option)\s*(?:is|:|-)?\s*\(?([A-Za-z])\)?\b", re.IGNORECASE
)
_CITATION_RE = re.compile(r"\[S(\d+)\]")
_WORD_RE = re.compile(r"[A-Za-z0-9_]+")
_CHOICE_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def normalize_answer(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\w\s]", "", text)
    return text.strip()


def accuracy(predictions: Sequence[Any], references: Sequence[Any]) -> float:
    if len(predictions) != len(references):
        raise ValueError("predictions and references must have equal length")
    if not predictions:
        return 0.0
    return sum(pred == ref for pred, ref in zip(predictions, references, strict=True)) / len(
        predictions
    )


def exact_match(predictions: Sequence[str], references: Sequence[str]) -> float:
    if not predictions:
        return 0.0
    return accuracy(
        [normalize_answer(item) for item in predictions],
        [normalize_answer(item) for item in references],
    )


def token_f1(prediction: str, reference: str) -> float:
    """SQuAD-style token F1 over lowercased alphanumeric tokens."""

    predicted = _WORD_RE.findall(prediction.lower())
    gold = _WORD_RE.findall(reference.lower())
    if not predicted and not gold:
        return 1.0
    if not predicted or not gold:
        return 0.0
    common = Counter(predicted) & Counter(gold)
    overlap = sum(common.values())
    if overlap == 0:
        return 0.0
    precision = overlap / len(predicted)
    recall = overlap / len(gold)
    return 2 * precision * recall / (precision + recall)


def mean_token_f1(predictions: Sequence[str], references: Sequence[str]) -> float:
    if not predictions:
        return 0.0
    return float(
        np.mean([token_f1(pred, ref) for pred, ref in zip(predictions, references, strict=True)])
    )


def edit_similarity(prediction: str, reference: str) -> float:
    if not prediction and not reference:
        return 1.0
    return difflib.SequenceMatcher(a=prediction, b=reference).ratio()


def parse_mcq_answer(
    text: str, choices: Sequence[str], *, num_choices: int | None = None
) -> int | None:
    """Parse a multiple-choice answer index from free-form model output."""

    count = num_choices or len(choices)
    if count <= 0:
        return None
    stripped = text.strip()
    if not stripped:
        return None
    # Exact/near-exact choice text.
    normalized = normalize_answer(stripped)
    for index, choice in enumerate(choices):
        if normalized == normalize_answer(choice):
            return index
    match = _ANSWER_LABEL_RE.search(stripped)
    candidates: list[str] = []
    if match:
        candidates.append(match.group(1))
    # Common standalone formats: "B", "B.", "(B)", "**B**".
    for candidate in re.findall(r"(?<![A-Za-z])([A-Za-z])(?![A-Za-z])", stripped):
        candidates.append(candidate)
    for candidate in candidates:
        index = "abcdefghijklmnopqrstuvwxyz".index(candidate.lower())
        if index < count:
            return index
    return None


def parse_mcq_answer_set(
    text: str, choices: Sequence[str], *, num_choices: int | None = None
) -> list[int] | None:
    """Parse one or more choice indices from free-form model output.

    Multi-select benchmarks (for example SecEval) mark several choices correct
    and score an exact set match. Single-answer output such as ``"B"`` returns
    ``[1]``; ``"AC"``, ``"A, C"``, and ``"Answer: A and C"`` return ``[0, 2]``.
    Parsing is deliberately conservative: only uppercase letters in the
    configured range are collected, and choice text is matched exactly first.
    """

    count = num_choices or len(choices)
    if count <= 0:
        return None
    stripped = text.strip()
    if not stripped:
        return None
    normalized = normalize_answer(stripped)
    for index, choice in enumerate(choices):
        if normalized == normalize_answer(choice):
            return [index]
    limit = min(count, len(_CHOICE_LETTERS))
    letters: set[int] = set()
    for run in re.findall(r"(?<![A-Za-z])([A-Z]{1,4})(?![A-Za-z])", stripped):
        for letter in run:
            if letter in _CHOICE_LETTERS[:limit]:
                letters.add(_CHOICE_LETTERS.index(letter))
    if letters:
        return sorted(letters)
    single = parse_mcq_answer(stripped, choices, num_choices=count)
    return [single] if single is not None else None


def refusal_rate(predictions: Sequence[str]) -> float:
    if not predictions:
        return 0.0
    return sum(bool(_REFUSAL_RE.search(text)) for text in predictions) / len(predictions)


def execution_claim_rate(predictions: Sequence[str]) -> float:
    """Fraction of outputs claiming to have executed a command or accessed a system."""

    if not predictions:
        return 0.0
    return sum(bool(_EXECUTION_CLAIM_RE.search(text)) for text in predictions) / len(predictions)


def citation_ids(text: str) -> set[int]:
    return {int(match) for match in _CITATION_RE.findall(text)}


def citation_precision(predictions: Sequence[str], available_sources: Sequence[int]) -> float:
    """Fraction of cited IDs that correspond to retrieved sources."""

    valid = set(available_sources)
    cited = 0
    correct = 0
    for text in predictions:
        ids = citation_ids(text)
        cited += len(ids)
        correct += len(ids & valid)
    return correct / cited if cited else 0.0


def unsupported_token_rate(prediction: str, evidence: str) -> float:
    """Lexical grounding proxy: answer tokens absent from the evidence.

    This is cheap and reproducible but can over-penalize valid paraphrase. Use
    it as a screening signal alongside manual review, never as a "hallucination
    rate" by itself.
    """

    answer_tokens = set(_WORD_RE.findall(prediction.lower()))
    if not answer_tokens:
        return 0.0
    evidence_tokens = set(_WORD_RE.findall(evidence.lower()))
    return len(answer_tokens - evidence_tokens) / len(answer_tokens)


def macro_f1(predictions: Sequence[str], references: Sequence[str]) -> float:
    if not predictions:
        return 0.0
    labels = sorted(set(references) | set(predictions))
    scores: list[float] = []
    for label in labels:
        tp = sum(p == label and r == label for p, r in zip(predictions, references, strict=True))
        fp = sum(p == label and r != label for p, r in zip(predictions, references, strict=True))
        fn = sum(p != label and r == label for p, r in zip(predictions, references, strict=True))
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        scores.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)
    return float(np.mean(scores)) if scores else 0.0


def per_class_counts(
    predictions: Sequence[str], references: Sequence[str]
) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for label in sorted(set(references) | set(predictions)):
        tp = sum(p == label and r == label for p, r in zip(predictions, references, strict=True))
        fp = sum(p == label and r != label for p, r in zip(predictions, references, strict=True))
        fn = sum(p != label and r == label for p, r in zip(predictions, references, strict=True))
        result[label] = {"tp": tp, "fp": fp, "fn": fn}
    return result


def false_positive_rate(
    predictions: Sequence[str], references: Sequence[str], *, positive_label: str
) -> float | None:
    """FPR among truly negative examples; ``None`` when there are no negatives."""

    negatives = [
        (pred, ref)
        for pred, ref in zip(predictions, references, strict=True)
        if ref != positive_label
    ]
    if not negatives:
        return None
    false_positives = sum(pred == positive_label for pred, _ in negatives)
    return false_positives / len(negatives)


def syntax_valid_rate(code_samples: Sequence[str], language: str = "python") -> float | None:
    """Validate syntax without executing generated code.

    Only Python is supported locally; other languages require an external parser
    and return ``None`` rather than a fabricated result.
    """

    if language != "python":
        return None
    import ast

    if not code_samples:
        return 0.0
    valid = 0
    for sample in code_samples:
        try:
            ast.parse(sample)
            valid += 1
        except SyntaxError:
            pass
    return valid / len(code_samples)


def bootstrap_accuracy_ci(
    predictions: Sequence[Any],
    references: Sequence[Any],
    *,
    n_bootstrap: int = 10_000,
    confidence: float = 0.95,
    seed: int = 42,
) -> tuple[float, float]:
    """Percentile bootstrap confidence interval for accuracy."""

    if len(predictions) != len(references):
        raise ValueError("predictions and references must have equal length")
    if not predictions:
        return (0.0, 0.0)
    correct = np.asarray([int(p == r) for p, r in zip(predictions, references, strict=True)])
    rng = np.random.default_rng(seed)
    means = np.empty(n_bootstrap)
    for index in range(n_bootstrap):
        sample = rng.choice(correct, size=len(correct), replace=True)
        means[index] = sample.mean()
    alpha = (1 - confidence) / 2
    return (float(np.quantile(means, alpha)), float(np.quantile(means, 1 - alpha)))


def performance_per_billion(score_fraction: float, parameters_b: float) -> float | None:
    if parameters_b <= 0:
        return None
    return score_fraction * 100 / parameters_b


def performance_per_dollar(score_fraction: float, cost_usd: float) -> float | None:
    if cost_usd <= 0:
        return None
    return score_fraction * 100 / cost_usd


def summarize_numeric(values: Iterable[float]) -> dict[str, float]:
    data = np.asarray(list(values), dtype=float)
    if data.size == 0:
        return {"count": 0}
    return {
        "count": int(data.size),
        "mean": float(data.mean()),
        "median": float(np.median(data)),
        "p50": float(np.quantile(data, 0.5)),
        "p95": float(np.quantile(data, 0.95)),
        "min": float(data.min()),
        "max": float(data.max()),
    }

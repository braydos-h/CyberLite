"""SecEval benchmark adapter.

SecEval is a 2,189-item, four-choice cybersecurity knowledge benchmark released
under CC BY-NC-SA 4.0 for evaluation only. CyberLite never bundles the items and
never uses them for training. This module converts an upstream ``questions.json``
file into the local evaluation schema and keeps the upstream identity in each
record's metadata.

Upstream: https://huggingface.co/datasets/XuanwuAI/SecEval
Paper:    https://xuanwuai.github.io/SecEval
License:  CC BY-NC-SA 4.0 (evaluation-only)
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from cyberlite.evaluation.harness import load_examples

__all__ = [
    "CHOICE_PREFIX_RE",
    "convert_records",
    "convert_seceval_record",
    "normalize_answer_set",
    "strip_choice_prefix",
]

CHOICE_PREFIX_RE = re.compile(r"^\s*([A-Z])\s*[:.)\-]\s*", re.IGNORECASE)


def strip_choice_prefix(choice: str) -> str:
    """Remove an ``A:``/``B.`` style label from a choice string."""

    return CHOICE_PREFIX_RE.sub("", str(choice)).strip()


def normalize_answer_set(answer: Any) -> str:
    """Normalize an upstream answer into sorted, unique choice letters.

    SecEval uses single letters (``"B"``) and multi-select sets (``"AC"``).
    Invalid or empty answers raise ``ValueError`` so the converter can drop the
    item instead of silently scoring it as wrong.
    """

    if isinstance(answer, (list, tuple, set)):
        raw = "".join(str(item) for item in answer)
    else:
        raw = str(answer or "")
    letters = [char for char in raw.upper() if char.isalpha()]
    if not letters:
        raise ValueError("empty answer")
    normalized = sorted(set(letters))
    if any(letter not in "ABCD" for letter in normalized):
        raise ValueError(f"answer outside A-D: {raw!r}")
    return "".join(normalized)


def convert_seceval_record(record: dict[str, Any]) -> dict[str, Any] | None:
    """Convert one upstream item, or return ``None`` when it is unusable."""

    if not isinstance(record, dict):
        raise ValueError("SecEval record must be an object")
    question = str(record.get("question", "")).strip()
    raw_choices = record.get("choices")
    if not question or not isinstance(raw_choices, list) or len(raw_choices) < 2:
        return None
    choices = [strip_choice_prefix(choice) for choice in raw_choices]
    if any(not choice for choice in choices):
        return None
    try:
        answer = normalize_answer_set(record.get("answer"))
    except ValueError:
        return None
    if any("ABCD".index(letter) >= len(choices) for letter in answer):
        return None
    upstream_id = str(record.get("id") or "").strip()
    identifier = f"seceval-{upstream_id}" if upstream_id else ""
    return {
        "id": identifier,
        "task": "mcq",
        "source": "seceval",
        "question": question,
        "choices": choices,
        "answer": answer,
        "metadata": {
            "topics": list(record.get("topics") or []),
            "keyword": record.get("keyword"),
            "upstream_source": record.get("source"),
            "upstream_id": upstream_id,
        },
    }


def convert_records(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Convert upstream records and return them with a conversion report."""

    converted: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()
    seen: set[str] = set()
    for record in records:
        item = convert_seceval_record(record)
        if item is None:
            skipped["unusable_or_empty_answer"] += 1
            continue
        if not item["id"]:
            skipped["missing_id"] += 1
            continue
        if item["id"] in seen:
            skipped["duplicate_id"] += 1
            continue
        seen.add(item["id"])
        converted.append(item)
    report = {
        "upstream_items": len(records),
        "converted_items": len(converted),
        "skipped": dict(sorted(skipped.items())),
        "single_answer_items": sum(1 for item in converted if len(item["answer"]) == 1),
        "multi_answer_items": sum(1 for item in converted if len(item["answer"]) > 1),
        "topics": dict(
            sorted(
                Counter(topic for item in converted for topic in item["metadata"]["topics"]).items()
            )
        ),
    }
    return converted, report


def validate_converted(path: str) -> list[Any]:
    """Load a converted file through the evaluation harness as a sanity check."""

    return load_examples(path)

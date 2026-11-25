"""Validation and freeze metadata for held-out evaluation sets.

Evaluation files use their own schema (``data/synthesis/eval/_schema.json``).
They are never loaded as training records and are never used as generation
seeds. This module checks structural validity, detects duplicates, and measures
lexical overlap against a built training corpus.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cyberlite.data.contamination import ngram_fingerprints
from cyberlite.data.schema import iter_jsonl, sha256_file

SUITES = {
    "factual",
    "knowledge",
    "vulnerability",
    "secure-code",
    "logs",
    "grounded-qa",
    "incident-response",
    "false-positive",
    "configuration",
    "uncertainty",
    "retention",
}
DIFFICULTIES = {"foundational", "intermediate", "advanced", "expert"}
_ID_RE = re.compile(r"^eval-[a-z0-9-]{3,64}$")


@dataclass
class EvalIssue:
    code: str
    message: str
    item_id: str = ""
    severity: str = "error"

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "item_id": self.item_id,
            "severity": self.severity,
        }


@dataclass
class EvalReport:
    path: str
    sha256: str
    items: int = 0
    suites: dict[str, int] = field(default_factory=dict)
    domains: dict[str, int] = field(default_factory=dict)
    difficulties: dict[str, int] = field(default_factory=dict)
    issues: list[EvalIssue] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    training_overlap: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "items": self.items,
            "suites": dict(sorted(self.suites.items())),
            "domains": dict(sorted(self.domains.items())),
            "difficulties": dict(sorted(self.difficulties.items())),
            "ok": self.ok,
            "issues": [issue.to_dict() for issue in self.issues],
            "duplicates": self.duplicates,
            "training_overlap": self.training_overlap,
        }


def _require_string(payload: dict[str, Any], key: str, issue: list[EvalIssue], item_id: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        issue.append(EvalIssue("missing_field", f"{key} must be a non-empty string", item_id))
        return ""
    return value.strip()


def validate_eval_file(
    path: str | Path,
    *,
    training_texts: list[str] | None = None,
    overlap_threshold: float = 0.2,
) -> EvalReport:
    file_path = Path(path)
    report = EvalReport(path=str(file_path), sha256=sha256_file(file_path))
    seen_ids: set[str] = set()
    seen_questions: dict[str, str] = {}
    items: list[dict[str, Any]] = []
    for line_number, payload in iter_jsonl(file_path):
        items.append(payload)
        item_id = str(payload.get("id") or f"line-{line_number}")
        if item_id in seen_ids:
            report.duplicates.append(item_id)
            report.issues.append(EvalIssue("duplicate_id", "duplicate id", item_id))
        seen_ids.add(item_id)
        if not _ID_RE.fullmatch(item_id):
            report.issues.append(EvalIssue("bad_id", "id must match eval-<slug>", item_id))
        suite = _require_string(payload, "suite", report.issues, item_id)
        domain = _require_string(payload, "domain", report.issues, item_id)
        task_family = _require_string(payload, "task_family", report.issues, item_id)
        difficulty = _require_string(payload, "difficulty", report.issues, item_id)
        question = _require_string(payload, "question", report.issues, item_id)
        answer = _require_string(payload, "answer", report.issues, item_id)
        if suite and suite not in SUITES:
            report.issues.append(EvalIssue("bad_suite", f"unknown suite {suite}", item_id))
        if difficulty and difficulty not in DIFFICULTIES:
            report.issues.append(
                EvalIssue("bad_difficulty", f"unknown difficulty {difficulty}", item_id)
            )
        if suite:
            report.suites[suite] = report.suites.get(suite, 0) + 1
        if domain:
            report.domains[domain] = report.domains.get(domain, 0) + 1
        else:
            domain = "unknown"
        if task_family and not task_family.strip():
            report.issues.append(EvalIssue("bad_task_family", "empty task family", item_id))
        if difficulty:
            report.difficulties[difficulty] = report.difficulties.get(difficulty, 0) + 1

        choices = payload.get("choices")
        answer_choices = payload.get("answer_choices")
        if choices is not None:
            if not isinstance(choices, list) or not 3 <= len(choices) <= 6:
                report.issues.append(
                    EvalIssue("bad_choices", "choices must be a list of 3-6", item_id)
                )
            else:
                choice_ids = []
                for choice in choices:
                    if not isinstance(choice, dict) or set(choice) != {"id", "text"}:
                        report.issues.append(
                            EvalIssue("bad_choice", "choice needs id and text", item_id)
                        )
                        continue
                    if not str(choice["text"]).strip():
                        report.issues.append(EvalIssue("empty_choice", "empty choice", item_id))
                    choice_ids.append(str(choice["id"]))
                if len(set(choice_ids)) != len(choice_ids):
                    report.issues.append(
                        EvalIssue("duplicate_choice_id", "duplicate choice", item_id)
                    )
                if not isinstance(answer_choices, list) or not answer_choices:
                    report.issues.append(
                        EvalIssue("missing_answer_choices", "MCQ needs answer_choices", item_id)
                    )
                elif not set(map(str, answer_choices)).issubset(set(choice_ids)):
                    report.issues.append(
                        EvalIssue("answer_not_in_choices", "answer_choices not in choices", item_id)
                    )
            if not payload.get("rationale"):
                report.issues.append(
                    EvalIssue("missing_rationale", "MCQ needs a rationale", item_id)
                )
        if not payload.get("references"):
            report.issues.append(EvalIssue("missing_references", "references required", item_id))
        if question:
            normalized = " ".join(question.lower().split())
            if normalized in seen_questions:
                report.duplicates.append(item_id)
                report.issues.append(
                    EvalIssue(
                        "duplicate_question",
                        f"same question as {seen_questions[normalized]}",
                        item_id,
                    )
                )
            else:
                seen_questions[normalized] = item_id
        if answer and len(answer) < 2 and choices is None:
            report.issues.append(EvalIssue("short_answer", "answer is too short", item_id))
    report.items = len(items)
    if not items:
        report.issues.append(EvalIssue("empty_file", "evaluation file has no items"))

    if training_texts:
        index: set[str] = set()
        for text in training_texts:
            index.update(ngram_fingerprints(text, 13))
        worst: list[dict[str, Any]] = []
        contaminated = 0
        for payload in items:
            text = " ".join(
                str(value)
                for key, value in payload.items()
                if key in {"question", "answer", "evidence", "logs", "rationale"}
            )
            fingerprints = ngram_fingerprints(text, 13)
            if not fingerprints:
                continue
            overlap = len(fingerprints & index) / len(fingerprints)
            if overlap >= overlap_threshold:
                contaminated += 1
                worst.append({"id": payload.get("id"), "overlap": round(overlap, 4)})
        report.training_overlap = {
            "training_texts": len(training_texts),
            "threshold": overlap_threshold,
            "contaminated_items": contaminated,
            "worst": sorted(worst, key=lambda item: -float(item["overlap"]))[:20],
            "method": "13-gram lexical overlap",
        }
    return report


def freeze_meta(
    report: EvalReport, *, name: str, license_id: str, description: str
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "name": name,
        "file": Path(report.path).name,
        "sha256": report.sha256,
        "items": report.items,
        "suites": dict(sorted(report.suites.items())),
        "difficulties": dict(sorted(report.difficulties.items())),
        "license": license_id,
        "evaluation_only": True,
        "frozen": True,
        "description": description,
        "validation": {
            "ok": report.ok,
            "error_count": sum(1 for issue in report.issues if issue.severity == "error"),
            "warning_count": sum(1 for issue in report.issues if issue.severity == "warning"),
        },
    }


def write_report(report: EvalReport, destination: str | Path) -> None:
    Path(destination).write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

"""Review ledger, rubric scoring, and quarantine decisions.

A review file is written by an independent reviewer. The schema is deliberately
simple so an external agent or human can produce it without importing the
package. This module never invents a review: it only aggregates files that
exist, records disagreement, and applies decisions to a corpus.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

RUBRIC = (
    "technical_accuracy",
    "source_grounding",
    "completeness",
    "relevance",
    "clarity",
    "practical_usefulness",
    "originality_diversity",
    "small_model_suitability",
)
SCORE_MIN = 0
SCORE_MAX = 10
MIN_AVERAGE = 8.5
MIN_TECHNICAL = 9.0
MIN_GROUNDING = 9.0
MAX_REVISIONS = 3


class ReviewError(ValueError):
    """A review ledger is malformed or internally inconsistent."""


@dataclass
class ReviewItem:
    record_id: str
    reviewer: str
    review_type: str
    scores: dict[str, float]
    findings: list[str]
    decision: str
    critical: bool = False
    revision: int = 0
    source_dependent: bool = True
    content_hash: str = ""

    @property
    def average(self) -> float:
        if not self.scores:
            return 0.0
        return round(sum(self.scores.values()) / len(self.scores), 3)

    @property
    def accepted(self) -> bool:
        if self.critical:
            return False
        if self.decision != "accept":
            return False
        if self.average < MIN_AVERAGE:
            return False
        if self.scores.get("technical_accuracy", 0) < MIN_TECHNICAL:
            return False
        return not (
            self.source_dependent and self.scores.get("source_grounding", 0) < MIN_GROUNDING
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "reviewer": self.reviewer,
            "review_type": self.review_type,
            "scores": self.scores,
            "average": self.average,
            "findings": self.findings,
            "decision": self.decision,
            "critical": self.critical,
            "revision": self.revision,
            "content_hash": self.content_hash,
            "accepted": self.accepted,
        }


@dataclass
class ReviewLedger:
    path: str
    reviewer: str
    review_type: str
    artifact: str
    dataset_version: str
    items: list[ReviewItem] = field(default_factory=list)

    def validate(self) -> None:
        if not self.reviewer:
            raise ReviewError(f"{self.path}: reviewer is required")
        if self.review_type not in {"technical", "quality", "security-privacy", "adjudication"}:
            raise ReviewError(f"{self.path}: unknown review_type {self.review_type!r}")
        seen: set[str] = set()
        for item in self.items:
            if item.record_id in seen:
                raise ReviewError(f"{self.path}: duplicate record {item.record_id}")
            seen.add(item.record_id)
            missing = set(RUBRIC) - set(item.scores)
            if missing:
                raise ReviewError(f"{self.path}: {item.record_id} missing scores {sorted(missing)}")
            for key, value in item.scores.items():
                if not SCORE_MIN <= float(value) <= SCORE_MAX:
                    raise ReviewError(f"{self.path}: {item.record_id} score {key} out of range")
            if item.decision not in {"accept", "revise", "quarantine"}:
                raise ReviewError(f"{self.path}: {item.record_id} invalid decision")
            if item.decision in {"revise", "quarantine"} and not item.findings:
                raise ReviewError(
                    f"{self.path}: {item.record_id} needs a concrete finding for {item.decision}"
                )
            if item.revision > MAX_REVISIONS:
                raise ReviewError(f"{self.path}: {item.record_id} exceeds revision limit")


def load_review(path: str | Path) -> ReviewLedger:
    file_path = Path(path)
    payload = json.loads(file_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ReviewError(f"{file_path}: review must be a JSON object")
    for key in ("reviewer", "review_type", "artifact", "dataset_version", "items"):
        if key not in payload:
            raise ReviewError(f"{file_path}: missing {key}")
    if not isinstance(payload["items"], list) or not payload["items"]:
        raise ReviewError(f"{file_path}: items must be a non-empty list")
    ledger = ReviewLedger(
        path=str(file_path),
        reviewer=str(payload["reviewer"]),
        review_type=str(payload["review_type"]),
        artifact=str(payload["artifact"]),
        dataset_version=str(payload["dataset_version"]),
    )
    for raw in payload["items"]:
        if not isinstance(raw, dict):
            raise ReviewError(f"{file_path}: item must be an object")
        scores = raw.get("scores")
        if not isinstance(scores, dict):
            raise ReviewError(f"{file_path}: item scores must be an object")
        findings = raw.get("findings", [])
        if not isinstance(findings, list):
            raise ReviewError(f"{file_path}: findings must be a list")
        ledger.items.append(
            ReviewItem(
                record_id=str(raw.get("record_id", "")),
                reviewer=ledger.reviewer,
                review_type=ledger.review_type,
                scores={str(key): float(value) for key, value in scores.items()},
                findings=[str(item) for item in findings],
                decision=str(raw.get("decision", "quarantine")),
                critical=bool(raw.get("critical", False)),
                revision=int(raw.get("revision", 0)),
                source_dependent=bool(raw.get("source_dependent", True)),
                content_hash=str(raw.get("content_hash", "")),
            )
        )
    ledger.validate()
    return ledger


@dataclass
class AggregateReview:
    record_id: str
    reviews: list[ReviewItem] = field(default_factory=list)

    @property
    def average(self) -> float:
        if not self.reviews:
            return 0.0
        return round(sum(item.average for item in self.reviews) / len(self.reviews), 3)

    @property
    def technical_accuracy(self) -> float:
        return (
            round(
                sum(item.scores.get("technical_accuracy", 0.0) for item in self.reviews)
                / len(self.reviews),
                3,
            )
            if self.reviews
            else 0.0
        )

    @property
    def source_grounding(self) -> float:
        return (
            round(
                sum(item.scores.get("source_grounding", 0.0) for item in self.reviews)
                / len(self.reviews),
                3,
            )
            if self.reviews
            else 0.0
        )

    @property
    def disagreements(self) -> list[str]:
        decisions = {item.decision for item in self.reviews}
        if len(decisions) > 1:
            return [f"decision disagreement: {sorted(decisions)}"]
        if self.reviews:
            averages = [item.average for item in self.reviews]
            if max(averages) - min(averages) > 2.0:
                return [f"score spread {max(averages) - min(averages):.1f} points"]
        return []

    @property
    def decision(self) -> str:
        if any(item.critical for item in self.reviews):
            return "quarantine"
        if any(item.decision == "quarantine" for item in self.reviews):
            return "quarantine"
        if any(item.decision == "revise" for item in self.reviews):
            return "revise"
        if self.reviews and all(item.accepted for item in self.reviews):
            return "accept"
        return "revise" if self.reviews else "unreviewed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "reviews": [item.to_dict() for item in self.reviews],
            "average": self.average,
            "technical_accuracy": self.technical_accuracy,
            "source_grounding": self.source_grounding,
            "decision": self.decision,
            "disagreements": self.disagreements,
        }


def aggregate(ledgers: list[ReviewLedger]) -> tuple[dict[str, AggregateReview], dict[str, Any]]:
    grouped: dict[str, AggregateReview] = {}
    for ledger in ledgers:
        for item in ledger.items:
            grouped.setdefault(
                item.record_id, AggregateReview(record_id=item.record_id)
            ).reviews.append(item)
    review_types: dict[str, int] = {}
    decisions: dict[str, int] = {}
    for ledger in ledgers:
        review_types[ledger.review_type] = review_types.get(ledger.review_type, 0) + len(
            ledger.items
        )
    for aggregate_item in grouped.values():
        decisions[aggregate_item.decision] = decisions.get(aggregate_item.decision, 0) + 1
    disagreement_records = [record_id for record_id, item in grouped.items() if item.disagreements]
    summary = {
        "ledgers": len(ledgers),
        "reviewed_records": len(grouped),
        "reviews": sum(len(item.reviews) for item in grouped.values()),
        "review_types": dict(sorted(review_types.items())),
        "decisions": dict(sorted(decisions.items())),
        "disagreement_records": len(disagreement_records),
        "disagreement_rate": round(len(disagreement_records) / max(1, len(grouped)), 4),
        "disagreement_ids": sorted(disagreement_records)[:100],
        "reviewers": sorted({ledger.reviewer for ledger in ledgers}),
    }
    return grouped, summary

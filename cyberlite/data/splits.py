"""Deterministic, group-aware dataset splitting."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass

from cyberlite.data.schema import Record


@dataclass(frozen=True)
class SplitRatios:
    train: float = 0.9
    validation: float = 0.05
    test: float = 0.05

    def __post_init__(self) -> None:
        total = self.train + self.validation + self.test
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"split ratios must sum to 1.0, got {total}")
        if min(self.train, self.validation, self.test) < 0:
            raise ValueError("split ratios must be non-negative")


def split_bucket(record_id: str, seed: int) -> float:
    """Map a record ID to a stable bucket in [0, 1)."""

    digest = hashlib.sha256(f"{seed}:{record_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def record_group(record: Record) -> str:
    """Return the leakage-control unit for a record.

    Preference order: an explicit group, the source document, an upstream
    security identifier, then the content ID (which disables grouping for that
    record). Normalizers set these fields explicitly; the fallbacks keep
    third-party JSONL inputs safe by default.
    """

    metadata = record.metadata or {}
    for key in ("group", "source_group", "document_group"):
        value = str(metadata.get(key) or "").strip()
        if value:
            return value
    document = str(metadata.get("document") or "").strip()
    if document:
        return f"{record.source}:{document}"
    for key in ("attack_id", "cwe_id", "cve_id", "rfc", "manpage", "upstream_id", "source_id"):
        value = str(metadata.get(key) or "").strip()
        if value:
            return f"{record.source}:{value}"
    heading = str(metadata.get("heading") or "").strip()
    if heading:
        return f"{record.source}:{record.url or 'document'}:{heading}"
    return record.id


def assign_split(record: Record, ratios: SplitRatios, seed: int) -> str:
    bucket = split_bucket(record_group(record), seed)
    if bucket < ratios.train:
        return "train"
    if bucket < ratios.train + ratios.validation:
        return "validation"
    return "test"


def split_records(
    records: list[Record],
    ratios: SplitRatios = SplitRatios(),
    seed: int = 42,
    *,
    group_key: Callable[[Record], str] | None = None,
) -> dict[str, list[Record]]:
    """Split records deterministically; groups are the leakage-control unit.

    Every record in the same group receives the same split bucket, so sections
    of one document, or multiple task views of one CVE/CWE/technique, cannot
    straddle training and evaluation.
    """

    key_function = group_key or record_group
    splits: dict[str, list[Record]] = {"train": [], "validation": [], "test": []}
    for record in records:
        group = key_function(record)
        bucket = split_bucket(group, seed)
        if bucket < ratios.train:
            record.split = "train"
        elif bucket < ratios.train + ratios.validation:
            record.split = "validation"
        else:
            record.split = "test"
        splits[record.split].append(record)
    return splits


def group_split_violations(splits: dict[str, list[Record]]) -> list[dict[str, str]]:
    """Return groups that appear in more than one split."""

    seen: dict[str, str] = {}
    violations: list[dict[str, str]] = []
    for split_name, records in splits.items():
        for record in records:
            group = record_group(record)
            previous = seen.get(group)
            if previous and previous != split_name:
                violations.append(
                    {
                        "group": group,
                        "left_split": previous,
                        "right_split": split_name,
                        "record_id": record.id,
                    }
                )
            else:
                seen[group] = split_name
    return violations

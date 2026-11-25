"""Deterministic, group-aware dataset splitting."""

from __future__ import annotations

import hashlib
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


def assign_split(record: Record, ratios: SplitRatios, seed: int) -> str:
    bucket = split_bucket(record.id, seed)
    if bucket < ratios.train:
        return "train"
    if bucket < ratios.train + ratios.validation:
        return "validation"
    return "test"


def split_records(
    records: list[Record], ratios: SplitRatios = SplitRatios(), seed: int = 42
) -> dict[str, list[Record]]:
    """Split records deterministically; IDs are the unit of leakage control."""

    splits: dict[str, list[Record]] = {"train": [], "validation": [], "test": []}
    for record in records:
        record.split = assign_split(record, ratios, seed)
        splits[record.split].append(record)
    return splits

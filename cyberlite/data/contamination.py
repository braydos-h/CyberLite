"""Benchmark-contamination checks for training corpora.

This is a best-effort lexical screen, not a proof of contamination absence.
It catches verbatim or near-verbatim benchmark leakage; paraphrased leakage and
semantic overlap require manual review.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cyberlite.data.schema import Record

_WORD_RE = re.compile(r"[a-z0-9_]+")
_WS_RE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9_\s]", " ", text)
    return _WS_RE.sub(" ", text).strip()


def ngram_fingerprints(text: str, n: int = 13) -> set[str]:
    """Return hashed word n-gram fingerprints for a text."""

    if n < 3:
        raise ValueError("n must be >= 3")
    words = _WORD_RE.findall(_normalize(text))
    if len(words) < n:
        return set()
    return {
        hashlib.blake2b(" ".join(words[i : i + n]).encode(), digest_size=8).hexdigest()
        for i in range(len(words) - n + 1)
    }


def _strings(payload: Any) -> list[str]:
    """Collect every string value from a parsed JSON payload."""

    if isinstance(payload, str):
        return [payload]
    if isinstance(payload, dict):
        collected: list[str] = []
        for value in payload.values():
            collected.extend(_strings(value))
        return collected
    if isinstance(payload, list):
        collected = []
        for value in payload:
            collected.extend(_strings(value))
        return collected
    return []


@dataclass
class ContaminationIndex:
    n: int = 13
    _fingerprints: set[str] = field(default_factory=set)
    sources: list[str] = field(default_factory=list)

    def add_text(self, text: str) -> None:
        self._fingerprints.update(ngram_fingerprints(text, self.n))

    def add_records(self, records: Iterable[Record]) -> None:
        for record in records:
            self.add_text(record.text_for_dedup())

    def add_file(self, path: str | Path) -> None:
        """Index an evaluation file without assuming the corpus record schema.

        Benchmarks use their own schema (for example ``question`` / ``choices`` /
        ``answer``), so parsing them as CyberLite training records silently drops
        every item. This indexes every string value instead, which keeps the
        screen working across schemas.
        """

        path = Path(path)
        added = 0
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                self.add_text(line)
                added += 1
                continue
            record_text = " ".join(_strings(payload))
            if record_text.strip():
                self.add_text(record_text)
                added += 1
        if added == 0:
            self.add_text(text)
        self.sources.append(str(path))

    def overlap(self, text: str) -> float:
        """Fraction of the candidate's n-grams present in the evaluation index."""

        candidate = ngram_fingerprints(text, self.n)
        if not candidate:
            return 0.0
        return len(candidate & self._fingerprints) / len(candidate)

    def is_contaminated(self, text: str, threshold: float = 0.2) -> bool:
        return self.overlap(text) >= threshold

    @property
    def size(self) -> int:
        return len(self._fingerprints)


def build_index(eval_files: Iterable[str], *, n: int = 13) -> ContaminationIndex:
    """Index every evaluation file for overlap checks."""

    index = ContaminationIndex(n=n)
    for path in eval_files:
        index.add_file(path)
    return index


def check_contamination(
    records: Iterable[Record],
    eval_files: Iterable[str],
    *,
    n: int = 13,
    threshold: float = 0.2,
    index: ContaminationIndex | None = None,
) -> tuple[list[Record], list[dict[str, object]]]:
    """Remove contaminated records and return kept records plus findings."""

    active = index if index is not None else build_index(eval_files, n=n)
    kept: list[Record] = []
    findings: list[dict[str, object]] = []
    for record in records:
        score = active.overlap(record.text_for_dedup())
        if score >= threshold:
            findings.append({"id": record.id, "source": record.source, "overlap": round(score, 4)})
        else:
            kept.append(record)
    return kept, findings

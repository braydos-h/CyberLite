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


# ---------------------------------------------------------------------------
# Per-benchmark screening (v2)
# ---------------------------------------------------------------------------

from cyberlite.data.cleaning import hamming_distance, simhash64  # noqa: E402


class ContaminationIndexError(ValueError):
    """Raised when an evaluation file produces no usable index."""


@dataclass
class EvaluationSet:
    name: str
    path: str
    sha256: str
    version: str
    license: str
    items: int
    ngrams: int
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def populated(self) -> bool:
        return self.ngrams > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "sha256": self.sha256,
            "version": self.version,
            "license": self.license,
            "items": self.items,
            "ngrams": self.ngrams,
            "populated": self.populated,
            "metadata": self.metadata,
        }


@dataclass
class BenchmarkFinding:
    id: str
    source: str
    benchmark: str
    overlap: float
    group: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "id": self.id,
            "source": self.source,
            "benchmark": self.benchmark,
            "overlap": round(self.overlap, 4),
        }
        if self.group:
            payload["group"] = self.group
        return payload


def _load_eval_metadata(path: Path) -> dict[str, Any]:
    sidecar = path.with_suffix(".meta.json")
    if not sidecar.is_file():
        return {}
    try:
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _eval_texts(path: Path) -> tuple[list[str], int]:
    texts: list[str] = []
    items = 0
    text = path.read_text(encoding="utf-8", errors="ignore")
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        items += 1
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            texts.append(line)
            continue
        record_text = " ".join(_strings(payload))
        if record_text.strip():
            texts.append(record_text)
    if items == 0 and text.strip():
        texts.append(text)
        items = 1
    return texts, items


class BenchmarkIndex:
    """One independently reported index per held-out evaluation file."""

    def __init__(self, n: int = 13, *, allow_empty: bool = False) -> None:
        if n < 3:
            raise ValueError("n must be >= 3")
        self.n = n
        self.allow_empty = allow_empty
        self.sets: list[EvaluationSet] = []
        self._fingerprints: dict[str, set[str]] = {}
        self._matched: dict[str, set[str]] = {}

    def add_file(self, path: str | Path) -> EvaluationSet:
        file_path = Path(path)
        if not file_path.is_file():
            raise FileNotFoundError(f"evaluation file not found: {file_path}")
        texts, items = _eval_texts(file_path)
        fingerprints: set[str] = set()
        for text in texts:
            fingerprints.update(ngram_fingerprints(text, self.n))
        if not fingerprints and not self.allow_empty:
            raise ContaminationIndexError(
                f"evaluation index {file_path} is empty; refusing to treat a skipped "
                "screen as a pass"
            )
        metadata = _load_eval_metadata(file_path)
        name = str(metadata.get("benchmark") or file_path.stem)
        version = str(
            metadata.get("upstream_revision")
            or metadata.get("converted_sha256")
            or metadata.get("version")
            or "unknown"
        )
        license_id = str(metadata.get("license") or "unknown")
        from cyberlite.data.schema import sha256_file

        item = EvaluationSet(
            name=name,
            path=str(file_path),
            sha256=sha256_file(file_path),
            version=version,
            license=license_id,
            items=items,
            ngrams=len(fingerprints),
            metadata=metadata,
        )
        # A duplicate benchmark name would make per-benchmark reporting ambiguous.
        if any(existing.name == name for existing in self.sets):
            name = f"{name}:{file_path.stem}"
            item.name = name
        self.sets.append(item)
        self._fingerprints[name] = fingerprints
        self._matched[name] = set()
        return item

    @property
    def size(self) -> int:
        return sum(len(fingerprints) for fingerprints in self._fingerprints.values())

    def screen(self, record: Record, threshold: float = 0.2) -> list[BenchmarkFinding]:
        candidate = ngram_fingerprints(record.text_for_dedup(), self.n)
        if not candidate:
            return []
        findings: list[BenchmarkFinding] = []
        for item in self.sets:
            fingerprints = self._fingerprints[item.name]
            intersection = candidate & fingerprints
            if not intersection:
                continue
            overlap = len(intersection) / len(candidate)
            if overlap >= threshold:
                self._matched[item.name].add(record.id)
                findings.append(
                    BenchmarkFinding(
                        id=record.id,
                        source=record.source,
                        benchmark=item.name,
                        overlap=overlap,
                        group=str(record.metadata.get("group") or "") or None,
                    )
                )
        return findings

    def report(self) -> dict[str, Any]:
        return {
            "ngram": self.n,
            "total_indexed_ngrams": self.size,
            "sets": [
                {
                    **item.to_dict(),
                    "matched_records": len(self._matched.get(item.name, set())),
                    "matched_ids": sorted(self._matched.get(item.name, set()))[:50],
                }
                for item in self.sets
            ],
        }


def build_benchmark_index(
    eval_files: Iterable[str | Path], *, n: int = 13, allow_empty: bool = False
) -> BenchmarkIndex:
    index = BenchmarkIndex(n=n, allow_empty=allow_empty)
    for path in eval_files:
        index.add_file(path)
    return index


def check_contamination_v2(
    records: Iterable[Record],
    index: BenchmarkIndex,
    *,
    threshold: float = 0.2,
    group_quarantine: bool = True,
) -> tuple[list[Record], list[BenchmarkFinding], dict[str, Any]]:
    """Screen all records, optionally quarantining a whole affected group.

    Group quarantine prevents a document whose one section leaked an evaluation
    item from contributing its remaining sections to training.
    """

    materialized = list(records)
    findings: list[BenchmarkFinding] = []
    by_id: dict[str, list[BenchmarkFinding]] = {}
    for record in materialized:
        record_findings = index.screen(record, threshold)
        if record_findings:
            findings.extend(record_findings)
            by_id[record.id] = record_findings
    contaminated_groups = {finding.group for finding in findings if finding.group}
    kept: list[Record] = []
    removed_groups: set[str] = set()
    group_removed_ids: list[str] = []
    for record in materialized:
        group = str(record.metadata.get("group") or "") or None
        if record.id in by_id:
            continue
        if group_quarantine and group and group in contaminated_groups:
            removed_groups.add(group)
            group_removed_ids.append(record.id)
            continue
        kept.append(record)
    report = index.report()
    report.update(
        {
            "threshold": threshold,
            "removed": len(findings),
            "removed_groups": sorted(removed_groups),
            "group_removed_ids": group_removed_ids,
            "findings": [finding.to_dict() for finding in findings[:200]],
        }
    )
    return kept, findings, report


@dataclass
class SplitLeakageFinding:
    left_split: str
    right_split: str
    left_id: str
    right_id: str
    kind: str
    distance: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "left_split": self.left_split,
            "right_split": self.right_split,
            "left_id": self.left_id,
            "right_id": self.right_id,
            "kind": self.kind,
            "distance": self.distance,
        }


def cross_split_leakage(
    splits: dict[str, list[Record]], *, threshold: int = 3
) -> list[SplitLeakageFinding]:
    """Detect exact and SimHash-near duplicates that cross split boundaries."""

    findings: list[SplitLeakageFinding] = []
    exact: dict[str, tuple[str, str]] = {}
    bands: dict[tuple[int, int], list[tuple[str, str, int]]] = {}
    for split_name in ("train", "validation", "test"):
        for record in splits.get(split_name, []):
            text = record.text_for_dedup()
            normalized = " ".join(_normalize(text).split())
            exact_key = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
            previous = exact.get(exact_key)
            if previous and previous[0] != split_name:
                findings.append(
                    SplitLeakageFinding(
                        left_split=previous[0],
                        right_split=split_name,
                        left_id=previous[1],
                        right_id=record.id,
                        kind="exact",
                    )
                )
            else:
                exact.setdefault(exact_key, (split_name, record.id))
            if threshold <= 0:
                continue
            fingerprint = simhash64(text)
            for band in range(4):
                key = (band, (fingerprint >> (band * 16)) & 0xFFFF)
                for other_split, other_id, other_fingerprint in bands.get(key, []):
                    if other_split == split_name:
                        continue
                    distance = hamming_distance(fingerprint, other_fingerprint)
                    if distance <= threshold:
                        findings.append(
                            SplitLeakageFinding(
                                left_split=other_split,
                                right_split=split_name,
                                left_id=other_id,
                                right_id=record.id,
                                kind="near",
                                distance=distance,
                            )
                        )
            for band in range(4):
                key = (band, (fingerprint >> (band * 16)) & 0xFFFF)
                bands.setdefault(key, []).append((split_name, record.id, fingerprint))
    return findings

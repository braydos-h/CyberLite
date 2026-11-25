"""Approximate near-duplicate detection for synthesised records.

Exact hashes and 64-bit SimHash already exist in ``cyberlite.data.cleaning``.
This module adds a MinHash/LSH pass over word shingles so that paraphrased or
structurally duplicated records that survive SimHash are surfaced before they
enter the corpus. It is a lexical approximation, not an embedding-based
semantic model; the report says so.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache

from cyberlite.data.schema import Record

_TOKEN_RE = re.compile(r"[a-z0-9_]+")
_PRIME = (1 << 61) - 1
_DEFAULT_HASHES = 64
_DEFAULT_BANDS = 16
_DEFAULT_ROWS = 4


@dataclass(frozen=True)
class DuplicatePair:
    left_id: str
    right_id: str
    similarity: float


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def shingles(text: str, size: int = 5) -> set[int]:
    tokens = _tokens(text)
    if not tokens:
        return set()
    if len(tokens) < size:
        payload = " ".join(tokens)
        return {int.from_bytes(hashlib.blake2b(payload.encode(), digest_size=8).digest(), "big")}
    values: set[int] = set()
    for index in range(len(tokens) - size + 1):
        payload = " ".join(tokens[index : index + size])
        values.add(int.from_bytes(hashlib.blake2b(payload.encode(), digest_size=8).digest(), "big"))
    return values


@lru_cache(maxsize=8)
def _permutations(count: int) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    for index in range(count):
        digest = hashlib.sha256(f"cyberlite-minhash-{index}".encode()).digest()
        a = int.from_bytes(digest[:8], "big") % _PRIME
        b = int.from_bytes(digest[8:16], "big") % _PRIME
        result.append((a or 1, b))
    return result


def minhash_signature(values: Iterable[int], *, count: int = _DEFAULT_HASHES) -> tuple[int, ...]:
    material = list(values)
    if not material:
        return tuple([0] * count)
    signature: list[int] = []
    for a, b in _permutations(count):
        signature.append(min(((a * value + b) % _PRIME) for value in material))
    return tuple(signature)


def _bands(signature: tuple[int, ...], bands: int, rows: int) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    for band in range(bands):
        chunk = signature[band * rows : (band + 1) * rows]
        if not chunk:
            break
        digest = hashlib.blake2b(repr(chunk).encode(), digest_size=8).digest()
        result.append((band, int.from_bytes(digest, "big")))
    return result


def find_near_duplicates(
    records: list[Record],
    *,
    threshold: float = 0.8,
    count: int = _DEFAULT_HASHES,
    bands: int = _DEFAULT_BANDS,
    rows: int = _DEFAULT_ROWS,
    max_pairs: int = 5000,
) -> list[DuplicatePair]:
    """Return near-duplicate pairs above ``threshold`` using banded MinHash."""

    if bands * rows > count:
        raise ValueError("bands * rows must not exceed the signature length")
    prepared: list[tuple[Record, set[int], tuple[int, ...]]] = []
    for record in records:
        values = shingles(record.text_for_dedup())
        prepared.append((record, values, minhash_signature(values, count=count)))
    buckets: dict[tuple[int, int], list[int]] = {}
    candidate_pairs: set[tuple[int, int]] = set()
    for index, (_, _, signature) in enumerate(prepared):
        for key in _bands(signature, bands, rows):
            bucket = buckets.setdefault(key, [])
            for other in bucket:
                if other != index:
                    candidate_pairs.add((min(other, index), max(other, index)))
            bucket.append(index)
            if len(candidate_pairs) >= max_pairs:
                break
        if len(candidate_pairs) >= max_pairs:
            break
    pairs: list[DuplicatePair] = []
    for left, right in sorted(candidate_pairs):
        left_values = prepared[left][1]
        right_values = prepared[right][1]
        if not left_values or not right_values:
            continue
        intersection = len(left_values & right_values)
        union = len(left_values | right_values)
        similarity = intersection / union if union else 0.0
        if similarity >= threshold:
            pairs.append(
                DuplicatePair(
                    left_id=prepared[left][0].id,
                    right_id=prepared[right][0].id,
                    similarity=round(similarity, 4),
                )
            )
    pairs.sort(key=lambda item: (-item.similarity, item.left_id, item.right_id))
    return pairs


def deduplicate_near(
    records: list[Record],
    *,
    threshold: float = 0.8,
    max_pairs: int = 5000,
) -> tuple[list[Record], list[DuplicatePair]]:
    """Remove later members of near-duplicate pairs, keeping deterministic order."""

    ordered = sorted(records, key=lambda item: item.id)
    pairs = find_near_duplicates(ordered, threshold=threshold, max_pairs=max_pairs)
    removed: set[str] = set()
    kept_pairs: list[DuplicatePair] = []
    for pair in pairs:
        if pair.left_id in removed or pair.right_id in removed:
            continue
        removed.add(pair.right_id)
        kept_pairs.append(pair)
    kept = [record for record in ordered if record.id not in removed]
    return kept, kept_pairs


def template_skeletons(records: list[Record], *, limit: int = 15) -> list[dict[str, object]]:
    """Group prompt shapes to reveal overrepresented generation templates."""

    buckets: dict[str, list[str]] = {}
    for record in records:
        prompt = record.prompt or ""
        if record.messages:
            prompt = "\n".join(
                message["content"] for message in record.messages if message["role"] == "user"
            )
        skeleton = _TOKEN_RE.sub("w", prompt.lower())
        skeleton = re.sub(r"w+", "w", skeleton).strip()[:180]
        buckets.setdefault(skeleton, []).append(record.id)
    ranked = sorted(buckets.items(), key=lambda item: (-len(item[1]), item[0]))
    return [
        {"skeleton": skeleton, "count": len(ids), "sample_ids": ids[:3]}
        for skeleton, ids in ranked[:limit]
    ]

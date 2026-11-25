from __future__ import annotations

from cyberlite.data.schema import Record
from cyberlite.data.semantic import deduplicate_near, find_near_duplicates, shingles


def _record(identifier: str, text: str) -> Record:
    return Record(
        id=identifier,
        source="test",
        license="Synthetic",
        task="knowledge",
        prompt="q",
        response=text,
        metadata={"group": identifier},
    )


def test_shingles_are_stable() -> None:
    assert shingles("a b c d e f") == shingles("a b c d e f")
    assert shingles("") == set()


def test_near_duplicate_detected() -> None:
    base = " ".join(f"word{index}" for index in range(60))
    first = _record("a", base)
    second = _record("b", base + " extra")
    third = _record("c", " ".join(f"other{index}" for index in range(60)))
    pairs = find_near_duplicates([first, second, third], threshold=0.8)
    assert any(pair.left_id == "a" and pair.right_id == "b" for pair in pairs)
    kept, removed = deduplicate_near([first, second, third], threshold=0.8)
    assert {record.id for record in kept} == {"a", "c"}
    assert removed


def test_unrelated_records_are_kept() -> None:
    first = _record("a", " ".join(f"alpha{index}" for index in range(60)))
    second = _record("b", " ".join(f"beta{index}" for index in range(60)))
    assert find_near_duplicates([first, second], threshold=0.8) == []

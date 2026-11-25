from __future__ import annotations

from cyberlite.data.schema import Record
from cyberlite.data.splits import SplitRatios, assign_split, split_records


def _records(count: int) -> list[Record]:
    return [
        Record(
            id=f"id-{index}",
            source="unit",
            license="Synthetic",
            prompt=f"prompt {index}",
            response=f"response {index} " * 10,
        )
        for index in range(count)
    ]


def test_split_ratios_must_sum_to_one() -> None:
    import pytest

    with pytest.raises(ValueError):
        SplitRatios(0.8, 0.1, 0.2)


def test_split_is_deterministic() -> None:
    records = _records(200)
    first = split_records(records, SplitRatios(0.8, 0.1, 0.1), seed=7)
    second = split_records(records, SplitRatios(0.8, 0.1, 0.1), seed=7)
    assert {key: [item.id for item in value] for key, value in first.items()} == {
        key: [item.id for item in value] for key, value in second.items()
    }


def test_assignment_is_stable() -> None:
    record = _records(1)[0]
    ratios = SplitRatios(0.8, 0.1, 0.1)
    assert assign_split(record, ratios, 1) == assign_split(record, ratios, 1)


def test_split_sizes_are_approximately_correct() -> None:
    splits = split_records(_records(1000), SplitRatios(0.8, 0.1, 0.1), seed=42)
    assert 740 <= len(splits["train"]) <= 860
    assert 70 <= len(splits["validation"]) <= 130
    assert 70 <= len(splits["test"]) <= 130
    assert sum(len(value) for value in splits.values()) == 1000

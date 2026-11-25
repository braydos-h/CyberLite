from __future__ import annotations

from cyberlite.evaluation.seceval import (
    convert_records,
    convert_seceval_record,
    normalize_answer_set,
    strip_choice_prefix,
)


def _record(**overrides):
    payload = {
        "id": "abc",
        "source": "owasp_mastg",
        "question": "Which controls are correct?",
        "choices": ["A: first", "B: second", "C: third", "D: fourth"],
        "answer": "AC",
        "topics": ["WebSecurity", "ApplicationSecurity"],
        "keyword": "TLS",
    }
    payload.update(overrides)
    return payload


def test_strip_choice_prefix() -> None:
    assert strip_choice_prefix("A: first") == "first"
    assert strip_choice_prefix("B. second") == "second"
    assert strip_choice_prefix("third") == "third"


def test_normalize_answer_set() -> None:
    assert normalize_answer_set("CA") == "AC"
    assert normalize_answer_set("AA") == "A"
    assert normalize_answer_set(["A", "C"]) == "AC"
    assert normalize_answer_set(" b ") == "B"


def test_convert_record_preserves_metadata() -> None:
    item = convert_seceval_record(_record())
    assert item is not None
    assert item["id"] == "seceval-abc"
    assert item["task"] == "mcq"
    assert item["source"] == "seceval"
    assert item["choices"] == ["first", "second", "third", "fourth"]
    assert item["answer"] == "AC"
    assert item["metadata"]["topics"] == ["WebSecurity", "ApplicationSecurity"]
    assert item["metadata"]["upstream_id"] == "abc"


def test_convert_records_skips_unusable_items() -> None:
    records = [
        _record(),
        _record(id="empty", answer=""),
        _record(id="rank", answer="E"),
        _record(),
        {"id": "short", "question": "q", "choices": ["A: only"], "answer": "A"},
    ]
    converted, report = convert_records(records)
    assert len(converted) == 1
    assert report["upstream_items"] == 5
    assert report["converted_items"] == 1
    assert report["single_answer_items"] == 0
    assert report["multi_answer_items"] == 1
    assert report["skipped"]["duplicate_id"] == 1
    assert report["skipped"]["unusable_or_empty_answer"] == 3

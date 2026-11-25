from __future__ import annotations

import json
from pathlib import Path

import pytest
from cyberlite.data.schema import Record, load_records, sha256_file, write_jsonl


def test_chat_record_roundtrip(tmp_path: Path) -> None:
    record = Record(
        id="",
        source="unit",
        license="Synthetic",
        messages=[
            {"role": "user", "content": "Question?"},
            {"role": "assistant", "content": "Answer."},
        ],
    )
    path = tmp_path / "out.jsonl"
    assert write_jsonl([record], path) == 1
    loaded = load_records(path)
    assert loaded[0].id == record.id
    assert loaded[0].kind == "chat"
    assert sha256_file(path)


def test_fim_record_requires_middle(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="middle"):
        Record(
            id="x",
            source="unit",
            license="Synthetic",
            prefix="a",
            suffix="b",
            middle="   ",
        )


def test_chat_must_end_with_assistant() -> None:
    with pytest.raises(ValueError, match="end with an assistant"):
        Record(
            id="x",
            source="unit",
            license="Synthetic",
            messages=[{"role": "assistant", "content": "a"}, {"role": "user", "content": "b"}],
        )


def test_unknown_fields_rejected() -> None:
    payload = {
        "id": "x",
        "source": "unit",
        "license": "Synthetic",
        "prompt": "a",
        "response": "b",
        "unexpected": True,
    }
    with pytest.raises(ValueError, match="unknown record fields"):
        Record.from_dict(payload)


def test_invalid_jsonl_reports_line(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    valid = {
        "id": "a",
        "source": "x",
        "license": "MIT",
        "prompt": "p",
        "response": "r" * 100,
    }
    path.write_text(json.dumps(valid) + "\nnot json\n")
    with pytest.raises(ValueError, match=":2:"):
        load_records(path)


def test_record_id_is_content_addressed() -> None:
    first = Record(id="", source="unit", license="Synthetic", prompt="p", response="r")
    second = Record(id="", source="unit", license="Synthetic", prompt="p", response="r")
    assert first.id == second.id


def test_json_output_has_provenance(tmp_path: Path) -> None:
    record = Record(id="", source="unit", license="Synthetic", prompt="p", response="r" * 100)
    path = tmp_path / "out.jsonl"
    write_jsonl([record], path)
    payload = json.loads(path.read_text().strip())
    assert payload["source"] == "unit"
    assert payload["license"] == "Synthetic"
    assert payload["kind"] == "completion"

from __future__ import annotations

import json
from pathlib import Path

from cyberlite.data.evalcheck import validate_eval_file


def _item(identifier: str = "eval-test-001", **overrides) -> dict:
    payload = {
        "id": identifier,
        "suite": "knowledge",
        "domain": "networking",
        "task_family": "technical-qa",
        "difficulty": "intermediate",
        "question": "Which protocol provides an encrypted interactive shell?",
        "choices": [
            {"id": "A", "text": "Telnet"},
            {"id": "B", "text": "SSH"},
            {"id": "C", "text": "FTP"},
        ],
        "answer": "B",
        "answer_choices": ["B"],
        "rationale": "SSH encrypts the session; Telnet and FTP do not.",
        "references": [{"title": "RFC 4251", "url": "https://www.rfc-editor.org/rfc/rfc4251.txt"}],
    }
    payload.update(overrides)
    return payload


def _write(tmp_path: Path, items: list[dict]) -> Path:
    path = tmp_path / "eval.jsonl"
    path.write_text("\n".join(json.dumps(item) for item in items) + "\n")
    return path


def test_valid_eval_file(tmp_path: Path) -> None:
    report = validate_eval_file(_write(tmp_path, [_item()]))
    assert report.ok
    assert report.items == 1
    assert report.suites == {"knowledge": 1}


def test_duplicate_question_detected(tmp_path: Path) -> None:
    second = _item("eval-test-002", question=_item()["question"])
    report = validate_eval_file(_write(tmp_path, [_item(), second]))
    assert not report.ok
    assert any(issue.code == "duplicate_question" for issue in report.issues)


def test_answer_not_in_choices(tmp_path: Path) -> None:
    report = validate_eval_file(_write(tmp_path, [_item(answer_choices=["D"])]))
    assert not report.ok
    assert any(issue.code == "answer_not_in_choices" for issue in report.issues)


def test_training_overlap_reported(tmp_path: Path) -> None:
    item = _item(
        question=(
            "A defender is reviewing TLS configuration and asks which protocol version "
            "must not be negotiated because it is obsolete and insecure in this environment."
        ),
        answer="SSL version 2 and SSL version 3 must not be negotiated.",
    )
    training = [
        "A defender is reviewing TLS configuration and asks which protocol version must not "
        "be negotiated because it is obsolete and insecure in this environment."
    ]
    report = validate_eval_file(_write(tmp_path, [item]), training_texts=training)
    assert report.training_overlap["contaminated_items"] == 1

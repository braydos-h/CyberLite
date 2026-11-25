from __future__ import annotations

import json
from pathlib import Path

import pytest
from cyberlite.data.detection import generate_detection_records, load_detection_rules


def test_library_loads_and_generates() -> None:
    rules = load_detection_rules()
    assert len(rules) >= 8
    records = generate_detection_records(rules)
    assert len(records) == len(rules) * 2
    assert len({record.id for record in records}) == len(records)
    assert all(record.metadata["group"].startswith("detection_rule:") for record in records)
    assert all(record.license == "Synthetic" for record in records)
    assert all(
        record.metadata["task_family"] == "detection-rule-interpretation" for record in records
    )


def test_invalid_yaml_rejected(tmp_path: Path) -> None:
    payload = {
        "rules": [
            {
                "id": "det-bad",
                "title": "bad",
                "purpose": "bad",
                "logsource": "test",
                "level": "low",
                "yaml": "title: bad\nnot_detection: true",
                "tuning": "none",
            }
        ]
    }
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        load_detection_rules(path)


def test_duplicate_rule_rejected(tmp_path: Path) -> None:
    rule = {
        "id": "det-dup",
        "title": "t",
        "purpose": "p",
        "logsource": "l",
        "level": "low",
        "yaml": "title: t\ndetection:\n  selection:\n    a: b\n  condition: selection",
        "tuning": "x",
    }
    path = tmp_path / "rules.json"
    path.write_text(json.dumps({"rules": [rule, rule]}))
    with pytest.raises(ValueError):
        load_detection_rules(path)

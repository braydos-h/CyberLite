from __future__ import annotations

import json
from pathlib import Path

import pytest
from cyberlite.autocomplete.metrics import summarize_feedback


def test_feedback_summary(tmp_path: Path) -> None:
    path = tmp_path / "feedback.jsonl"
    rows = [
        {"accepted": True, "language": "python", "latency_seconds": 0.1},
        {"accepted": True, "language": "python", "latency_seconds": 0.2},
        {"accepted": False, "language": "bash", "latency_seconds": 0.3},
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    summary = summarize_feedback(path)
    assert summary["records"] == 3
    assert summary["accepted"] == 2
    assert summary["acceptance_rate"] == pytest.approx(2 / 3)
    assert summary["by_language"]["python"]["accepted"] == 2
    assert summary["latency_seconds"]["max"] == 0.3
    low, high = summary["acceptance_rate_95ci_wilson"]
    assert 0 <= low <= high <= 1


def test_empty_feedback_rejected(tmp_path: Path) -> None:
    path = tmp_path / "empty.jsonl"
    path.write_text("")
    with pytest.raises(ValueError, match="no feedback"):
        summarize_feedback(path)

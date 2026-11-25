from __future__ import annotations

import json
from pathlib import Path

from cyberlite.data.review import aggregate, load_review


def _scores(value: float = 9.5) -> dict[str, float]:
    keys = (
        "technical_accuracy",
        "source_grounding",
        "completeness",
        "relevance",
        "clarity",
        "practical_usefulness",
        "originality_diversity",
        "small_model_suitability",
    )
    return {key: value for key in keys}


def _write(tmp_path: Path, name: str, reviewer: str, decision: str = "accept", score=9.5) -> Path:
    payload = {
        "reviewer": reviewer,
        "review_type": "technical",
        "artifact": "synthesis-calibration",
        "dataset_version": "v1",
        "items": [
            {
                "record_id": "rec-1",
                "scores": _scores(score),
                "findings": ["verified against primary documentation"]
                if decision == "accept"
                else ["wrong default value"],
                "decision": decision,
            }
        ],
    }
    path = tmp_path / name
    path.write_text(json.dumps(payload))
    return path


def test_accept_threshold(tmp_path: Path) -> None:
    ledger = load_review(_write(tmp_path, "d.json", "agent-D"))
    assert ledger.items[0].accepted


def test_low_technical_score_rejected(tmp_path: Path) -> None:
    payload = json.loads(_write(tmp_path, "d.json", "agent-D").read_text())
    payload["items"][0]["scores"]["technical_accuracy"] = 8.0
    path = tmp_path / "low.json"
    path.write_text(json.dumps(payload))
    ledger = load_review(path)
    assert not ledger.items[0].accepted


def test_revise_needs_finding(tmp_path: Path) -> None:
    payload = json.loads(_write(tmp_path, "d.json", "agent-D", decision="revise").read_text())
    payload["items"][0]["findings"] = []
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(payload))
    try:
        load_review(path)
    except ValueError as exc:
        assert "finding" in str(exc)
    else:
        raise AssertionError("expected a validation error")


def test_disagreement_and_quarantine(tmp_path: Path) -> None:
    first = load_review(_write(tmp_path, "d.json", "agent-D", "accept", 9.5))
    second = load_review(_write(tmp_path, "e.json", "agent-E", "quarantine", 7.0))
    grouped, summary = aggregate([first, second])
    assert grouped["rec-1"].decision == "quarantine"
    assert grouped["rec-1"].disagreements
    assert summary["disagreement_rate"] == 1.0


def test_missing_rubric_dimension_rejected(tmp_path: Path) -> None:
    payload = json.loads(_write(tmp_path, "d.json", "agent-D").read_text())
    del payload["items"][0]["scores"]["clarity"]
    path = tmp_path / "missing.json"
    path.write_text(json.dumps(payload))
    try:
        load_review(path)
    except ValueError as exc:
        assert "missing scores" in str(exc)
    else:
        raise AssertionError("expected a validation error")

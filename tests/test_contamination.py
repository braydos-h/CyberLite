from __future__ import annotations

from pathlib import Path

from cyberlite.data.contamination import ContaminationIndex, check_contamination, ngram_fingerprints
from cyberlite.data.schema import Record, write_jsonl


def test_ngram_fingerprints_require_length() -> None:
    assert ngram_fingerprints("too short", n=13) == set()


def test_ngram_normalization_is_case_and_punctuation_insensitive() -> None:
    left = " ".join(["word"] * 20)
    right = ", ".join(["WORD"] * 20)
    assert ngram_fingerprints(left) == ngram_fingerprints(right)


def test_contamination_index_overlap() -> None:
    index = ContaminationIndex()
    index.add_text(" ".join(["networking", "security", "guidance"] * 10))
    assert index.overlap(" ".join(["networking", "security", "guidance"] * 10)) == 1.0
    assert index.is_contaminated(" ".join(["networking", "security", "guidance"] * 10))
    assert index.size > 0


def test_check_contamination_removes_verbatim(tmp_path: Path) -> None:
    shared = " ".join(["vulnerability", "remediation", "verification"] * 30)
    eval_record = Record(id="eval", source="eval", license="Synthetic", prompt="q", response=shared)
    eval_path = tmp_path / "eval.jsonl"
    write_jsonl([eval_record], eval_path)
    train_record = Record(
        id="train", source="train", license="Synthetic", prompt="q", response=shared
    )
    kept, findings = check_contamination([train_record], [str(eval_path)])
    assert not kept
    assert findings[0]["id"] == "train"
    assert findings[0]["overlap"] > 0.9


def test_check_contamination_keeps_unrelated(tmp_path: Path) -> None:
    eval_record = Record(
        id="eval",
        source="eval",
        license="Synthetic",
        prompt="q",
        response=" ".join(["authentication", "logging"] * 30),
    )
    eval_path = tmp_path / "eval.jsonl"
    write_jsonl([eval_record], eval_path)
    train_record = Record(
        id="train",
        source="train",
        license="Synthetic",
        prompt="q",
        response=" ".join(["firewall", "segmentation"] * 30),
    )
    kept, findings = check_contamination([train_record], [str(eval_path)])
    assert kept == [train_record]
    assert findings == []

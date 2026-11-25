from __future__ import annotations

from cyberlite.data.config import QualityThresholds
from cyberlite.data.quality import (
    HeuristicTokenCounter,
    assess_record,
    load_token_counter,
    token_length_report,
)
from cyberlite.data.schema import Record


def _record(
    response: str, *, prompt: str = "Explain the defensive control.", meta: dict | None = None
) -> Record:
    return Record(
        id="",
        source="unit",
        license="Synthetic",
        prompt=prompt,
        response=response,
        url="https://example.invalid/source",
        metadata=meta or {"upstream_id": "u1", "source_version": "v1"},
    )


def test_empty_and_short_responses_rejected() -> None:
    thresholds = QualityThresholds(min_response_chars=50)
    empty = _record("placeholder")
    empty.response = ""
    assert not assess_record(empty, thresholds).accepted
    assert not assess_record(_record("too short"), thresholds).accepted


def test_boilerplate_and_navigation_rejected() -> None:
    text = "\n".join(
        ["[Home](/)", "[Next](/next)", "Back to top", "Copyright 2026 Example", ""] * 10
    )
    assessment = assess_record(_record(text), QualityThresholds(min_response_chars=10))
    assert not assessment.accepted
    assert "boilerplate_heavy" in assessment.rejection_reasons


def test_pii_and_unredacted_secret_rejected() -> None:
    assessment = assess_record(
        _record("Contact 123-45-6789 or use -----BEGIN PRIVATE KEY----- material. " * 4),
        QualityThresholds(min_response_chars=10, min_unique_token_ratio=0),
    )
    assert not assessment.accepted
    assert {"pii_detected", "secret_not_redacted"} & set(assessment.rejection_reasons)


def test_broken_metadata_is_reported() -> None:
    record = Record(
        id="",
        source="nist_nvd",
        license="Public-Domain",
        prompt="Summarize CVE-2024-0001.",
        response="A sufficiently long factual vulnerability description without a CVE identifier. "
        * 4,
        metadata={},
    )
    assessment = assess_record(record, QualityThresholds(), required_metadata=("cve_id",))
    assert not assessment.accepted
    assert "broken_source_metadata" in assessment.rejection_reasons


def test_low_information_and_link_heavy() -> None:
    text = " ".join(["https://example.invalid/a"] * 40)
    assessment = assess_record(
        _record(text),
        QualityThresholds(min_response_chars=10, min_unique_token_ratio=0.5, max_url_ratio=0.1),
    )
    assert not assessment.accepted
    assert "low_information" in assessment.rejection_reasons
    assert "link_heavy" in assessment.rejection_reasons


def test_absolute_claim_is_a_warning_by_default() -> None:
    assessment = assess_record(
        _record("This control always prevents every attack and is 100% safe. " * 4),
        QualityThresholds(min_response_chars=10),
    )
    assert assessment.accepted
    assert "unsupported_absolute_claim" in assessment.warnings


def test_token_length_report_is_labeled_estimate() -> None:
    records = [_record("defensive " * 100), _record("short response " * 20)]
    report = token_length_report(records, HeuristicTokenCounter(), max_sequence_tokens=64)
    assert report["tokenizer"] == "heuristic(chars/4)"
    assert report["tokens"]["p50"] > 0
    assert report["truncation"]["over_limit"] >= 1
    counter, info = load_token_counter("definitely-not-a-real-model-xyz", local_only=True)
    assert info["estimated"] is True
    assert counter.count("hello") >= 1

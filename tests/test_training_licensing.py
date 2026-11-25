from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from cyberlite.training.dataset import build_datasets
from cyberlite.training.licensing import (
    LicenseValidationError,
    reconcile_license_policies,
    validate_training_licenses,
)


def _record(
    identifier: str,
    license_id: str,
    *,
    source: str = "unit",
    metadata: dict | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=identifier,
        source=source,
        license=license_id,
        task="knowledge",
        metadata=metadata or {},
    )


def _validate(records, **overrides):
    kwargs = {
        "split": "train",
        "allowed_licenses": ["Public-Domain", "MITRE-ATTACK", "Synthetic"],
        "require_license": True,
        "require_resolved_licenses": True,
        "allow_unresolved_licenses": [],
        "profile": "research",
        "evaluation_ids": (),
    }
    kwargs.update(overrides)
    return validate_training_licenses(records, **kwargs)


def test_resolved_allowed_license_passes() -> None:
    result = _validate([_record("a", "Public-Domain")])
    assert result.ok
    assert result.accepted_records == 1
    assert result.rejected_records == 0
    assert result.license_counts == {"Public-Domain": 1}


def test_missing_license_is_rejected() -> None:
    result = _validate([_record("a", "")])
    assert not result.ok
    assert result.rejected[0].reason == "missing_license"


def test_disallowed_license_is_rejected() -> None:
    result = _validate([_record("a", "GPL-3.0-or-later")])
    assert not result.ok
    assert result.rejected[0].reason == "disallowed_license"


def test_unknown_license_is_rejected_even_if_allow_listed() -> None:
    result = _validate(
        [_record("a", "Proprietary-1.0")],
        allowed_licenses=["Proprietary-1.0"],
        require_resolved_licenses=False,
    )
    assert not result.ok
    assert result.rejected[0].reason == "unknown_license"


def test_prohibited_use_is_rejected() -> None:
    result = _validate(
        [_record("a", "See-source")],
        allowed_licenses=["See-source"],
        require_resolved_licenses=False,
    )
    assert not result.ok
    assert result.rejected[0].reason == "prohibited_use"


def test_evaluation_only_license_and_metadata_are_rejected() -> None:
    license_result = _validate(
        [_record("a", "CC-BY-NC-SA-4.0")],
        allowed_licenses=["CC-BY-NC-SA-4.0"],
        require_resolved_licenses=False,
    )
    assert not license_result.ok
    assert license_result.rejected[0].reason == "evaluation_only"

    metadata_result = _validate([_record("b", "Public-Domain", metadata={"evaluation_only": True})])
    assert not metadata_result.ok
    assert metadata_result.rejected[0].reason == "evaluation_only"

    source_result = _validate(
        [_record("c", "Public-Domain", source="seceval")],
    )
    assert not source_result.ok
    assert source_result.rejected[0].reason == "evaluation_only"


def test_evaluation_id_match_is_rejected() -> None:
    result = _validate(
        [_record("probe-mcq-01", "Public-Domain")],
        evaluation_ids={"probe-mcq-01"},
    )
    assert not result.ok
    assert result.rejected[0].reason == "evaluation_only"


def test_unresolved_license_requires_explicit_acknowledgement() -> None:
    records = [_record("a", "MITRE-ATTACK")]
    blocked = _validate(records)
    assert not blocked.ok
    assert blocked.rejected[0].reason == "unresolved_license"
    assert "MITRE-ATTACK" in blocked.unresolved_licenses

    acknowledged = _validate(records, allow_unresolved_licenses=["MITRE-ATTACK"])
    assert acknowledged.ok
    assert acknowledged.unresolved_licenses


def test_smoke_profile_reports_but_does_not_block_unresolved() -> None:
    result = _validate(
        [_record("a", "Synthetic")],
        profile="smoke",
        require_resolved_licenses=False,
        allowed_licenses=["Synthetic"],
    )
    assert result.ok
    assert result.unresolved_licenses


def test_reconciliation_does_not_auto_approve() -> None:
    reconciliation = reconcile_license_policies(
        ingestion_licenses=["Public-Domain", "MITRE-ATTACK"],
        training_licenses=["Public-Domain", "MITRE-ATTACK"],
    )
    assert reconciliation.ingestion_only == []
    assert reconciliation.training_only == []
    assert "MITRE-ATTACK" in reconciliation.unresolved_in_training


def _write_records(path: Path, license_id: str, prefix: str) -> None:
    path.write_text(
        json.dumps(
            {
                "id": f"{prefix}-1",
                "source": "unit",
                "license": license_id,
                "task": "knowledge",
                "prompt": "Question?",
                "response": "A concrete, verifiable answer.",
                "split": prefix,
                "url": "https://example.invalid",
                "metadata": {"source_version": "v1", "upstream_id": f"u-{prefix}"},
            }
        )
        + "\n",
        encoding="utf-8",
    )


def test_build_datasets_enforces_train_and_validation_licenses(
    fake_tokenizer, tmp_path: Path
) -> None:
    train = tmp_path / "train.jsonl"
    validation = tmp_path / "validation.jsonl"
    _write_records(train, "Public-Domain", "train")
    _write_records(validation, "Public-Domain", "validation")

    train_dataset, validation_dataset = build_datasets(
        fake_tokenizer,
        train_file=train,
        validation_file=validation,
        max_seq_length=256,
        allowed_licenses=["Public-Domain"],
        require_resolved_licenses=False,
    )
    assert len(train_dataset) == 1
    assert validation_dataset is not None
    assert train_dataset.license_validation["accepted_records"] == 1
    assert validation_dataset.license_validation["accepted_records"] == 1

    bad_train = tmp_path / "bad-train.jsonl"
    _write_records(bad_train, "CC-BY-NC-SA-4.0", "train")
    with pytest.raises(LicenseValidationError, match="evaluation_only"):
        build_datasets(
            fake_tokenizer,
            train_file=bad_train,
            validation_file=validation,
            max_seq_length=256,
            allowed_licenses=["CC-BY-NC-SA-4.0", "Public-Domain"],
            require_resolved_licenses=False,
        )

    bad_validation = tmp_path / "bad-validation.jsonl"
    _write_records(bad_validation, "CC-BY-NC-SA-4.0", "validation")
    with pytest.raises(LicenseValidationError, match="validation split"):
        build_datasets(
            fake_tokenizer,
            train_file=train,
            validation_file=bad_validation,
            max_seq_length=256,
            allowed_licenses=["CC-BY-NC-SA-4.0", "Public-Domain"],
            require_resolved_licenses=False,
        )


def test_build_datasets_never_silently_skips_validation(fake_tokenizer, tmp_path: Path) -> None:
    train = tmp_path / "train.jsonl"
    _write_records(train, "Public-Domain", "train")
    with pytest.raises(FileNotFoundError, match="validation data not found"):
        build_datasets(
            fake_tokenizer,
            train_file=train,
            validation_file=tmp_path / "missing.jsonl",
            max_seq_length=256,
            allowed_licenses=["Public-Domain"],
            require_resolved_licenses=False,
        )
    with pytest.raises(FileNotFoundError, match="validation data is required"):
        build_datasets(
            fake_tokenizer,
            train_file=train,
            validation_file=None,
            max_seq_length=256,
            require_validation=True,
            allowed_licenses=["Public-Domain"],
            require_resolved_licenses=False,
        )

"""Fail-closed license policy for supervised training data.

Ingestion may accept a broader set of licenses than training. This module is the
training gate: it requires an explicit license on every record, checks that the
license is both allow-listed and reviewed for training, rejects evaluation-only
material, and refuses licenses whose guidance still contains unresolved
questions unless the caller names each one explicitly.

Public accessibility is not training permission. An allow-list entry is a
project decision, not a replacement for the unresolved legal questions recorded
in ``data/manifests/*/license_report.md``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Literal

from cyberlite.data.cleaning import normalize_license
from cyberlite.data.licensing import is_evaluation_only
from cyberlite.data.reports import DEFAULT_GUIDANCE, LICENSE_GUIDANCE

TRAINING_USE = "training"

LicenseProfile = Literal["research", "smoke", "custom"]


@dataclass
class LicenseIssue:
    record_id: str
    source: str
    license: str
    reason: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {
            "record_id": self.record_id,
            "source": self.source,
            "license": self.license,
            "reason": self.reason,
            "detail": self.detail,
        }


@dataclass
class LicenseValidationResult:
    split: str
    profile: LicenseProfile
    checked_records: int = 0
    accepted_records: int = 0
    rejected_records: int = 0
    license_counts: dict[str, int] = field(default_factory=dict)
    rejected: list[LicenseIssue] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unresolved_licenses: dict[str, list[str]] = field(default_factory=dict)
    allowed_licenses: list[str] = field(default_factory=list)
    allow_unresolved_licenses: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.rejected

    def to_dict(self, *, issue_limit: int = 50) -> dict[str, Any]:
        return {
            "split": self.split,
            "profile": self.profile,
            "checked_records": self.checked_records,
            "accepted_records": self.accepted_records,
            "rejected_records": self.rejected_records,
            "license_counts": dict(sorted(self.license_counts.items())),
            "allowed_licenses": sorted(self.allowed_licenses),
            "allow_unresolved_licenses": sorted(self.allow_unresolved_licenses),
            "unresolved_licenses": {
                license_id: sorted(questions)
                for license_id, questions in sorted(self.unresolved_licenses.items())
            },
            "rejected_examples": [issue.to_dict() for issue in self.rejected[:issue_limit]],
            "rejected_truncated": max(0, len(self.rejected) - issue_limit),
            "warnings": self.warnings,
        }


class LicenseValidationError(ValueError):
    """Raised when training data fails the configured license policy."""

    def __init__(self, result: LicenseValidationResult) -> None:
        self.result = result
        examples = "; ".join(
            f"{issue.record_id} ({issue.license or 'missing'}): {issue.reason}"
            for issue in result.rejected[:5]
        )
        remainder = len(result.rejected) - 5
        suffix = f"; and {remainder} more" if remainder > 0 else ""
        super().__init__(
            f"{result.split} split rejected {result.rejected_records} of "
            f"{result.checked_records} records by the training license policy: "
            f"{examples}{suffix}. Inspect the full report with --preflight."
        )


def _guidance(license_id: str) -> dict[str, Any]:
    return LICENSE_GUIDANCE.get(normalize_license(license_id), DEFAULT_GUIDANCE)


def validate_training_licenses(
    records: Iterable[Any],
    *,
    split: str,
    allowed_licenses: Iterable[str],
    require_license: bool = True,
    require_resolved_licenses: bool = True,
    allow_unresolved_licenses: Iterable[str] = (),
    profile: LicenseProfile = "research",
    evaluation_ids: Iterable[str] = (),
) -> LicenseValidationResult:
    """Validate every record and return a machine-readable report.

    The function never mutates records and never silently drops a rejected row.
    Callers must raise :class:`LicenseValidationError` when ``result.ok`` is
    false.
    """

    allowed = {normalize_license(item) for item in allowed_licenses if str(item).strip()}
    acknowledged = {
        normalize_license(item) for item in allow_unresolved_licenses if str(item).strip()
    }
    eval_ids = {str(item) for item in evaluation_ids}
    result = LicenseValidationResult(
        split=split,
        profile=profile,
        allowed_licenses=sorted(allowed),
        allow_unresolved_licenses=sorted(acknowledged),
    )

    seen_unresolved: dict[str, set[str]] = {}
    for record in records:
        result.checked_records += 1
        record_id = str(getattr(record, "id", "") or "<missing-id>")
        source = str(getattr(record, "source", "") or "<missing-source>")
        raw_license = str(getattr(record, "license", "") or "").strip()
        license_id = normalize_license(raw_license)
        rejection: tuple[str, str] | None = None

        eval_only, eval_detail = is_evaluation_only(record)
        if eval_only:
            rejection = ("evaluation_only", eval_detail)
        elif record_id in eval_ids:
            rejection = ("evaluation_only", "record identifier appears in a local evaluation file")
        elif not license_id:
            if require_license:
                rejection = ("missing_license", "record has no license identifier")
            else:
                result.warnings.append(
                    f"{record_id}: missing license accepted by require_license=false"
                )
        elif not allowed and require_license:
            rejection = (
                "disallowed_license",
                "no training licenses are configured in data.allowed_licenses",
            )
        elif allowed and license_id not in allowed:
            rejection = ("disallowed_license", "license is not in data.allowed_licenses")
        else:
            guidance = _guidance(license_id)
            if guidance is DEFAULT_GUIDANCE:
                rejection = ("unknown_license", "license has no reviewed guidance entry")
            elif TRAINING_USE not in (guidance.get("permitted_uses") or []):
                rejection = ("prohibited_use", "reviewed guidance does not permit training")
            else:
                unresolved = list(guidance.get("unresolved") or [])
                if unresolved:
                    seen_unresolved[license_id] = set(unresolved)
                    if require_resolved_licenses and license_id not in acknowledged:
                        rejection = (
                            "unresolved_license",
                            "license has unresolved questions; acknowledge it explicitly "
                            "with data.allow_unresolved_licenses after review",
                        )

        result.license_counts[license_id or "<missing>"] = (
            result.license_counts.get(license_id or "<missing>", 0) + 1
        )
        if rejection is None:
            result.accepted_records += 1
        else:
            result.rejected_records += 1
            result.rejected.append(
                LicenseIssue(
                    record_id=record_id,
                    source=source,
                    license=license_id,
                    reason=rejection[0],
                    detail=rejection[1],
                )
            )

    result.unresolved_licenses = {
        license_id: sorted(questions) for license_id, questions in seen_unresolved.items()
    }
    if profile == "smoke":
        result.warnings.append(
            "smoke profile: unresolved licensing questions are reported but do not block "
            "the synthetic pipeline test; smoke output is not a research result"
        )
    return result


@dataclass
class LicensePolicyReconciliation:
    ingestion_licenses: list[str]
    training_licenses: list[str]
    ingestion_only: list[str]
    training_only: list[str]
    unresolved_in_training: dict[str, list[str]]
    unknown_in_training: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ingestion_licenses": self.ingestion_licenses,
            "training_licenses": self.training_licenses,
            "ingestion_only": self.ingestion_only,
            "training_only": self.training_only,
            "unresolved_in_training": {
                license_id: sorted(questions)
                for license_id, questions in sorted(self.unresolved_in_training.items())
            },
            "unknown_in_training": self.unknown_in_training,
        }


def reconcile_license_policies(
    ingestion_licenses: Iterable[str], training_licenses: Iterable[str]
) -> LicensePolicyReconciliation:
    """Compare ingestion and training allow-lists without approving anything.

    Ingestion-only licenses are normal (a corpus may permit research access
    without permitting training). Training-only licenses are reported so a
    config cannot quietly widen the ingestion policy.
    """

    ingestion = {normalize_license(item) for item in ingestion_licenses if str(item).strip()}
    training = {normalize_license(item) for item in training_licenses if str(item).strip()}
    unresolved: dict[str, list[str]] = {}
    unknown: list[str] = []
    for license_id in sorted(training):
        guidance = _guidance(license_id)
        if guidance is DEFAULT_GUIDANCE:
            unknown.append(license_id)
        elif guidance.get("unresolved"):
            unresolved[license_id] = list(guidance["unresolved"])
    return LicensePolicyReconciliation(
        ingestion_licenses=sorted(ingestion),
        training_licenses=sorted(training),
        ingestion_only=sorted(ingestion - training),
        training_only=sorted(training - ingestion),
        unresolved_in_training=unresolved,
        unknown_in_training=unknown,
    )

"""CPU-only training preflight.

Preflight answers two different questions and never conflates them:

* **Software readiness** — would ``scripts/train.py`` pass configuration, data,
  integrity, revision, and licensing gates before loading a model?
* **Research readiness** — is the run also supported by the human review,
  external pre-registration, and resolved licensing that the project requires?

It never downloads a model, starts training, or fabricates an approval.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cyberlite.config import (
    PINNED_QWEN35_MODEL_ID,
    PINNED_QWEN35_REVISION,
    ExperimentConfig,
)
from cyberlite.data.integrity import (
    DatasetIntegrityReport,
    evaluation_ids_from_directory,
    verify_dataset,
)
from cyberlite.hardware import detect_hardware
from cyberlite.training.licensing import (
    LicenseValidationResult,
    reconcile_license_policies,
    validate_training_licenses,
)
from cyberlite.training.model import looks_like_commit

PREREGISTRATION_PATH = Path("docs/preregistration.md")


@dataclass
class PreflightBlocker:
    code: str
    severity: str  # "software" or "research"
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
        }
        if self.details:
            payload["details"] = self.details
        return payload


@dataclass
class PreflightReport:
    config_path: str | None
    config_sha256: str
    config_fingerprint: str
    profile: str
    software_ready: bool
    research_ready: bool
    exit_code: int
    checks: dict[str, Any] = field(default_factory=dict)
    blockers: list[PreflightBlocker] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    dataset: dict[str, Any] = field(default_factory=dict)
    licenses: dict[str, Any] = field(default_factory=dict)
    model: dict[str, Any] = field(default_factory=dict)
    hardware: dict[str, Any] = field(default_factory=dict)
    plan: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "preflight": "cyberlite-training",
            "schema_version": 1,
            "generated_at": datetime.now(tz=UTC).isoformat(),
            "config_path": self.config_path,
            "config_sha256": self.config_sha256,
            "config_fingerprint": self.config_fingerprint,
            "profile": self.profile,
            "software_ready": self.software_ready,
            "research_ready": self.research_ready,
            "exit_code": self.exit_code,
            "checks": self.checks,
            "blockers": [blocker.to_dict() for blocker in self.blockers],
            "warnings": self.warnings,
            "next_actions": self.next_actions,
            "dataset": self.dataset,
            "licenses": self.licenses,
            "model": self.model,
            "hardware": self.hardware,
            "plan": self.plan,
        }


def preregistration_status(path: Path = PREREGISTRATION_PATH) -> dict[str, Any]:
    if not path.is_file():
        return {
            "path": str(path),
            "externally_registered": False,
            "status": "missing",
            "note": "pre-registration document is missing",
        }
    text = path.read_text(encoding="utf-8", errors="ignore")
    lowered = text.lower()
    externally_registered = (
        "not externally registered" not in lowered
        and "status: draft" not in lowered
        and bool(re.search(r"(osf\.io/|zenodo\.org/record/|arxiv\.org/abs/|doi:\s*10\.)", lowered))
    )
    status = "registered" if externally_registered else "draft"
    return {
        "path": str(path),
        "externally_registered": externally_registered,
        "status": status,
        "note": (
            "external registration identifier is recorded"
            if externally_registered
            else "document is a draft and is not externally registered"
        ),
    }


def _dataset_profile(config: ExperimentConfig) -> str:
    return "smoke" if config.training.smoke else "research"


def _resolve(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (Path.cwd() / path)


def _add_issues(
    report: PreflightReport,
    integrity: DatasetIntegrityReport,
) -> None:
    for issue in integrity.issues:
        if issue.severity == "error":
            report.blockers.append(
                PreflightBlocker(
                    code=issue.check,
                    severity="software",
                    message=issue.message,
                    details=issue.to_dict(),
                )
            )
        else:
            report.warnings.append(issue.message)


def _license_blockers(
    report: PreflightReport,
    result: LicenseValidationResult,
    *,
    require_resolved: bool,
) -> None:
    if not result.ok:
        reason_counts: dict[str, int] = {}
        for issue in result.rejected:
            reason_counts[issue.reason] = reason_counts.get(issue.reason, 0) + 1
        report.blockers.append(
            PreflightBlocker(
                code="license_validation_failed",
                severity="software",
                message=(
                    f"{result.split} split failed training license validation: "
                    + ", ".join(f"{key}={value}" for key, value in sorted(reason_counts.items()))
                ),
                details=result.to_dict(),
            )
        )
    if result.unresolved_licenses:
        message = "licenses with unresolved questions remain: " + ", ".join(
            sorted(result.unresolved_licenses)
        )
        if require_resolved:
            report.blockers.append(
                PreflightBlocker(
                    code="unresolved_license",
                    severity="research",
                    message=message,
                    details={"unresolved": result.unresolved_licenses},
                )
            )
        else:
            report.warnings.append(message)


def run_preflight(
    config: ExperimentConfig,
    *,
    config_path: str | Path | None = None,
) -> PreflightReport:
    """Run all CPU-only checks and return a structured readiness report."""

    profile = _dataset_profile(config)
    report = PreflightReport(
        config_path=str(config_path) if config_path else getattr(config, "_source_path", None),
        config_sha256=config.sha256(),
        config_fingerprint=config.training_fingerprint(),
        profile=profile,
        software_ready=True,
        research_ready=True,
        exit_code=0,
    )
    report.checks["configuration"] = {
        "status": "pass",
        "schema_version": config.schema_version,
        "run": config.run.name,
        "profile": profile,
        "dataset_paths": {
            "train": config.data.train_file,
            "validation": config.data.validation_file,
            "test": config.data.test_file,
            "manifest": config.data.manifest_file,
        },
        "expected_dataset_version": config.data.dataset_version,
        "expected_split_counts": config.data.expected_split_counts,
    }

    if profile != "smoke":
        smoke_parts = [
            name
            for name, value in (
                ("train", config.data.train_file),
                ("validation", config.data.validation_file),
                ("test", config.data.test_file),
                ("manifest", config.data.manifest_file),
            )
            if value and any(part in {"smoke", "ci-smoke"} for part in Path(value).parts)
        ]
        if smoke_parts:
            report.blockers.append(
                PreflightBlocker(
                    code="smoke_dataset_in_research_run",
                    severity="software",
                    message=(
                        "research training is configured with smoke-test paths: "
                        + ", ".join(smoke_parts)
                    ),
                )
            )

    eval_dir = _resolve("data/evaluation")
    integrity: DatasetIntegrityReport | None = None
    try:
        integrity = verify_dataset(
            train_file=_resolve(config.data.train_file),
            validation_file=(
                _resolve(config.data.validation_file) if config.data.validation_file else None
            ),
            test_file=_resolve(config.data.test_file) if config.data.test_file else None,
            manifest_file=(
                _resolve(config.data.manifest_file) if config.data.manifest_file else None
            ),
            expected_version=config.data.dataset_version,
            expected_split_counts=config.data.expected_split_counts,
            profile=profile,  # type: ignore[arg-type]
            require_manifest=config.data.require_manifest,
            require_provenance=config.data.require_provenance,
            require_contamination_screen=config.data.require_contamination_screen,
            eval_dir=eval_dir,
            dedup_threshold=3,
            base_dir=Path.cwd(),
        )
    except Exception as exc:
        report.blockers.append(
            PreflightBlocker(
                code="dataset_verification_error",
                severity="software",
                message=f"dataset verification could not run: {exc}",
            )
        )

    if integrity is not None:
        _add_issues(report, integrity)
        report.dataset = integrity.to_dict()
        report.checks["dataset_availability"] = {
            "status": "pass" if integrity.ok else "fail",
            "manifest_path": integrity.manifest_path,
            "split_counts": integrity.split_counts,
            "expected_split_counts": integrity.expected_split_counts,
            "files": integrity.files,
        }
        report.checks["manifest_integrity"] = {
            "status": "pass" if integrity.ok else "fail",
            "dataset_name": integrity.dataset_name,
            "dataset_version": integrity.dataset_version,
            "expected_version": integrity.expected_version,
            "manifest_sha256": integrity.manifest_sha256,
            "duplicate_id_count": len(integrity.duplicate_ids),
            "cross_split_leakage_count": len(integrity.cross_split_leakage),
            "evaluation_contamination": {
                "checked": integrity.evaluation_contamination.get("checked", False),
                "finding_count": integrity.evaluation_contamination.get("finding_count", 0),
                "sets": integrity.evaluation_contamination.get("sets", []),
            },
            "errors": [issue.to_dict() for issue in integrity.errors],
        }
        report.checks["dataset_statistics"] = {
            "status": "pass",
            "record_count": sum(integrity.split_counts.values()),
            "split_counts": integrity.split_counts,
            "source_counts": integrity.source_counts,
            "license_counts": integrity.license_counts,
            "task_counts": integrity.task_counts,
            "kind_counts": integrity.kind_counts,
            "provenance_gaps": integrity.provenance_gaps,
            "token_audit": {
                "from_manifest": (integrity.manifest.get("audit") or {}).get("token_truncation"),
                "token_lengths": (integrity.manifest.get("quality") or {}).get("token_lengths"),
            },
        }

        evaluation_ids = evaluation_ids_from_directory(eval_dir)
        license_checks: dict[str, Any] = {}
        for split in ("train", "validation"):
            records = integrity.records.get(split, [])
            result = validate_training_licenses(
                records,
                split=split,
                allowed_licenses=config.data.allowed_licenses,
                require_license=config.data.require_license,
                require_resolved_licenses=(
                    config.data.require_resolved_licenses and profile != "smoke"
                ),
                allow_unresolved_licenses=config.data.allow_unresolved_licenses,
                profile=profile,  # type: ignore[arg-type]
                evaluation_ids=evaluation_ids,
            )
            license_checks[split] = result.to_dict()
            report.licenses[split] = result.to_dict()
            _license_blockers(
                report,
                result,
                require_resolved=(config.data.require_resolved_licenses and profile != "smoke"),
            )
        reconciliation = reconcile_license_policies(
            (integrity.manifest.get("options") or {}).get("allowed_licenses") or [],
            config.data.allowed_licenses,
        )
        license_checks["reconciliation"] = reconciliation.to_dict()
        report.licenses["reconciliation"] = reconciliation.to_dict()
        report.checks["license_compliance"] = {
            "status": (
                "pass"
                if all(
                    not report.licenses.get(split, {}).get("rejected_records")
                    for split in ("train", "validation")
                )
                else "fail"
            ),
            **license_checks,
        }

    revision = config.model.revision
    revision_check: dict[str, Any] = {
        "model_id": config.model.id,
        "requested_revision": revision,
        "baseline_reference": PINNED_QWEN35_REVISION,
        "baseline_model": PINNED_QWEN35_MODEL_ID,
        "matches_baseline": (
            config.model.id == PINNED_QWEN35_MODEL_ID and revision == PINNED_QWEN35_REVISION
        ),
        "require_pinned_revision": config.model.require_pinned_revision,
        "matched_baseline": config.model.matched_baseline,
    }
    revision_blocked = False
    if config.model.require_pinned_revision and not revision:
        revision_check["status"] = "fail"
        revision_blocked = True
        report.blockers.append(
            PreflightBlocker(
                code="model_revision_missing",
                severity="software",
                message=(
                    "model.require_pinned_revision=true but model.revision is unset; "
                    f"pin {PINNED_QWEN35_REVISION}"
                ),
            )
        )
    elif (
        config.model.matched_baseline
        and config.model.id == PINNED_QWEN35_MODEL_ID
        and revision != PINNED_QWEN35_REVISION
    ):
        revision_check["status"] = "fail"
        revision_blocked = True
        report.blockers.append(
            PreflightBlocker(
                code="model_revision_mismatch",
                severity="software",
                message=(
                    f"matched experiment requests revision {revision!r}, but the "
                    f"registered baseline is {PINNED_QWEN35_REVISION}"
                ),
            )
        )
    elif revision and not looks_like_commit(revision):
        report.warnings.append(
            f"model.revision={revision!r} is not a full 40-character commit; "
            "a moving tag can change during a matched experiment"
        )
        revision_check["status"] = "warn"
    else:
        revision_check["status"] = "pass"
    revision_check["blocked"] = revision_blocked
    report.model = revision_check
    report.checks["model_revision"] = revision_check

    hardware = detect_hardware()
    try:
        from cyberlite.training.trainer import build_plan

        plan = build_plan(config, hardware)
        plan_payload = plan.to_dict()
        compatibility = {
            "status": "pass",
            "device": plan.device,
            "quantization_bits": plan.quantization_bits,
            "warnings": plan.warnings,
            "fit_by_vram": plan.fit_by_vram,
        }
        if plan.warnings:
            compatibility["status"] = "warn"
            report.warnings.extend(plan.warnings)
            if config.model.device == "cuda" and not hardware.cuda_available:
                compatibility["status"] = "fail"
                report.blockers.append(
                    PreflightBlocker(
                        code="hardware_incompatible",
                        severity="software",
                        message="model.device=cuda but no CUDA device is available",
                    )
                )
        report.plan = plan_payload
        report.hardware = {
            "status": compatibility["status"],
            "detected": hardware.to_dict(),
            "compatibility": compatibility,
            "recommendation": plan.recommendation,
        }
        report.checks["hardware"] = report.hardware
    except Exception as exc:
        report.warnings.append(f"hardware planning estimate failed: {exc}")
        report.checks["hardware"] = {"status": "warn", "error": str(exc)}

    manual_review = (integrity.manifest.get("manual_review") or {}) if integrity else {}
    review_complete = bool(manual_review.get("completed"))
    report.checks["manual_review"] = {
        "status": "pass" if review_complete else "pending",
        "completed": review_complete,
        "reviewed_records": manual_review.get("reviewed_records", 0),
        "note": manual_review.get("note"),
    }
    if not review_complete:
        report.blockers.append(
            PreflightBlocker(
                code="manual_review_pending",
                severity="research",
                message="manual quality/safety review of the training corpus is not complete",
            )
        )

    prereg = preregistration_status()
    report.checks["preregistration"] = prereg
    if not prereg["externally_registered"]:
        report.blockers.append(
            PreflightBlocker(
                code="preregistration_not_external",
                severity="research",
                message="hypotheses and analysis plan are not externally pre-registered",
                details=prereg,
            )
        )

    if profile == "smoke":
        report.blockers.append(
            PreflightBlocker(
                code="smoke_not_research",
                severity="research",
                message="this is an explicitly identified smoke pipeline test, not a research run",
            )
        )

    report.software_ready = not any(blocker.severity == "software" for blocker in report.blockers)
    report.research_ready = report.software_ready and not report.blockers
    if report.research_ready:
        report.exit_code = 0
    elif report.software_ready:
        report.exit_code = 1
    else:
        report.exit_code = 3

    if not report.software_ready:
        report.next_actions.append("Fix every software blocker before invoking training.")
    if not review_complete:
        report.next_actions.append(
            "Complete the stratified manual review in data/manifests/pilot-v2/audit/ "
            "and record the result; do not mark it complete without reviewers."
        )
    if not prereg["externally_registered"]:
        report.next_actions.append(
            "Register docs/preregistration.md externally (OSF, Zenodo, or arXiv v1) and "
            "record the identifier."
        )
    unresolved = sorted(
        {
            license_id
            for split in ("train", "validation")
            for license_id in (report.licenses.get(split, {}).get("unresolved_licenses") or {})
        }
    )
    if unresolved:
        report.next_actions.append(
            "Obtain a documented licensing decision for: " + ", ".join(unresolved)
        )
    if report.software_ready and not report.research_ready and not unresolved:
        report.next_actions.append(
            "Resolve the remaining research blockers; software checks are ready."
        )
    return report

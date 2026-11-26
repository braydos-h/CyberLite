"""Frozen-manifest integrity checks for training datasets.

The checks are intentionally read-only: a failing dataset is reported, never
repaired. Regenerating a manifest to make a mismatch disappear would destroy the
evidence a research run depends on.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from cyberlite.data.contamination import (
    build_benchmark_index,
    check_contamination_v2,
    cross_split_leakage,
)
from cyberlite.data.licensing import is_evaluation_only
from cyberlite.data.schema import Record, load_records, sha256_file

REPO_ROOT = Path(__file__).resolve().parents[2]
SPLITS = ("train", "validation", "test")
Profile = Literal["research", "smoke", "custom"]


@dataclass
class IntegrityIssue:
    check: str
    message: str
    severity: Literal["error", "warning"] = "error"
    path: str | None = None
    record_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "check": self.check,
            "severity": self.severity,
            "message": self.message,
        }
        if self.path:
            payload["path"] = self.path
        if self.record_id:
            payload["record_id"] = self.record_id
        if self.details:
            payload["details"] = self.details
        return payload


class DatasetIntegrityError(ValueError):
    """Raised when training data does not match its frozen manifest."""

    def __init__(self, report: DatasetIntegrityReport) -> None:
        self.report = report
        messages = [issue.message for issue in report.errors[:5]]
        remainder = len(report.errors) - len(messages)
        suffix = f"; and {remainder} more" if remainder > 0 else ""
        super().__init__(
            f"dataset integrity verification failed ({len(report.errors)} error(s)): "
            + "; ".join(messages)
            + suffix
        )


@dataclass
class DatasetIntegrityReport:
    profile: Profile
    manifest_path: str | None = None
    manifest_sha256: str | None = None
    dataset_name: str | None = None
    dataset_version: str | None = None
    expected_version: str | None = None
    expected_split_counts: dict[str, int] = field(default_factory=dict)
    split_counts: dict[str, int] = field(default_factory=dict)
    source_counts: dict[str, int] = field(default_factory=dict)
    license_counts: dict[str, int] = field(default_factory=dict)
    task_counts: dict[str, int] = field(default_factory=dict)
    kind_counts: dict[str, int] = field(default_factory=dict)
    provenance_gaps: dict[str, int] = field(default_factory=dict)
    files: dict[str, dict[str, Any]] = field(default_factory=dict)
    manifest: dict[str, Any] = field(default_factory=dict)
    duplicate_ids: list[dict[str, Any]] = field(default_factory=list)
    cross_split_leakage: list[dict[str, Any]] = field(default_factory=list)
    evaluation_contamination: dict[str, Any] = field(default_factory=dict)
    issues: list[IntegrityIssue] = field(default_factory=list)
    records: dict[str, list[Record]] = field(default_factory=dict, repr=False)

    @property
    def ok(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)

    @property
    def errors(self) -> list[IntegrityIssue]:
        return [issue for issue in self.issues if issue.severity == "error"]

    @property
    def warnings(self) -> list[IntegrityIssue]:
        return [issue for issue in self.issues if issue.severity == "warning"]

    def add(self, check: str, message: str, **kwargs: Any) -> None:
        self.issues.append(IntegrityIssue(check=check, message=message, **kwargs))

    def to_dict(self) -> dict[str, Any]:
        return {
            "report": "training-dataset-integrity",
            "schema_version": 1,
            "profile": self.profile,
            "ok": self.ok,
            "manifest_path": self.manifest_path,
            "manifest_sha256": self.manifest_sha256,
            "dataset_name": self.dataset_name,
            "dataset_version": self.dataset_version,
            "expected_version": self.expected_version,
            "expected_split_counts": self.expected_split_counts,
            "split_counts": self.split_counts,
            "record_count": sum(self.split_counts.values()),
            "source_counts": self.source_counts,
            "license_counts": self.license_counts,
            "task_counts": self.task_counts,
            "kind_counts": self.kind_counts,
            "provenance_gaps": self.provenance_gaps,
            "files": self.files,
            "manifest": {
                "split_counts": self.manifest.get("split_counts"),
                "files": self.manifest.get("files"),
                "manual_review": self.manifest.get("manual_review"),
                "contamination": self.manifest.get("contamination"),
                "cross_split_leakage": len(self.manifest.get("cross_split_leakage") or []),
                "group_split_violations": len(self.manifest.get("group_split_violations") or []),
            },
            "duplicate_ids": self.duplicate_ids[:50],
            "duplicate_id_count": len(self.duplicate_ids),
            "cross_split_leakage": self.cross_split_leakage[:50],
            "cross_split_leakage_count": len(self.cross_split_leakage),
            "evaluation_contamination": self.evaluation_contamination,
            "issues": [issue.to_dict() for issue in self.issues],
            "blockers": [issue.message for issue in self.errors],
        }


def _resolve_path(value: str | Path, *, base_dir: Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base_dir / path)


def _resolve_manifest_file(value: str | Path, *, manifest_path: Path, base_dir: Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    base_candidate = base_dir / path
    sibling_candidate = manifest_path.parent / path
    if base_candidate.exists() or not sibling_candidate.exists():
        return base_candidate
    return sibling_candidate


def _read_evaluation_ids(eval_files: list[Path]) -> set[str]:
    ids: set[str] = set()
    for path in eval_files:
        try:
            with path.open(encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(payload, dict) and payload.get("id") is not None:
                        ids.add(str(payload["id"]))
        except OSError:
            continue
    return ids


def _required_provenance(record: Record) -> list[str]:
    missing: list[str] = []
    if not record.id:
        missing.append("id")
    if not record.source:
        missing.append("source")
    if not record.license:
        missing.append("license")
    if not record.task:
        missing.append("task")
    if not (record.url or record.metadata.get("source_url")):
        missing.append("source_url")
    if not record.metadata.get("source_version"):
        missing.append("source_version")
    if not record.metadata.get("upstream_id"):
        missing.append("upstream_id")
    return missing


def _manifest_split_counts(manifest: dict[str, Any]) -> dict[str, int]:
    counts = manifest.get("split_counts")
    if isinstance(counts, dict):
        return {name: int(counts.get(name, 0) or 0) for name in SPLITS}
    return {}


def _compare_processed_manifest(
    report: DatasetIntegrityReport,
    processed_path: Path,
    manifest: dict[str, Any],
) -> None:
    try:
        processed = json.loads(processed_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        report.add(
            "processed_manifest_invalid",
            f"processed dataset manifest is unreadable: {processed_path}: {exc}",
            path=str(processed_path),
        )
        return
    for key in ("dataset_version", "split_counts"):
        if processed.get(key) != manifest.get(key):
            report.add(
                "processed_manifest_mismatch",
                f"{processed_path} has {key}={processed.get(key)!r}, but the frozen "
                f"manifest has {manifest.get(key)!r}; rebuild the dataset instead of "
                "regenerating the frozen manifest",
                path=str(processed_path),
            )
    frozen_files = manifest.get("files") or {}
    processed_files = processed.get("files") or {}
    for split in SPLITS:
        frozen_hash = (frozen_files.get(split) or {}).get("sha256")
        processed_hash = (processed_files.get(split) or {}).get("sha256")
        if frozen_hash and processed_hash and frozen_hash != processed_hash:
            report.add(
                "processed_manifest_mismatch",
                f"{split} hash differs between the processed manifest and the frozen "
                "manifest; the local split is not the registered dataset",
                path=str(processed_path),
                details={"frozen": frozen_hash, "processed": processed_hash},
            )


def verify_dataset(
    *,
    train_file: str | Path,
    validation_file: str | Path | None,
    test_file: str | Path | None,
    manifest_file: str | Path | None,
    expected_version: str | None,
    expected_split_counts: dict[str, int] | None,
    profile: Profile = "research",
    require_manifest: bool = True,
    require_provenance: bool = True,
    require_contamination_screen: bool = True,
    eval_dir: str | Path | None = "data/evaluation",
    contamination_n: int = 13,
    contamination_threshold: float = 0.2,
    dedup_threshold: int = 3,
    base_dir: str | Path | None = None,
) -> DatasetIntegrityReport:
    """Verify dataset files against a frozen manifest without modifying anything."""

    base = Path(base_dir) if base_dir is not None else REPO_ROOT
    report = DatasetIntegrityReport(
        profile=profile,
        expected_version=expected_version,
        expected_split_counts=dict(expected_split_counts or {}),
    )
    configured = {
        "train": train_file,
        "validation": validation_file,
        "test": test_file,
    }
    paths = {
        name: _resolve_path(value, base_dir=base)
        for name, value in configured.items()
        if value is not None
    }

    if profile != "smoke" and expected_version is None:
        report.add(
            "dataset_version_missing",
            "research training requires data.dataset_version from the frozen manifest",
        )
    if profile != "smoke" and not report.expected_split_counts:
        report.add(
            "split_counts_missing",
            "research training requires data.expected_split_counts from the frozen manifest",
        )

    manifest: dict[str, Any] = {}
    manifest_path: Path | None = None
    if manifest_file is not None:
        manifest_path = _resolve_path(manifest_file, base_dir=base)
    elif paths.get("train") is not None:
        manifest_path = paths["train"].parent / "manifest.json"

    if manifest_path is None or not manifest_path.is_file():
        message = (
            f"dataset manifest not found: {manifest_path or manifest_file}. "
            "Research training requires the frozen manifest; rebuild with "
            "`python scripts/prepare_dataset.py --config configs/dataset_pilot.yaml --force` "
            "instead of creating or editing a manifest by hand."
        )
        report.add(
            "manifest_missing",
            message,
            severity="error" if require_manifest else "warning",
            path=str(manifest_path) if manifest_path else None,
        )
    else:
        report.manifest_path = str(manifest_path)
        try:
            report.manifest_sha256 = sha256_file(manifest_path)
            loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("manifest root must be a JSON object")
            manifest = loaded
            report.manifest = manifest
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            report.add(
                "manifest_invalid",
                f"dataset manifest is unreadable: {manifest_path}: {exc}",
                path=str(manifest_path),
            )

    if manifest:
        report.dataset_name = str(manifest.get("dataset_name") or "") or None
        report.dataset_version = str(manifest.get("dataset_version") or "") or None
        if profile != "smoke" and not report.dataset_version:
            report.add(
                "dataset_version_missing",
                "frozen manifest has no dataset_version",
                path=str(manifest_path),
            )
        if expected_version and report.dataset_version != expected_version:
            report.add(
                "dataset_version_mismatch",
                f"expected dataset version {expected_version}, found "
                f"{report.dataset_version!r}; this is a stale or different build",
                path=str(manifest_path),
            )
        manifest_counts = _manifest_split_counts(manifest)
        if manifest_counts:
            for split, count in manifest_counts.items():
                expected = report.expected_split_counts.get(split)
                if expected is not None and count != expected:
                    report.add(
                        "manifest_split_count_mismatch",
                        f"frozen manifest {split} count is {count}, expected {expected}",
                        path=str(manifest_path),
                    )
        if manifest.get("dataset_schema") not in (1, 2):
            report.add(
                "manifest_schema_unsupported",
                f"unsupported dataset_schema={manifest.get('dataset_schema')!r}",
                path=str(manifest_path),
            )
        output_records = manifest.get("output_records")
        if (
            isinstance(output_records, int)
            and manifest_counts
            and output_records != sum(manifest_counts.values())
        ):
            report.add(
                "manifest_count_inconsistent",
                f"manifest output_records={output_records} but split counts sum to "
                f"{sum(manifest_counts.values())}",
                path=str(manifest_path),
            )
        processed_path = paths.get("train", Path()).parent / "manifest.json"
        if manifest_path and processed_path != manifest_path and processed_path.is_file():
            _compare_processed_manifest(report, processed_path, manifest)

    files_by_split: dict[str, dict[str, Any]] = {}
    all_records: dict[str, list[Record]] = {}
    id_locations: dict[str, tuple[str, int]] = {}
    duplicate_ids: list[dict[str, Any]] = []
    provenance_gaps: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    license_counts: Counter[str] = Counter()
    task_counts: Counter[str] = Counter()
    kind_counts: Counter[str] = Counter()
    eval_only_findings: list[dict[str, Any]] = []

    manifest_files = manifest.get("files") or {}
    for split in SPLITS:
        configured_path = paths.get(split)
        manifest_item = manifest_files.get(split) or {}
        manifest_value = manifest_item.get("path")
        manifest_resolved = (
            _resolve_manifest_file(manifest_value, manifest_path=manifest_path, base_dir=base)
            if manifest_value and manifest_path is not None
            else None
        )
        path = configured_path or manifest_resolved
        if path is None:
            if split == "validation" and not validation_file:
                report.add(
                    "split_missing",
                    "validation split is not configured; research training requires it",
                )
            elif split == "test" and not test_file:
                report.add("split_missing", "test split is not configured")
            continue
        if not path.is_file():
            report.add(
                "dataset_file_missing",
                f"{split} dataset file not found: {path}. Rebuild the registered dataset; "
                "do not train from a partially generated directory.",
                path=str(path),
            )
            continue

        actual_hash = sha256_file(path)
        actual_bytes = path.stat().st_size
        item: dict[str, Any] = {
            "path": str(path),
            "sha256": actual_hash,
            "bytes": actual_bytes,
            "records": 0,
        }
        if manifest_item:
            expected_hash = manifest_item.get("sha256")
            expected_bytes = manifest_item.get("bytes")
            if expected_hash and expected_hash != actual_hash:
                report.add(
                    "dataset_hash_mismatch",
                    f"{split} file hash does not match the frozen manifest: {path}. "
                    "The file was modified or replaced; refuse to train on it.",
                    path=str(path),
                    details={"expected": expected_hash, "actual": actual_hash},
                )
            if isinstance(expected_bytes, int) and expected_bytes != actual_bytes:
                report.add(
                    "dataset_size_mismatch",
                    f"{split} file size is {actual_bytes}, manifest says {expected_bytes}",
                    path=str(path),
                )
        elif profile != "smoke":
            report.add(
                "manifest_file_entry_missing",
                f"frozen manifest has no file entry for the {split} split",
                path=str(path),
            )

        try:
            records = load_records(path)
        except (OSError, ValueError) as exc:
            report.add(
                "schema_invalid",
                f"{split} split failed schema validation: {exc}",
                path=str(path),
            )
            files_by_split[split] = item
            continue

        item["records"] = len(records)
        expected_records = manifest_item.get("records")
        if isinstance(expected_records, int) and expected_records != len(records):
            report.add(
                "split_record_count_mismatch",
                f"{split} has {len(records)} records, manifest says {expected_records}",
                path=str(path),
            )
        expected_count = report.expected_split_counts.get(split)
        if expected_count is not None and expected_count != len(records):
            report.add(
                "split_record_count_mismatch",
                f"{split} has {len(records)} records, expected {expected_count}",
                path=str(path),
            )

        for record_index, record in enumerate(records):
            if record.id in id_locations:
                previous_split, previous_index = id_locations[record.id]
                duplicate = {
                    "id": record.id,
                    "first_split": previous_split,
                    "first_index": previous_index,
                    "duplicate_split": split,
                    "duplicate_index": record_index,
                }
                duplicate_ids.append(duplicate)
                report.add(
                    "duplicate_record_id",
                    f"duplicate record id {record.id!r} in {split} and {previous_split}",
                    record_id=record.id,
                )
            else:
                id_locations[record.id] = (split, record_index)

            if record.split != split:
                report.add(
                    "split_field_mismatch",
                    f"record {record.id!r} is in {split} but its split field is {record.split!r}",
                    record_id=record.id,
                )
            if require_provenance and profile != "smoke":
                missing = _required_provenance(record)
                for field_name in missing:
                    provenance_gaps[field_name] += 1
                if missing:
                    report.add(
                        "provenance_missing",
                        f"record {record.id!r} is missing provenance fields: {', '.join(missing)}",
                        record_id=record.id,
                        details={"missing": missing},
                    )
            elif profile == "smoke":
                for field_name in ("id", "source", "license", "task"):
                    if not getattr(record, field_name, ""):
                        provenance_gaps[field_name] += 1

            eval_only, reason = is_evaluation_only(record)
            if eval_only:
                eval_only_findings.append(
                    {"record_id": record.id, "split": split, "reason": reason}
                )
                report.add(
                    "evaluation_only_record",
                    f"record {record.id!r} in {split} is evaluation-only: {reason}",
                    record_id=record.id,
                    details={"reason": reason},
                )

            source_counts[record.source] += 1
            license_counts[record.license] += 1
            task_counts[record.task] += 1
            kind_counts[record.kind] += 1

        all_records[split] = records
        files_by_split[split] = item

    report.records = all_records
    report.files = files_by_split
    report.split_counts = {split: len(items) for split, items in all_records.items()}
    report.source_counts = dict(sorted(source_counts.items()))
    report.license_counts = dict(sorted(license_counts.items()))
    report.task_counts = dict(sorted(task_counts.items()))
    report.kind_counts = dict(sorted(kind_counts.items()))
    report.duplicate_ids = duplicate_ids
    report.provenance_gaps = dict(sorted(provenance_gaps.items()))

    leakage = cross_split_leakage(all_records, threshold=dedup_threshold)
    report.cross_split_leakage = [finding.to_dict() for finding in leakage]
    if leakage:
        report.add(
            "cross_split_leakage",
            f"{len(leakage)} exact or near-duplicate records cross split boundaries; "
            "the test/validation split is not isolated from training",
        )

    contamination: dict[str, Any] = {
        "checked": False,
        "sets": [],
        "total_indexed_ngrams": 0,
        "findings": [],
        "limitations": [
            "13-gram overlap detects verbatim and near-verbatim leakage only.",
            "Paraphrase, translation, and conceptual overlap are not detected.",
        ],
        "evaluation_only_findings": eval_only_findings[:50],
    }
    if profile != "smoke" and require_contamination_screen and eval_dir:
        eval_path = Path(eval_dir)
        eval_files = sorted(eval_path.glob("*.jsonl")) if eval_path.is_dir() else []
        if not eval_files:
            report.add(
                "evaluation_files_missing",
                f"no evaluation JSONL files found under {eval_path}; cannot verify "
                "benchmark contamination",
                path=str(eval_path),
            )
        else:
            benchmark_index = build_benchmark_index([], n=contamination_n)
            for eval_file in eval_files:
                try:
                    benchmark_index.add_file(eval_file)
                except Exception as exc:
                    report.add(
                        "evaluation_index_invalid",
                        f"could not index evaluation file {eval_file}: {exc}",
                        severity="warning",
                        path=str(eval_file),
                    )
            if benchmark_index.sets:
                all_accepted = [record for records in all_records.values() for record in records]
                kept, findings, screened = check_contamination_v2(
                    all_accepted,
                    benchmark_index,
                    threshold=contamination_threshold,
                    group_quarantine=True,
                )
                contamination = {
                    "checked": True,
                    "sets": [
                        {
                            "name": item.get("name"),
                            "path": Path(str(item.get("path", ""))).name,
                            "sha256": item.get("sha256"),
                            "items": item.get("items"),
                            "ngrams": item.get("ngrams"),
                        }
                        for item in screened.get("sets", [])
                    ],
                    "total_indexed_ngrams": screened.get("total_indexed_ngrams", 0),
                    "findings": screened.get("findings", [])[:50],
                    "finding_count": len(findings),
                    "verified_kept": len(kept),
                    "limitations": contamination["limitations"],
                    "evaluation_only_findings": eval_only_findings[:50],
                }
                if findings:
                    report.add(
                        "benchmark_contamination",
                        f"{len(findings)} training records overlap local evaluation data "
                        f"at the {contamination_n}-gram threshold {contamination_threshold}",
                    )
            else:
                report.add(
                    "evaluation_files_missing",
                    "no usable evaluation n-grams were indexed; cannot verify benchmark "
                    "contamination",
                    path=str(eval_path),
                )
    report.evaluation_contamination = contamination
    return report


def evaluation_ids_from_directory(eval_dir: str | Path | None) -> set[str]:
    """Return ids from local evaluation files for accidental-ingestion checks."""

    if not eval_dir:
        return set()
    path = Path(eval_dir)
    if not path.is_dir():
        return set()
    return _read_evaluation_ids(sorted(path.glob("*.jsonl")))

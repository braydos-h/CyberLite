"""Reproducible dataset preparation pipeline.

The pipeline is intentionally offline-first: it operates on local files and
never downloads a source unless the caller passes ``--download`` or a dataset
configuration explicitly enables acquisition. Every output split is accompanied
by a manifest containing input/output hashes, license counts, quality and
contamination statistics, and the effective options.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cyberlite import __version__
from cyberlite.data.acquire import (
    AcquisitionError,
    CacheMissError,
    fetch_archive,
    fetch_file,
    locate_extracted_root,
)
from cyberlite.data.cleaning import (
    Deduplicator,
    license_allowed,
    normalize_license,
    normalize_text,
    redact_secrets,
)
from cyberlite.data.config import (
    DEFAULT_ALLOWED_LICENSES,
    PIPELINE_VERSION,
    DatasetConfig,
    QualityThresholds,
    SourceRunConfig,
)
from cyberlite.data.contamination import (
    BenchmarkFinding,
    BenchmarkIndex,
    build_benchmark_index,
    check_contamination_v2,
    cross_split_leakage,
)
from cyberlite.data.quality import (
    QualityAssessment,
    assess_record,
    load_token_counter,
    quality_summary,
    token_length_report,
)
from cyberlite.data.reports import (
    build_license_report,
    render_license_markdown,
    render_manifest_readme,
    write_json_and_markdown,
)
from cyberlite.data.schema import Record, load_records, sha256_file, write_jsonl
from cyberlite.data.sources import (
    SourceRegistry,
    SourceSpec,
    collect_nvd,
    download_source,
    normalize_source_outcome,
)
from cyberlite.data.splits import (
    SplitRatios,
    group_split_violations,
    split_records,
)
from cyberlite.logging_utils import configure_logging, get_logger, log_event

logger = get_logger(__name__)

REQUIRED_PROVENANCE: dict[str, tuple[str, ...]] = {
    "mitre_attack": ("attack_id",),
    "mitre_cwe": ("cwe_id",),
    "nist_nvd": ("cve_id",),
    "ietf_rfcs": ("rfc",),
    "linux_man_pages": ("manpage",),
    "openssh_docs": ("manpage",),
    "netfilter_nftables": ("manpage",),
    "owasp_cheatsheets": ("document",),
}


@dataclass
class PrepareOptions:
    out_dir: Path
    seed: int = 42
    ratios: SplitRatios = field(default_factory=lambda: SplitRatios(0.9, 0.05, 0.05))
    allowed_licenses: list[str] = field(default_factory=lambda: list(DEFAULT_ALLOWED_LICENSES))
    redact: bool = True
    min_chars: int = 80
    max_chars: int = 200_000
    dedup_threshold: int = 3
    contamination_n: int = 13
    contamination_threshold: float = 0.2
    contamination_group_quarantine: bool = True
    group_splits: bool = True
    verify_split_leakage: bool = True
    force: bool = False
    smoke: bool = False
    quality: QualityThresholds = field(default_factory=QualityThresholds)
    tokenizer: str = ""
    tokenizer_local_only: bool = True
    max_seq_len: int = 2048
    dataset_name: str = "cyberlite"
    report_dir: Path | None = None
    reproduction_command: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["out_dir"] = str(self.out_dir)
        payload["report_dir"] = str(self.report_dir) if self.report_dir else None
        payload["ratios"] = asdict(self.ratios)
        payload["quality"] = asdict(self.quality)
        return payload


@dataclass
class PreparedDataset:
    splits: dict[str, list[Record]]
    rejected: list[dict[str, Any]]
    manifest: dict[str, Any]
    quality_assessments: list[QualityAssessment] = field(default_factory=list)
    benchmark_index: BenchmarkIndex | None = None
    source_inputs: list[dict[str, Any]] = field(default_factory=list)
    source_errors: list[dict[str, Any]] = field(default_factory=list)


def _clean_text_fields(record: Record, options: PrepareOptions) -> tuple[Record, dict[str, Any]]:
    """Normalize and redact all text fields, returning a new validated record."""

    stats: dict[str, Any] = {"secret_kinds": [], "redactions": 0}

    def clean(value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = normalize_text(value, max_chars=options.max_chars)
        if options.redact:
            cleaned, findings = redact_secrets(cleaned)
            stats["redactions"] += len(findings)
            stats["secret_kinds"].extend(finding.kind for finding in findings)
        return cleaned

    messages = None
    if record.messages:
        messages = [
            {"role": message["role"], "content": clean(message["content"]) or ""}
            for message in record.messages
        ]
    metadata = dict(record.metadata)
    metadata["prepared_by"] = f"cyberlite-{__version__}"
    metadata.setdefault("source_version", "unversioned")
    if stats["redactions"]:
        metadata["secrets_redacted"] = stats["redactions"]
        metadata["secret_kinds"] = sorted(set(stats["secret_kinds"]))
    cleaned_record = Record(
        id=record.id,
        source=record.source,
        license=normalize_license(record.license),
        task=record.task,
        messages=messages,
        prompt=clean(record.prompt),
        response=clean(record.response),
        prefix=clean(record.prefix),
        suffix=clean(record.suffix),
        middle=clean(record.middle),
        url=record.url,
        split=record.split,
        metadata=metadata,
    )
    return cleaned_record, stats


def _char_count(record: Record) -> int:
    return len(record.text_for_dedup())


def _rejection_counts(rejected: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in rejected:
        reason = str(item["reason"]).split(":", 1)[0]
        counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items()))


def _required_metadata(source: str) -> tuple[str, ...]:
    return REQUIRED_PROVENANCE.get(source, ())


def _token_report(records: list[Record], options: PrepareOptions) -> dict[str, Any]:
    if not options.tokenizer:
        return {
            "status": "not_requested",
            "note": "Pass --tokenizer MODEL or set tokenizer in the dataset config.",
            "max_sequence_tokens": options.max_seq_len,
        }
    counter, info = load_token_counter(options.tokenizer, local_only=options.tokenizer_local_only)
    report = token_length_report(records, counter, max_sequence_tokens=options.max_seq_len)
    report["tokenizer_info"] = info
    return report


def _task_imbalance(task_counts: dict[str, int]) -> dict[str, Any]:
    if not task_counts:
        return {"balanced": True, "ratio": None, "note": "no accepted records"}
    values = list(task_counts.values())
    minimum = min(values)
    maximum = max(values)
    ratio = None if minimum == 0 else round(maximum / minimum, 3)
    return {
        "min_count": minimum,
        "max_count": maximum,
        "ratio": ratio,
        "balanced": ratio is not None and ratio <= 10.0,
        "note": (
            "A ratio above 10 indicates a task category with very little coverage; "
            "it is a review prompt, not an automatic rejection."
        ),
    }


def _provenance_gaps(splits: dict[str, list[Record]]) -> dict[str, int]:
    fields = {
        "url": lambda record: bool(record.url),
        "source_version": lambda record: bool(record.metadata.get("source_version")),
        "license": lambda record: bool(record.license),
        "task": lambda record: bool(record.task),
        "upstream_id": lambda record: bool(record.metadata.get("upstream_id")),
    }
    gaps: dict[str, int] = {}
    for name, predicate in fields.items():
        gaps[name] = sum(
            1 for records in splits.values() for record in records if not predicate(record)
        )
    return gaps


def _split_counts(splits: dict[str, list[Record]]) -> dict[str, int]:
    return {name: len(items) for name, items in splits.items()}


def prepare_records(
    records: list[Record],
    options: PrepareOptions,
    *,
    eval_files: list[str] | None = None,
    source_registry_hash: str = "",
    config_sha256: str = "",
    source_inputs: list[dict[str, Any]] | None = None,
    source_errors: list[dict[str, Any]] | None = None,
) -> PreparedDataset:
    """Clean, filter, deduplicate, contaminate-check, and split records.

    All sources are combined before any of these stages, so deduplication,
    contamination screening, and splitting are global rather than per-source.
    """

    rejected: list[dict[str, Any]] = []
    cleaned: list[Record] = []
    license_counts: dict[str, int] = {}
    redaction_count = 0
    quality_assessments: list[QualityAssessment] = []
    warning_by_source: dict[str, dict[str, int]] = {}

    for record in records:
        if not license_allowed(record.license, options.allowed_licenses):
            rejected.append(
                {
                    "reason": "license_not_allowed",
                    "license": record.license,
                    "source": record.source,
                    "id": record.id,
                }
            )
            continue
        try:
            record, stats = _clean_text_fields(record, options)
        except ValueError as exc:
            rejected.append(
                {"reason": f"invalid_record:{exc}", "source": record.source, "id": record.id}
            )
            continue
        redaction_count += stats["redactions"]
        assessment = assess_record(
            record,
            options.quality,
            required_metadata=_required_metadata(record.source),
        )
        quality_assessments.append(assessment)
        if assessment.warnings:
            entry = warning_by_source.setdefault(record.source, {})
            for warning in assessment.warnings:
                entry[warning] = entry.get(warning, 0) + 1
        if not assessment.accepted:
            rejected.append(
                {
                    "reason": f"quality:{assessment.rejection_reasons[0]}",
                    "source": record.source,
                    "id": record.id,
                    "quality_issues": assessment.rejection_reasons,
                }
            )
            continue
        if _char_count(record) < options.min_chars:
            rejected.append({"reason": "too_short", "source": record.source, "id": record.id})
            continue
        cleaned.append(record)
        license_counts[record.license] = license_counts.get(record.license, 0) + 1

    deduplicator = Deduplicator(threshold=options.dedup_threshold)
    unique: list[Record] = []
    id_sources = {record.id: record.source for record in cleaned}
    exact_sources: dict[str, str] = {}
    cross_source_duplicates = 0
    for record in cleaned:
        text = record.text_for_dedup()
        exact_key = deduplicator._exact_key(text)
        duplicate, reason = deduplicator.is_duplicate(text)
        if duplicate:
            other_source = ""
            if reason == "exact":
                other_source = exact_sources.get(exact_key, "")
            elif reason.startswith("near:"):
                other_source = id_sources.get(reason.split(":", 1)[1], "")
            if other_source and other_source != record.source:
                cross_source_duplicates += 1
            rejected.append(
                {
                    "reason": f"duplicate:{reason}",
                    "source": record.source,
                    "id": record.id,
                    "other_source": other_source,
                }
            )
        else:
            exact_sources.setdefault(exact_key, record.source)
            unique.append(record)

    contamination_findings: list[BenchmarkFinding] = []
    contamination_report: dict[str, Any] = {
        "status": "not_screened",
        "evaluation_files": [],
        "total_indexed_ngrams": 0,
        "removed": 0,
        "threshold": options.contamination_threshold,
        "ngram": options.contamination_n,
        "limitations": (
            "No evaluation files were supplied, so no contamination screen was run. "
            "This is not evidence of absence."
        ),
    }
    benchmark_index: BenchmarkIndex | None = None
    active_eval_files = eval_files or []
    if active_eval_files:
        benchmark_index = build_benchmark_index(active_eval_files, n=options.contamination_n)
        before = len(unique)
        id_to_record = {record.id: record for record in unique}
        unique, contamination_findings, contamination_report = check_contamination_v2(
            unique,
            benchmark_index,
            threshold=options.contamination_threshold,
            group_quarantine=options.contamination_group_quarantine,
        )
        for finding in contamination_findings:
            rejected.append(
                {
                    "reason": "benchmark_contamination",
                    "source": finding.source,
                    "id": finding.id,
                    "benchmark": finding.benchmark,
                    "overlap": round(finding.overlap, 4),
                }
            )
        direct_ids = {finding.id for finding in contamination_findings}
        for record_id in contamination_report.get("group_removed_ids", []):
            if record_id in direct_ids:
                continue
            removed = id_to_record.get(record_id)
            rejected.append(
                {
                    "reason": "benchmark_contamination_group",
                    "source": removed.source if removed else "unknown",
                    "id": record_id,
                }
            )
        contamination_report["status"] = "screened"
        contamination_report["records_before"] = before
        contamination_report["records_after"] = len(unique)

    leaks: list[dict[str, Any]] = []
    if options.group_splits:
        splits = split_records(unique, options.ratios, options.seed)
    else:
        splits = split_records(unique, options.ratios, options.seed, group_key=lambda item: item.id)
    group_violations = group_split_violations(splits)
    if options.verify_split_leakage:
        leak_findings = cross_split_leakage(splits, threshold=options.dedup_threshold)
        removed_ids: set[str] = set()
        for leak in leak_findings:
            leaks.append(leak.to_dict())
            removed_ids.add(leak.right_id)
            rejected.append(
                {
                    "reason": "cross_split_leakage",
                    "source": leak.right_split,
                    "id": leak.right_id,
                    "other_id": leak.left_id,
                    "kind": leak.kind,
                }
            )
        if removed_ids:
            for split_name, items in splits.items():
                splits[split_name] = [item for item in items if item.id not in removed_ids]
            group_violations = group_split_violations(splits)
    if options.smoke:
        # Guarantee non-empty evaluation splits for pipeline validation only.
        for name in ("validation", "test"):
            if not splits[name] and len(splits["train"]) > 2:
                splits[name].append(splits["train"].pop())

    source_counts: dict[str, int] = {}
    task_counts: dict[str, int] = {}
    output_records: list[Record] = []
    for split_items in splits.values():
        for record in split_items:
            source_counts[record.source] = source_counts.get(record.source, 0) + 1
            task_counts[record.task] = task_counts.get(record.task, 0) + 1
            output_records.append(record)

    split_counts = _split_counts(splits)
    token_report = _token_report(output_records, options)
    quality_stats = quality_summary(quality_assessments)
    quality_stats["warnings_by_source"] = {
        source: dict(sorted(counts.items())) for source, counts in sorted(warning_by_source.items())
    }
    quality_stats["token_lengths"] = token_report

    manifest: dict[str, Any] = {
        "dataset_schema": 2,
        "dataset_name": options.dataset_name,
        "pipeline_version": PIPELINE_VERSION,
        "cyberlite_version": __version__,
        "created_at": datetime.now(tz=UTC).isoformat(),
        "seed": options.seed,
        "options": options.to_dict(),
        "config_sha256": config_sha256,
        "source_registry_sha256": source_registry_hash,
        "input_records": len(records),
        "output_records": sum(split_counts.values()),
        "rejected_total": len(rejected),
        "split_counts": split_counts,
        "source_counts": dict(sorted(source_counts.items())),
        "task_counts": dict(sorted(task_counts.items())),
        "license_counts": dict(sorted(license_counts.items())),
        "sources": source_inputs or [],
        "source_errors": source_errors or [],
        "cleaning": {
            "redacted_secrets": redaction_count,
            "dedup": deduplicator.stats,
            "duplicates": deduplicator.exact_duplicates + deduplicator.near_duplicates,
            "cross_source_duplicates": cross_source_duplicates,
        },
        "quality": quality_stats,
        "contamination": contamination_report,
        "rejections": rejected[:2000],
        "rejection_counts": _rejection_counts(rejected),
        "group_split_violations": group_violations,
        "cross_split_leakage": leaks[:200],
        "provenance_gaps": _provenance_gaps(splits),
        "task_imbalance": _task_imbalance(task_counts),
        "manual_review": {
            "completed": False,
            "reviewed_records": 0,
            "required": True,
            "target_records": 200,
            "note": (
                "No human review has been recorded. Generate a review sample with "
                "scripts/audit_dataset.py; do not mark this complete until reviewers "
                "have actually assessed the sample."
            ),
        },
        "reproduction": {
            "command": options.reproduction_command,
            "pinned_inputs": "See sources[].inputs[] SHA-256 values.",
            "offline": ("Re-run with --offline against the same cache to rebuild without network."),
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "files": {},
        "limitations": [
            "Quality gates are heuristics and can reject useful text or accept questionable text.",
            "The 13-gram screen does not detect paraphrase, translation, or conceptual overlap.",
            "Token counts are a length signal, not a quality or factuality measure.",
            "Manual review is pending; no record is described as human-verified.",
        ],
    }

    # A dataset version is derived from the content of all splits and the
    # processing configuration, never from timestamps, so identical pinned
    # inputs and options produce identical versions.
    version_hash = hashlib.sha256()
    version_hash.update(PIPELINE_VERSION.encode())
    version_hash.update(b"\x00")
    version_hash.update(config_sha256.encode())
    for split_name in ("train", "validation", "test"):
        for record in sorted(splits[split_name], key=lambda item: item.id):
            version_hash.update(record.id.encode())
            version_hash.update(b"\x00")
            version_hash.update(record.text_for_dedup().encode())
            version_hash.update(b"\x00")
    manifest["dataset_version"] = (
        f"cyberlite-data-{PIPELINE_VERSION}-{version_hash.hexdigest()[:12]}"
    )
    return PreparedDataset(
        splits=splits,
        rejected=rejected,
        manifest=manifest,
        quality_assessments=quality_assessments,
        benchmark_index=benchmark_index,
        source_inputs=source_inputs or [],
        source_errors=source_errors or [],
    )


def write_prepared_dataset(dataset: PreparedDataset, options: PrepareOptions) -> dict[str, Any]:
    """Write splits, quarantine, and manifest; return the completed manifest."""

    out_dir = options.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "train": out_dir / "train.jsonl",
        "validation": out_dir / "validation.jsonl",
        "test": out_dir / "test.jsonl",
    }
    if not options.force and any(path.exists() for path in paths.values()):
        raise FileExistsError(
            f"output splits already exist in {out_dir}; pass --force to replace them"
        )
    for name, path in paths.items():
        write_jsonl(dataset.splits[name], path)
        dataset.manifest["files"][name] = {
            "path": str(path),
            "records": len(dataset.splits[name]),
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
    quarantine_path = out_dir / "quarantine.jsonl"
    with quarantine_path.open("w", encoding="utf-8") as handle:
        for item in dataset.rejected:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    dataset.manifest["files"]["quarantine"] = {
        "path": str(quarantine_path),
        "records": len(dataset.rejected),
        "sha256": sha256_file(quarantine_path),
        "bytes": quarantine_path.stat().st_size,
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(dataset.manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    dataset.manifest["manifest_path"] = str(manifest_path)
    return dataset.manifest


def _relative(path: str | Path, base: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(base.resolve()))
    except ValueError:
        return str(path)


def write_dataset_reports(
    dataset: PreparedDataset,
    options: PrepareOptions,
    registry: SourceRegistry,
    *,
    base_dir: Path,
) -> dict[str, Any]:
    """Write quality, contamination, and license reports next to the manifest."""

    directory = options.report_dir or options.out_dir
    directory.mkdir(parents=True, exist_ok=True)
    manifest = dataset.manifest
    for item in manifest.get("files", {}).values():
        if item.get("path"):
            item["path"] = _relative(item["path"], base_dir)
    for item in manifest.get("contamination", {}).get("sets", []):
        if item.get("path"):
            item["path"] = _relative(item["path"], base_dir)
    accepted_records = [record for records in dataset.splits.values() for record in records]
    source_counts = {
        entry.get("name", "unknown"): int(entry.get("records", 0))
        for entry in dataset.source_inputs
    }
    license_report = build_license_report(
        registry_sources=[
            registry.get(name) for name in sorted(source_counts) if name in registry.sources
        ],
        records=accepted_records,
        source_records=source_counts,
        allowed_licenses=options.allowed_licenses,
    )
    quality_report = {
        "report": "quality-and-audit",
        "schema_version": 1,
        "dataset_name": manifest.get("dataset_name"),
        "dataset_version": manifest.get("dataset_version"),
        "pipeline_version": manifest.get("pipeline_version"),
        "rejected": manifest.get("rejected_total", 0),
        "accepted": manifest.get("output_records", 0),
        "counts": {
            "input_records": manifest.get("input_records", 0),
            "accepted_records": manifest.get("output_records", 0),
            "rejected_records": manifest.get("rejected_total", 0),
            "splits": manifest.get("split_counts", {}),
        },
        "source_distribution": manifest.get("source_counts", {}),
        "task_distribution": manifest.get("task_counts", {}),
        "license_distribution": manifest.get("license_counts", {}),
        "rejection_reasons": manifest.get("rejection_counts", {}),
        "quality_rejections": sum(
            (manifest.get("quality", {}).get("rejection_reasons", {}) or {}).values()
        ),
        "duplicate_rates": {
            **manifest.get("cleaning", {}),
            "rate": (
                manifest.get("cleaning", {}).get("duplicates", 0)
                / max(1, manifest.get("input_records", 0))
            ),
        },
        "contamination": manifest.get("contamination", {}),
        "token_lengths": manifest.get("quality", {}).get("token_lengths", {}),
        "missing_provenance": manifest.get("provenance_gaps", {}),
        "cross_split_leakage": manifest.get("cross_split_leakage", []),
        "group_split_violations": manifest.get("group_split_violations", []),
        "task_imbalance": manifest.get("task_imbalance", {}),
        "quality_warnings": manifest.get("quality", {}),
        "files": manifest.get("files", {}),
        "source_errors": manifest.get("source_errors", []),
        "manual_review": manifest.get("manual_review", {}),
        "limitations": manifest.get("limitations", []),
    }
    contamination_report = {
        "report": "benchmark-contamination",
        "schema_version": 1,
        "dataset_name": manifest.get("dataset_name"),
        "dataset_version": manifest.get("dataset_version"),
        "screen": manifest.get("contamination", {}),
        "requirements": {
            "never_ingest_evaluation_items": True,
            "per_benchmark_statistics": True,
            "versions_and_hashes_recorded": True,
            "quarantine_contaminated_records": True,
            "verify_evaluation_indexes_populated": True,
            "prevent_cross_split_leakage": True,
            "group_related_records": bool(options.group_splits),
        },
        "limitations": [
            "13-gram overlap catches verbatim and near-verbatim leakage only.",
            "Paraphrased, translated, or conceptually equivalent items are not detected.",
            "A zero finding is a measured zero for this screen, not proof of absence.",
            "Restricted benchmark content is not redistributed; only hashes and counts appear here.",
        ],
    }
    quality_path, _ = write_json_and_markdown(quality_report, directory, "quality_report")
    contamination_path, _ = write_json_and_markdown(
        contamination_report, directory, "contamination_report"
    )
    license_path, license_md_path = write_json_and_markdown(
        license_report,
        directory,
        "license_report",
        markdown=render_license_markdown(license_report),
    )
    report_files = {
        "quality_report": quality_path,
        "contamination_report": contamination_path,
        "license_report": license_path,
    }
    if license_md_path:
        report_files["license_report_markdown"] = license_md_path
    manifest["reports"] = {
        name: {
            "path": _relative(path, base_dir),
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
        for name, path in report_files.items()
    }
    manifest["manual_review"]["review_sample_command"] = (
        "python scripts/audit_dataset.py "
        f"--dataset {options.out_dir} --review-out {options.out_dir}/review_samples.jsonl"
    )
    manifest_path = directory / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    manifest["manifest_path"] = str(manifest_path)
    readme = render_manifest_readme(
        manifest, {"quality": quality_report, "contamination": manifest.get("contamination", {})}
    )
    (directory / "README.md").write_text(readme, encoding="utf-8")
    return manifest


def collect_local_inputs(
    registry: SourceRegistry, raw_dir: Path, names: list[str] | None = None
) -> list[tuple[Path, SourceSpec]]:
    """Find already-downloaded local inputs for enabled sources."""

    inputs: list[tuple[Path, SourceSpec]] = []
    candidates = [registry.get(name) for name in names] if names else registry.enabled()
    for spec in candidates:
        if spec.kind == "jsonl" and not spec.filename:
            continue
        filename = spec.filename or Path(spec.url).name
        if not filename:
            continue
        path = raw_dir / spec.name / filename
        if path.is_file():
            inputs.append((path, spec))
    return inputs


def _load_eval_files(eval_dir: Path) -> list[str]:
    if not eval_dir.is_dir():
        return []
    return sorted(str(path) for path in eval_dir.glob("*.jsonl"))


def _enrich_seed_records(records: Iterable[Record]) -> list[Record]:
    enriched: list[Record] = []
    for record in records:
        record.metadata.setdefault("source_version", "seed-v1")
        record.metadata.setdefault("upstream_id", record.id)
        record.metadata.setdefault("transformation", "seed")
        enriched.append(record)
    return enriched


def run_prepare(
    *,
    registry_path: Path,
    raw_dir: Path,
    eval_dir: Path,
    options: PrepareOptions,
    smoke_file: Path | None = None,
    input_paths: list[tuple[Path, SourceSpec]] | None = None,
) -> dict[str, Any]:
    """Execute the legacy preparation path and write artifacts."""

    registry = SourceRegistry.load(registry_path)
    registry_hash = sha256_file(registry_path)
    records: list[Record] = []
    source_inputs: list[dict[str, Any]] = []
    source_errors: list[dict[str, Any]] = []
    if options.smoke:
        if smoke_file is None or not smoke_file.is_file():
            raise FileNotFoundError(f"smoke dataset not found: {smoke_file}")
        records.extend(_enrich_seed_records(load_records(smoke_file)))
        source_inputs.append(
            {
                "name": "cyberlite_smoke",
                "title": "CyberLite synthetic smoke dataset",
                "license": "Synthetic",
                "kind": "jsonl",
                "revision": "seed-v1",
                "records": len(records),
                "inputs": [
                    {
                        "path": str(smoke_file),
                        "sha256": sha256_file(smoke_file),
                        "bytes": smoke_file.stat().st_size,
                    }
                ],
                "errors": [],
            }
        )
    else:
        inputs = input_paths if input_paths is not None else collect_local_inputs(registry, raw_dir)
        if not inputs:
            raise FileNotFoundError(
                "no local raw inputs found. Download explicitly with --download SOURCE, "
                "or pass --input PATH --source NAME. Use --config for multi-source builds "
                "or --smoke for the tiny test dataset."
            )
        for path, spec in inputs:
            log_event(logger, "normalizing_source", source=spec.name, path=str(path))
            try:
                outcome = normalize_source_outcome(path, spec)
            except Exception as exc:
                source_errors.append({"source": spec.name, "path": str(path), "error": str(exc)})
                continue
            records.extend(outcome.records)
            source_inputs.append(
                {
                    "name": spec.name,
                    "title": spec.title,
                    "license": spec.license,
                    "kind": spec.kind,
                    "revision": spec.revision,
                    "records": len(outcome.records),
                    "files": outcome.files,
                    "inputs": [
                        {
                            "path": str(path),
                            "sha256": sha256_file(path),
                            "bytes": path.stat().st_size,
                        }
                    ],
                    "errors": [error.to_dict() for error in outcome.errors],
                }
            )
            source_errors.extend(error.to_dict() for error in outcome.errors)

    if not records:
        raise ValueError("no records were produced from the selected inputs")

    dataset = prepare_records(
        records,
        options,
        eval_files=_load_eval_files(eval_dir),
        source_registry_hash=registry_hash,
        source_inputs=source_inputs,
        source_errors=source_errors,
    )
    manifest = write_prepared_dataset(dataset, options)
    if options.report_dir:
        manifest = write_dataset_reports(
            dataset, options, registry, base_dir=options.report_dir.parent
        )
    log_event(
        logger,
        "dataset_prepared",
        version=manifest["dataset_version"],
        train=manifest["split_counts"]["train"],
        validation=manifest["split_counts"]["validation"],
        test=manifest["split_counts"]["test"],
        rejected=len(dataset.rejected),
    )
    return manifest


def _merge_spec(spec: SourceSpec, source: SourceRunConfig, config: DatasetConfig) -> SourceSpec:
    max_records = source.max_records
    if max_records is None:
        max_records = config.limits.get(source.name, spec.max_records)
    return replace(
        spec,
        max_records=max_records,
        revision=source.revision or spec.revision,
        license=source.license_override or spec.license,
        options={**spec.options, **source.options},
    )


def _acquire_paths(
    source: SourceRunConfig,
    spec: SourceSpec,
    config: DatasetConfig,
) -> tuple[list[Path], list[dict[str, Any]], list[dict[str, Any]]]:
    """Resolve a source's local paths, using the cache or explicit downloads."""

    paths: list[Path] = []
    inputs: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    offline = config.offline or not config.download

    def record_input(path: Path, kind: str, url: str = "", *, normalize: bool = True) -> None:
        if normalize:
            paths.append(path)
        inputs.append(
            {
                "path": _relative(path, config.base_path),
                "kind": kind,
                "url": url,
                "sha256": sha256_file(path) if path.is_file() else "",
                "bytes": path.stat().st_size if path.is_file() else 0,
            }
        )

    explicit = [config.resolve(item) for item in source.paths]
    if explicit:
        for path in explicit:
            if path.exists():
                record_input(path, "local")
            elif source.url or spec.url:
                url = source.url or spec.url
                destination = (
                    config.resolve(config.raw_dir)
                    / source.name
                    / (spec.filename or Path(url).name or f"{source.name}.input")
                )
                try:
                    result = fetch_file(
                        url,
                        destination,
                        expected_sha256=source.sha256,
                        offline=offline,
                    )
                    record_input(result.path, "download", url)
                except (AcquisitionError, CacheMissError) as exc:
                    errors.append({"source": source.name, "path": str(path), "error": str(exc)})
            else:
                errors.append(
                    {
                        "source": source.name,
                        "path": str(path),
                        "error": "configured local path does not exist",
                    }
                )
        return paths, inputs, errors

    urls = source.options.get("urls") or spec.options.get("urls") or []
    if urls:
        if not isinstance(urls, list):
            raise ValueError(f"source {source.name!r} options.urls must be a list")
        for url in urls:
            destination = config.resolve(config.cache_dir) / "files" / source.name / Path(url).name
            try:
                result = fetch_file(url, destination, offline=offline)
                record_input(result.path, "download", str(url))
            except (AcquisitionError, CacheMissError) as exc:
                errors.append({"source": source.name, "path": str(url), "error": str(exc)})
        return paths, inputs, errors

    archive_url = source.archive_url or (
        spec.url
        if any(suffix in spec.url.lower() for suffix in (".tar.gz", ".tgz", ".tar.xz", ".zip"))
        else ""
    )
    if archive_url:
        filename = (
            source.options.get("filename")
            or spec.filename
            or Path(archive_url.split("?")[0]).name
            or f"{source.name}.archive"
        )
        try:
            archive_path, extracted = fetch_archive(
                archive_url,
                config.resolve(config.cache_dir),
                filename=str(filename),
                expected_sha256=source.sha256,
                offline=offline,
            )
            root = locate_extracted_root(extracted)
            subdir = str(source.options.get("subdir") or spec.options.get("subdir") or "")
            if subdir:
                root = root / subdir
            record_input(archive_path, "archive", archive_url, normalize=False)
            record_input(root, "extracted", archive_url)
        except (AcquisitionError, CacheMissError) as exc:
            errors.append({"source": source.name, "path": archive_url, "error": str(exc)})
        return paths, inputs, errors

    url = source.url or spec.url
    if url:
        filename = spec.filename or Path(url.split("?")[0]).name or f"{source.name}.input"
        destination = config.resolve(config.raw_dir) / source.name / filename
        try:
            result = fetch_file(
                url,
                destination,
                expected_sha256=source.sha256,
                offline=offline,
            )
            record_input(result.path, "download", url)
        except (AcquisitionError, CacheMissError) as exc:
            errors.append({"source": source.name, "path": url, "error": str(exc)})
        return paths, inputs, errors

    filename = spec.filename or (Path(spec.url).name if spec.url else "")
    if filename:
        path = config.resolve(config.raw_dir) / source.name / filename
        if path.exists():
            record_input(path, "local")
        else:
            errors.append(
                {
                    "source": source.name,
                    "path": str(path),
                    "error": "local input is missing; enable download or place the file",
                }
            )
    else:
        errors.append(
            {
                "source": source.name,
                "path": "",
                "error": "source has no paths, URL, archive, or registered filename",
            }
        )
    return paths, inputs, errors


def _source_record_limit(records: list[Record], source: SourceSpec) -> list[Record]:
    if source.max_records is None:
        return records
    return records[: source.max_records]


def run_config_prepare(
    config: DatasetConfig,
    *,
    registry_path: Path | None = None,
) -> dict[str, Any]:
    """Run a config-driven multi-source build and publish frozen reports."""

    registry_path = registry_path or config.resolve(config.registry)
    registry = SourceRegistry.load(registry_path)
    registry_hash = sha256_file(registry_path)
    selected = config.resolve_sources()
    if not selected:
        raise ValueError("no sources selected by the dataset configuration")

    records: list[Record] = []
    source_inputs: list[dict[str, Any]] = []
    source_errors: list[dict[str, Any]] = []
    eval_dir = config.resolve(config.eval_dir)
    cache_dir = config.resolve(config.cache_dir)

    for selection in selected:
        spec = _merge_spec(registry.get(selection.name), selection, config)
        if (
            not license_allowed(spec.license, config.allowed_licenses)
            and normalize_license(spec.license) != "Mixed-SPDX"
        ):
            message = (
                f"source license {spec.license!r} is not in allowed_licenses; source quarantined"
            )
            source_errors.append({"source": spec.name, "path": "", "error": message})
            source_inputs.append(
                {
                    "name": spec.name,
                    "title": spec.title,
                    "license": spec.license,
                    "kind": spec.kind,
                    "revision": spec.revision,
                    "records": 0,
                    "inputs": [],
                    "errors": [{"source": spec.name, "path": "", "error": message}],
                    "status": "quarantined",
                }
            )
            logger.warning(
                "source quarantined", extra={"source": spec.name, "license": spec.license}
            )
            continue

        mode = str(selection.options.get("mode") or spec.options.get("mode") or "")
        source_records: list[Record] = []
        try:
            if mode == "api" and spec.kind == "nvd_json":
                date_start = str(
                    selection.options.get("date_start") or spec.options.get("date_start") or ""
                )
                date_end = str(
                    selection.options.get("date_end") or spec.options.get("date_end") or ""
                )
                if not date_start or not date_end:
                    raise ValueError("NVD API source requires date_start and date_end")
                source_records, collection = collect_nvd(
                    spec,
                    cache_dir,
                    date_start=date_start,
                    date_end=date_end,
                    max_records=spec.max_records,
                    offline=(config.offline or not config.download),
                    page_size=int(
                        selection.options.get("page_size") or spec.options.get("page_size") or 2000
                    ),
                )
                source_inputs.append(
                    {
                        "name": spec.name,
                        "title": spec.title,
                        "license": spec.license,
                        "kind": spec.kind,
                        "revision": spec.revision,
                        "records": len(source_records),
                        "inputs": [
                            {
                                "path": _relative(item["path"], config.base_path),
                                "sha256": item["sha256"],
                                "kind": "nvd-page",
                                "start_index": item["start_index"],
                                "total_results": item["total_results"],
                            }
                            for item in collection.get("page_meta", [])
                        ],
                        "acquisition": {
                            "mode": "api",
                            "date_start": collection.get("date_start"),
                            "date_end": collection.get("date_end"),
                            "requests": collection.get("requests"),
                            "cache_hits": collection.get("cache_hits"),
                            "records_seen": collection.get("records_seen"),
                            "total_results": collection.get("total_results"),
                            "truncated": collection.get("truncated"),
                        },
                        "errors": [],
                    }
                )
            else:
                paths, inputs, acquisition_errors = _acquire_paths(selection, spec, config)
                source_errors.extend(acquisition_errors)
                for path in paths:
                    log_event(logger, "normalizing_source", source=spec.name, path=str(path))
                    try:
                        outcome = normalize_source_outcome(path, spec)
                    except Exception as exc:
                        source_errors.append(
                            {"source": spec.name, "path": str(path), "error": str(exc)}
                        )
                        continue
                    source_records.extend(outcome.records)
                    source_errors.extend(error.to_dict() for error in outcome.errors)
                source_records = _source_record_limit(source_records, spec)
                source_inputs.append(
                    {
                        "name": spec.name,
                        "title": spec.title,
                        "license": spec.license,
                        "kind": spec.kind,
                        "revision": spec.revision,
                        "records": len(source_records),
                        "inputs": inputs,
                        "errors": [
                            error for error in source_errors if error.get("source") == spec.name
                        ],
                        "max_records": spec.max_records,
                        "group": selection.group,
                    }
                )
        except Exception as exc:
            source_errors.append({"source": spec.name, "path": "", "error": str(exc)})
            source_inputs.append(
                {
                    "name": spec.name,
                    "title": spec.title,
                    "license": spec.license,
                    "kind": spec.kind,
                    "revision": spec.revision,
                    "records": 0,
                    "inputs": [],
                    "errors": [{"source": spec.name, "path": "", "error": str(exc)}],
                    "status": "failed",
                }
            )
            logger.warning("source failed", extra={"source": spec.name, "error": str(exc)})
            continue
        records.extend(source_records)

    if not records:
        raise ValueError(
            "no records were produced by the configured sources; inspect source_errors"
        )

    options = PrepareOptions(
        out_dir=config.resolve(config.out_dir),
        seed=config.seed,
        ratios=config.ratios,
        allowed_licenses=list(config.allowed_licenses),
        redact=config.redact,
        min_chars=config.min_chars,
        max_chars=config.max_chars,
        dedup_threshold=config.dedup_threshold,
        contamination_n=config.contamination_n,
        contamination_threshold=config.contamination_threshold,
        contamination_group_quarantine=config.contamination_group_quarantine,
        group_splits=config.group_splits,
        verify_split_leakage=config.verify_split_leakage,
        force=True,
        quality=config.quality,
        tokenizer=config.tokenizer,
        tokenizer_local_only=config.tokenizer_local_only,
        max_seq_len=config.quality.max_sequence_tokens,
        dataset_name=config.name,
        report_dir=config.resolve(config.manifest_dir),
        reproduction_command=(
            f"python scripts/prepare_dataset.py --config {_relative(Path(config.config_path), config.base_path)}"
            " --force"
        ),
    )
    dataset = prepare_records(
        records,
        options,
        eval_files=_load_eval_files(eval_dir),
        source_registry_hash=registry_hash,
        config_sha256=config.sha256(),
        source_inputs=source_inputs,
        source_errors=source_errors,
    )
    manifest = write_prepared_dataset(dataset, options)
    manifest = write_dataset_reports(dataset, options, registry, base_dir=config.base_path)
    log_event(
        logger,
        "dataset_prepared",
        version=manifest["dataset_version"],
        train=manifest["split_counts"]["train"],
        validation=manifest["split_counts"]["validation"],
        test=manifest["split_counts"]["test"],
        rejected=manifest.get("rejected_total", 0),
    )
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare a reproducible CyberLite dataset from local sources."
    )
    parser.add_argument("--config", default=None, help="multi-source dataset YAML")
    parser.add_argument("--sources", default="data/sources.yaml", help="source registry YAML")
    parser.add_argument("--out", default=None, help="output directory for splits")
    parser.add_argument("--manifest-dir", default=None, help="directory for frozen reports")
    parser.add_argument("--raw-dir", default="data/raw", help="directory containing raw inputs")
    parser.add_argument("--cache-dir", default="data/cache", help="acquisition cache")
    parser.add_argument("--eval-dir", default="data/evaluation", help="held-out evaluation JSONL")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--train-ratio", type=float, default=0.9)
    parser.add_argument("--validation-ratio", type=float, default=0.05)
    parser.add_argument("--test-ratio", type=float, default=0.05)
    parser.add_argument("--min-chars", type=int, default=80)
    parser.add_argument("--max-chars", type=int, default=200_000)
    parser.add_argument("--dedup-threshold", type=int, default=3)
    parser.add_argument("--contamination-threshold", type=float, default=0.2)
    parser.add_argument("--tokenizer", default="", help="tokenizer model id or local path")
    parser.add_argument("--max-seq-len", type=int, default=2048)
    parser.add_argument(
        "--allow-license",
        action="append",
        default=[],
        help="additional license identifier to accept (repeatable)",
    )
    parser.add_argument("--no-redact", action="store_true", help="disable secret redaction")
    parser.add_argument("--smoke", action="store_true", help="use the tiny bundled smoke dataset")
    parser.add_argument("--smoke-file", default="data/seed/smoke.jsonl")
    parser.add_argument(
        "--input",
        action="append",
        default=[],
        help="local input path (repeatable; requires --source)",
    )
    parser.add_argument("--source", default=None, help="registered source name for --input")
    parser.add_argument(
        "--download",
        action="append",
        default=[],
        help="explicitly download registered source(s) (repeatable)",
    )
    parser.add_argument("--offline", action="store_true", help="forbid network access")
    parser.add_argument("--no-download", action="store_true", help="disable config downloads")
    parser.add_argument(
        "--include",
        action="append",
        default=[],
        help="include only these config sources (repeatable)",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="exclude these config sources (repeatable)",
    )
    parser.add_argument("--force", action="store_true", help="replace existing output splits")
    parser.add_argument("--list-sources", action="store_true")
    parser.add_argument("--json-logs", action="store_true")
    parser.add_argument("--json", action="store_true", help="print manifest JSON to stdout")
    return parser


def _apply_config_overrides(config: DatasetConfig, args: argparse.Namespace) -> DatasetConfig:
    if args.out:
        config.out_dir = args.out
    if args.manifest_dir:
        config.manifest_dir = args.manifest_dir
    if args.raw_dir != "data/raw":
        config.raw_dir = args.raw_dir
    if args.cache_dir != "data/cache":
        config.cache_dir = args.cache_dir
    if args.eval_dir != "data/evaluation":
        config.eval_dir = args.eval_dir
    if args.seed != 42:
        config.seed = args.seed
    if (args.train_ratio, args.validation_ratio, args.test_ratio) != (0.9, 0.05, 0.05):
        try:
            config.ratios = SplitRatios(args.train_ratio, args.validation_ratio, args.test_ratio)
        except ValueError as exc:
            raise SystemExit(f"error: {exc}") from exc
    if args.tokenizer:
        config.tokenizer = args.tokenizer
    if args.max_seq_len != 2048:
        config.quality = replace(config.quality, max_sequence_tokens=args.max_seq_len)
    if args.allow_license:
        config.allowed_licenses = list(config.allowed_licenses) + list(args.allow_license)
    if args.offline:
        config.offline = True
    if args.no_download:
        config.download = False
    if args.download:
        config.download = True
    if args.include:
        config.include_sources = list(args.include)
    if args.exclude:
        config.exclude_sources = list(args.exclude)
    return config


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(json_logs=args.json_logs)
    try:
        registry = SourceRegistry.load(args.sources)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.list_sources:
        for spec in registry.sources.values():
            flag = "enabled" if spec.enabled else "disabled"
            print(f"{spec.name:24s} {spec.kind:10s} {spec.license:18s} {flag:8s} {spec.title}")
        return 0

    if args.input and not args.source:
        print("error: --input requires --source", file=sys.stderr)
        return 2

    if args.config:
        try:
            config = DatasetConfig.load(args.config)
            config = _apply_config_overrides(config, args)
            if args.download:
                # Downloading is explicit; the config still controls which
                # sources are selected.
                config.download = True
            manifest = run_config_prepare(config, registry_path=config.resolve(config.registry))
        except (FileExistsError, FileNotFoundError, KeyError, ValueError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(manifest, indent=2))
        else:
            counts = manifest["split_counts"]
            print(f"dataset version : {manifest['dataset_version']}")
            print(f"output          : {config.resolve(config.out_dir)}")
            print(
                f"records         : train={counts['train']} "
                f"validation={counts['validation']} test={counts['test']}"
            )
            print(f"rejected        : {manifest.get('rejected_total', 0)} (see quarantine.jsonl)")
            print(f"manifest        : {config.resolve(config.manifest_dir) / 'manifest.json'}")
        return 0

    raw_dir = Path(args.raw_dir)
    downloaded: list[tuple[Path, SourceSpec]] = []
    for name in args.download:
        try:
            spec = registry.get(name)
            path = download_source(spec, raw_dir / name)
        except (KeyError, OSError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        downloaded.append((path, spec))

    input_paths: list[tuple[Path, SourceSpec]] | None = None
    if args.input:
        try:
            spec = registry.get(args.source)
        except KeyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        input_paths = [(Path(path), spec) for path in args.input]
    elif downloaded:
        input_paths = downloaded

    out_dir = (
        Path(args.out)
        if args.out
        else Path("data/processed/smoke" if args.smoke else "data/processed")
    )
    try:
        if args.smoke and (args.train_ratio, args.validation_ratio, args.test_ratio) == (
            0.9,
            0.05,
            0.05,
        ):
            # A 34-example smoke corpus cannot populate 5% evaluation splits.
            ratios = SplitRatios(0.75, 0.125, 0.125)
        else:
            ratios = SplitRatios(args.train_ratio, args.validation_ratio, args.test_ratio)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    allowed = list(DEFAULT_ALLOWED_LICENSES) + args.allow_license
    options = PrepareOptions(
        out_dir=out_dir,
        seed=args.seed,
        ratios=ratios,
        allowed_licenses=allowed,
        redact=not args.no_redact,
        min_chars=args.min_chars,
        max_chars=args.max_chars,
        dedup_threshold=args.dedup_threshold,
        contamination_threshold=args.contamination_threshold,
        force=args.force,
        smoke=args.smoke,
        tokenizer=args.tokenizer,
        tokenizer_local_only=True,
        max_seq_len=args.max_seq_len,
        report_dir=Path(args.manifest_dir) if args.manifest_dir else None,
        reproduction_command=f"python scripts/prepare_dataset.py --smoke --out {out_dir} --force"
        if args.smoke
        else "",
    )
    try:
        manifest = run_prepare(
            registry_path=Path(args.sources),
            raw_dir=raw_dir,
            eval_dir=Path(args.eval_dir),
            options=options,
            smoke_file=Path(args.smoke_file),
            input_paths=input_paths,
        )
    except (FileExistsError, FileNotFoundError, KeyError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(manifest, indent=2))
    else:
        counts = manifest["split_counts"]
        print(f"dataset version : {manifest['dataset_version']}")
        print(f"output          : {out_dir}")
        print(
            f"records         : train={counts['train']} "
            f"validation={counts['validation']} test={counts['test']}"
        )
        print(f"rejected        : {manifest.get('rejected_total', 0)} (see quarantine.jsonl)")
        print(f"manifest        : {out_dir / 'manifest.json'}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

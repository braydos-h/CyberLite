"""CPU-only dataset auditing, stratified review sampling, and report rendering.

The auditor reads the produced splits and manifest, re-checks leakage and
contamination, measures token lengths, and writes machine-readable and
human-readable reports. It never marks manual review complete; only a human
reviewer can change the review status in the generated template.
"""

from __future__ import annotations

import json
import math
import random
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cyberlite.data.cleaning import Deduplicator
from cyberlite.data.contamination import (
    build_benchmark_index,
    check_contamination_v2,
    cross_split_leakage,
)
from cyberlite.data.quality import (
    HeuristicTokenCounter,
    TokenCounter,
    load_token_counter,
    token_length_report,
)
from cyberlite.data.reports import build_license_report, render_license_markdown
from cyberlite.data.schema import Record, load_records, sha256_file
from cyberlite.data.sources import SourceRegistry

REVIEW_FIELDS = [
    "accuracy",
    "relevance",
    "completeness",
    "provenance",
    "safety",
    "overall_quality",
]


@dataclass
class AuditResult:
    report: dict[str, Any]
    markdown: str
    review_samples: list[dict[str, Any]] = field(default_factory=list)
    review_plan: dict[str, Any] = field(default_factory=dict)


def _read_quarantine(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            rows.append({"reason": "malformed_quarantine_line"})
            continue
        if isinstance(payload, dict):
            rows.append(payload)
        else:
            rows.append({"reason": "malformed_quarantine_record"})
    return rows


def _distribution(records: Iterable[Record], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = str(getattr(record, key, "unknown"))
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _rejection_counts(quarantine: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in quarantine:
        reason = str(row.get("reason", "unknown")).split(":", 1)[0]
        counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items()))


def _provenance_gaps(records: list[Record]) -> dict[str, int]:
    checks = {
        "id": lambda record: bool(record.id),
        "source": lambda record: bool(record.source),
        "source_url": lambda record: bool(record.url),
        "source_version": lambda record: bool(record.metadata.get("source_version")),
        "license": lambda record: bool(record.license),
        "task": lambda record: bool(record.task),
        "upstream_id": lambda record: bool(record.metadata.get("upstream_id")),
    }
    return {
        name: sum(1 for record in records if not predicate(record))
        for name, predicate in checks.items()
    }


def _duplicate_analysis(records: list[Record]) -> dict[str, Any]:
    exact = Deduplicator(threshold=0)
    near = Deduplicator(threshold=3)
    exact_count = 0
    near_count = 0
    cross_source = 0
    source_by_exact: dict[str, str] = {}
    for record in records:
        text = record.text_for_dedup()
        is_exact, _ = exact.is_duplicate(text)
        if is_exact:
            exact_count += 1
            key = exact._exact_key(text)
            previous = source_by_exact.get(key)
            if previous and previous != record.source:
                cross_source += 1
        else:
            source_by_exact.setdefault(exact._exact_key(text), record.source)
        is_near, _ = near.is_duplicate(text)
        if is_near:
            near_count += 1
    total = len(records)
    return {
        "records_checked": total,
        "exact_duplicates": exact_count,
        "near_duplicates": near_count,
        "cross_source_duplicates": cross_source,
        "exact_rate": round(exact_count / total, 4) if total else 0.0,
        "near_rate": round(near_count / total, 4) if total else 0.0,
    }


def _task_imbalance(counts: dict[str, int]) -> dict[str, Any]:
    if not counts:
        return {"balanced": True, "ratio": None}
    values = list(counts.values())
    minimum = min(values)
    maximum = max(values)
    ratio = None if minimum == 0 else round(maximum / minimum, 3)
    return {
        "min_count": minimum,
        "max_count": maximum,
        "ratio": ratio,
        "balanced": ratio is not None and ratio <= 10.0,
        "note": "A high ratio is a review prompt, not an automatic defect.",
    }


def _stratified_sample(
    records: list[Record], target: int, seed: int
) -> tuple[list[Record], dict[str, Any]]:
    strata: dict[tuple[str, str], list[Record]] = defaultdict(list)
    for record in records:
        strata[(record.source, record.task)].append(record)
    for items in strata.values():
        items.sort(key=lambda item: item.id)
    if target >= len(records):
        all_selected = sorted(records, key=lambda item: (item.source, item.task, item.id))
        return all_selected, {
            "target": target,
            "selected": len(all_selected),
            "sample_ids": [record.id for record in all_selected],
            "strata": {
                f"{source}/{task}": len(items) for (source, task), items in sorted(strata.items())
            },
        }
    keys = sorted(strata)
    quotas: dict[tuple[str, str], int] = {key: 0 for key in keys}
    total = len(records)
    remaining = target
    for key in keys:
        size = len(strata[key])
        quota = max(1, math.floor(size / total * target))
        quota = min(quota, size)
        quotas[key] = quota
        remaining -= quota
    # Distribute the remaining slots by largest fractional share, then by size.
    order = sorted(
        keys,
        key=lambda key: (
            -(len(strata[key]) / total * target - math.floor(len(strata[key]) / total * target)),
            -len(strata[key]),
            key,
        ),
    )
    cursor = 0
    while remaining > 0:
        key = order[cursor % len(order)]
        if quotas[key] < len(strata[key]):
            quotas[key] += 1
            remaining -= 1
        cursor += 1
        if cursor > len(order) * max(1, target) * 2:
            break
    rng = random.Random(seed)
    selected: list[Record] = []
    for key in keys:
        items = list(strata[key])
        rng.shuffle(items)
        selected.extend(items[: quotas[key]])
    selected.sort(key=lambda item: item.id)
    return selected, {
        "target": target,
        "selected": len(selected),
        "seed": seed,
        "sample_ids": [record.id for record in selected],
        "strata": {
            f"{source}/{task}": {
                "available": len(items),
                "selected": quotas[(source, task)],
            }
            for (source, task), items in sorted(strata.items())
        },
    }


def _review_record(record: Record) -> dict[str, Any]:
    payload = record.to_dict()
    payload["review"] = {
        "reviewer": "",
        "reviewed_at": "",
        "accuracy": None,
        "relevance": None,
        "completeness": None,
        "provenance": None,
        "safety": None,
        "overall_quality": None,
        "notes": "",
        "review_status": "pending",
    }
    return payload


def _review_template() -> str:
    return """# Manual review template

**Status: not completed.** No human review has been recorded by the auditor.
Fill this template only after a person has read the sampled records and checked
the source evidence. Do not mark a record reviewed because an automated check
passed.

## Instructions

1. Open `review_samples.jsonl` in a local, access-controlled environment. It is
   intentionally outside Git because it contains source text.
2. Review each sample against its `url`, `source_version`, and `upstream_id`.
3. Score each field from 1 (poor) to 5 (excellent), or mark `unsure` with a note.
4. Record concrete errors, unsupported claims, unsafe guidance, or provenance gaps.
5. Do not edit the dataset splits. Report issues for a new build.
6. Aggregate results in `review_summary.json`; set `completed: true` only when
   every sampled record has a reviewer and a timestamp.

## Fields

| Field | What to check |
|---|---|
| `accuracy` | Is the technical content correct and consistent with the cited source? |
| `relevance` | Does the response answer the prompt and stay on the defensive-security task? |
| `completeness` | Are the important conditions, limitations, and verification steps present? |
| `provenance` | Do source, URL, version, license, and upstream identifiers match the evidence? |
| `safety` | Does the record avoid operational harm, credentials, and unsupported instructions? |
| `overall_quality` | Would this record be acceptable for the intended training run? |

## Record-level fields

```json
{
  "id": "...",
  "reviewer": "...",
  "reviewed_at": "YYYY-MM-DD",
  "accuracy": 1,
  "relevance": 1,
  "completeness": 1,
  "provenance": 1,
  "safety": 1,
  "overall_quality": 1,
  "notes": "Evidence and specific issue, if any.",
  "review_status": "reviewed"
}
```

## Aggregate

```json
{
  "completed": false,
  "reviewed_records": 0,
  "sample_size": 0,
  "reviewers": [],
  "accuracy_mean": null,
  "safety_failures": null,
  "provenance_failures": null,
  "notes": "Set completed to true only after the human review is finished."
}
```
"""


def _token_report(records: list[Record], tokenizer: str, max_seq_len: int) -> dict[str, Any]:
    if not tokenizer:
        counter: TokenCounter = HeuristicTokenCounter()
        info = {
            "name": counter.name,
            "kind": "heuristic",
            "estimated": True,
            "error": "no tokenizer requested",
        }
    else:
        counter, info = load_token_counter(tokenizer, local_only=True)
    report = token_length_report(records, counter, max_sequence_tokens=max_seq_len)
    report["tokenizer_info"] = info
    return report


def _file_manifest(dataset_dir: Path) -> dict[str, Any]:
    files: dict[str, Any] = {}
    for name in (
        "train.jsonl",
        "validation.jsonl",
        "test.jsonl",
        "quarantine.jsonl",
        "manifest.json",
    ):
        path = dataset_dir / name
        if path.is_file():
            files[name] = {
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
    return files


def audit_dataset(
    dataset_dir: str | Path,
    *,
    out_dir: str | Path | None = None,
    review_out: str | Path | None = None,
    review_size: int = 200,
    seed: int = 42,
    tokenizer: str = "",
    max_seq_len: int = 2048,
    eval_dir: str | Path | None = None,
    verify_contamination: bool = True,
    registry_path: str | Path | None = None,
) -> AuditResult:
    dataset_dir = Path(dataset_dir)
    out_dir = Path(out_dir) if out_dir else dataset_dir
    manifest_path = dataset_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"dataset manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    options = manifest.get("options", {}) or {}

    splits: dict[str, list[Record]] = {}
    for name in ("train", "validation", "test"):
        path = dataset_dir / f"{name}.jsonl"
        if path.is_file():
            splits[name] = load_records(path)
        else:
            splits[name] = []
    accepted = [record for records in splits.values() for record in records]
    quarantine = _read_quarantine(dataset_dir / "quarantine.jsonl")

    source_distribution = _distribution(accepted, "source")
    task_distribution = _distribution(accepted, "task")
    license_distribution = _distribution(accepted, "license")
    rejection_reasons = _rejection_counts(quarantine)
    duplicate_analysis = _duplicate_analysis(accepted)
    leakage = cross_split_leakage(splits, threshold=int(options.get("dedup_threshold", 3) or 0))
    provenance = _provenance_gaps(accepted)
    tokenizer = tokenizer or str(options.get("tokenizer") or "")
    max_seq_len = int(options.get("max_seq_len") or max_seq_len or 2048)
    tokens = _token_report(accepted, tokenizer, max_seq_len)

    contamination: dict[str, Any] = {
        "verified": False,
        "note": "verification disabled or no evaluation directory supplied",
        "manifest_screen": manifest.get("contamination", {}),
    }
    if verify_contamination and eval_dir:
        eval_path = Path(eval_dir)
        eval_files = sorted(str(path) for path in eval_path.glob("*.jsonl"))
        if eval_files:
            try:
                index = build_benchmark_index(eval_files, n=int(options.get("contamination_n", 13)))
                kept, findings, screened = check_contamination_v2(
                    accepted,
                    index,
                    threshold=float(options.get("contamination_threshold", 0.2)),
                    group_quarantine=bool(options.get("contamination_group_quarantine", True)),
                )
                for item in screened.get("sets", []):
                    item["path"] = Path(str(item.get("path", ""))).name
                contamination = {
                    "verified": True,
                    "index": screened,
                    "verified_removed": len(findings),
                    "verified_kept": len(kept),
                    "passed": len(findings) == 0,
                    "limitations": [
                        "13-gram overlap detects verbatim and near-verbatim leakage only.",
                        "Paraphrase, translation, and conceptual overlap are not detected.",
                    ],
                }
            except Exception as exc:
                contamination = {
                    "verified": False,
                    "passed": False,
                    "error": str(exc),
                }
        else:
            contamination = {
                "verified": False,
                "passed": False,
                "note": "no *.jsonl evaluation files were found; index is empty",
            }

    sample, review_plan = _stratified_sample(accepted, review_size, seed)
    review_samples = [_review_record(record) for record in sample]

    registry: SourceRegistry | None = None
    if registry_path and Path(registry_path).is_file():
        registry = SourceRegistry.load(registry_path)
    license_sources = []
    if registry is not None:
        license_sources = [
            registry.get(name) for name in source_distribution if name in registry.sources
        ]
    license_report = build_license_report(
        registry_sources=license_sources,
        records=accepted,
        source_records=source_distribution,
        allowed_licenses=options.get("allowed_licenses", []),
    )

    file_inventory = _file_manifest(dataset_dir)
    manifest_files = manifest.get("files", {})
    file_hash_mismatches = [
        name
        for name, item in file_inventory.items()
        if name.removesuffix(".jsonl") in manifest_files
        and manifest_files[name.removesuffix(".jsonl")].get("sha256") not in (None, item["sha256"])
    ]

    report: dict[str, Any] = {
        "report": "dataset-audit",
        "schema_version": 1,
        "dataset_name": manifest.get("dataset_name"),
        "dataset_version": manifest.get("dataset_version"),
        "pipeline_version": manifest.get("pipeline_version"),
        "config_sha256": manifest.get("config_sha256"),
        "seed": manifest.get("seed", seed),
        "counts": {
            "total_records": len(accepted) + len(quarantine),
            "accepted_records": len(accepted),
            "rejected_records": len(quarantine),
            "splits": {name: len(records) for name, records in splits.items()},
        },
        "source_distribution": source_distribution,
        "task_distribution": task_distribution,
        "license_distribution": license_distribution,
        "rejection_reasons": rejection_reasons,
        "duplicate_analysis": duplicate_analysis,
        "contamination": contamination,
        "cross_split_leakage": [item.to_dict() for item in leakage],
        "group_split_violations": manifest.get("group_split_violations", []),
        "token_lengths": tokens,
        "missing_provenance": provenance,
        "task_imbalance": _task_imbalance(task_distribution),
        "file_inventory": file_inventory,
        "manifest_file_hash_mismatches": file_hash_mismatches,
        "manual_review": {
            "completed": False,
            "reviewed_records": 0,
            "required": True,
            "sample_size": len(review_samples),
            "review_files": {
                "samples": str(review_out or (dataset_dir / "review_samples.jsonl")),
                "template": str(out_dir / "review_template.md"),
            },
            "fields": REVIEW_FIELDS,
            "note": (
                "No human review has been recorded. The auditor generates samples "
                "and a template only; it never marks review complete."
            ),
        },
        "license_report": license_report,
        "limitations": manifest.get("limitations", []),
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "audit.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out_dir / "quality_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out_dir / "contamination_report.json").write_text(
        json.dumps(
            {
                "report": "benchmark-contamination-audit",
                "dataset_version": report["dataset_version"],
                "contamination": contamination,
                "limitations": report["limitations"],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (out_dir / "license_report.json").write_text(
        json.dumps(license_report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out_dir / "license_report.md").write_text(
        render_license_markdown(license_report), encoding="utf-8"
    )
    (out_dir / "review_template.md").write_text(_review_template(), encoding="utf-8")
    review_out = Path(review_out) if review_out else dataset_dir / "review_samples.jsonl"
    review_out.parent.mkdir(parents=True, exist_ok=True)
    with review_out.open("w", encoding="utf-8") as handle:
        for payload in review_samples:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    (out_dir / "review_plan.json").write_text(
        json.dumps(review_plan, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    markdown = render_audit_markdown(report)
    (out_dir / "audit.md").write_text(markdown, encoding="utf-8")
    return AuditResult(
        report=report,
        markdown=markdown,
        review_samples=review_samples,
        review_plan=review_plan,
    )


def render_audit_markdown(report: dict[str, Any]) -> str:
    counts = report["counts"]
    lines = [
        f"# Dataset audit — {report.get('dataset_name', 'dataset')}",
        "",
        f"Dataset version: `{report.get('dataset_version', '')}`",
        "",
        "## Counts",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Total records (accepted + rejected) | {counts['total_records']} |",
        f"| Accepted | {counts['accepted_records']} |",
        f"| Rejected / quarantined | {counts['rejected_records']} |",
    ]
    for name, value in counts["splits"].items():
        lines.append(f"| {name} | {value} |")
    lines.extend(["", "## Source distribution", "", "| Source | Records |", "|---|---:|"])
    for source, value in report["source_distribution"].items():
        lines.append(f"| {source} | {value} |")
    lines.extend(["", "## Task distribution", "", "| Task | Records |", "|---|---:|"])
    for task, value in report["task_distribution"].items():
        lines.append(f"| {task} | {value} |")
    lines.extend(["", "## License distribution", "", "| License | Records |", "|---|---:|"])
    for license_id, value in report["license_distribution"].items():
        lines.append(f"| {license_id} | {value} |")
    lines.extend(["", "## Rejection reasons", "", "| Reason | Records |", "|---|---:|"])
    for reason, value in report["rejection_reasons"].items():
        lines.append(f"| {reason} | {value} |")
    duplicate = report["duplicate_analysis"]
    lines.extend(
        [
            "",
            "## Duplicates and leakage",
            "",
            "| Check | Result |",
            "|---|---:|",
            f"| Exact duplicates | {duplicate['exact_duplicates']} |",
            f"| Near duplicates | {duplicate['near_duplicates']} |",
            f"| Cross-source duplicates | {duplicate['cross_source_duplicates']} |",
            f"| Cross-split leakage findings | {len(report['cross_split_leakage'])} |",
            f"| Group split violations | {len(report['group_split_violations'])} |",
        ]
    )
    contamination = report["contamination"]
    lines.extend(
        [
            "",
            "## Contamination",
            "",
            f"Verified in this audit: **{contamination.get('verified')}**",
            "",
        ]
    )
    if contamination.get("verified"):
        index = contamination.get("index", {})
        lines.extend(
            [
                f"Indexed evaluation n-grams: {index.get('total_indexed_ngrams', 0)}",
                "",
                "| Benchmark | Items | N-grams | SHA-256 | Version | Matched |",
                "|---|---:|---:|---|---|---:|",
            ]
        )
        for item in index.get("sets", []):
            lines.append(
                f"| {item.get('name')} | {item.get('items')} | {item.get('ngrams')} | "
                f"`{item.get('sha256')}` | {item.get('version')} | {item.get('matched_records')} |"
            )
        lines.append(f"\nVerified removals across splits: {contamination.get('verified_removed')}")
    else:
        lines.append(contamination.get("note") or contamination.get("error") or "not verified")
    tokens = report["token_lengths"]
    token_stats = tokens.get("tokens", {})
    lines.extend(
        [
            "",
            "## Token lengths",
            "",
            f"Tokenizer: `{tokens.get('tokenizer')}`",
            "",
            "| p50 | p90 | p95 | p99 | max | over limit |",
            "|---:|---:|---:|---:|---:|---:|",
            f"| {token_stats.get('p50')} | {token_stats.get('p90')} | {token_stats.get('p95')} | "
            f"{token_stats.get('p99')} | {token_stats.get('max')} | "
            f"{tokens.get('truncation', {}).get('over_limit')} |",
            "",
            "## Missing provenance",
            "",
            "| Field | Missing records |",
            "|---|---:|",
        ]
    )
    for field_name, value in report["missing_provenance"].items():
        lines.append(f"| {field_name} | {value} |")
    lines.extend(
        [
            "",
            "## Manual review",
            "",
            "**Not completed.** A deterministic stratified sample and review template "
            "have been generated. No human review is recorded by this audit.",
            "",
            f"Samples: `{report['manual_review']['review_files']['samples']}`",
            f"Template: `{report['manual_review']['review_files']['template']}`",
            "",
            "## File inventory",
            "",
            "| File | Bytes | SHA-256 |",
            "|---|---:|---|",
        ]
    )
    for name, item in report["file_inventory"].items():
        lines.append(f"| {name} | {item['bytes']} | `{item['sha256']}` |")
    if report["manifest_file_hash_mismatches"]:
        lines.extend(
            [
                "",
                "**Manifest hash mismatch:** " + ", ".join(report["manifest_file_hash_mismatches"]),
            ]
        )
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in report.get("limitations", []))
    lines.append("")
    return "\n".join(lines)

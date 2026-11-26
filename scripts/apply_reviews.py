#!/usr/bin/env python
"""Apply an independent review ledger to a synthesis build.

The script never creates reviews. It aggregates reviewer JSON files, enforces
the rubric threshold, records disagreement, and either marks records as
AI-reviewed or removes them to a review quarantine. Revision decisions are kept
out of training until a later revision is reviewed again.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from cyberlite.data.review import aggregate, load_review
from cyberlite.data.schema import Record, load_records, sha256_file, write_jsonl


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--splits-dir", required=True)
    parser.add_argument("--manifest-dir", required=True)
    parser.add_argument("--reviews-dir", default=None)
    parser.add_argument("--apply", action="store_true", help="rewrite splits")
    parser.add_argument("--force", action="store_true")
    return parser


def _review_metadata(item) -> dict[str, object]:
    return {
        "review_status": "ai-independently-reviewed",
        "human_reviewed": False,
        "review_average": item.average,
        "review_technical_accuracy": item.technical_accuracy,
        "review_source_grounding": item.source_grounding,
        "reviewers": sorted({review.reviewer for review in item.reviews}),
        "review_types": sorted({review.review_type for review in item.reviews}),
        "review_disagreements": item.disagreements,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    splits_dir = Path(args.splits_dir)
    manifest_dir = Path(args.manifest_dir)
    reviews_dir = Path(args.reviews_dir or manifest_dir / "reviews")
    files = sorted(reviews_dir.glob("*.json")) if reviews_dir.exists() else []
    if not files:
        raise SystemExit(f"no review files found in {reviews_dir}")
    ledgers = [load_review(path) for path in files]
    items, summary = aggregate(ledgers)

    records: list[Record] = []
    split_of: dict[str, str] = {}
    for name in ("train", "validation", "test"):
        path = splits_dir / f"{name}.jsonl"
        if path.exists():
            for record in load_records(path):
                records.append(record)
                split_of[record.id] = name
    if not records:
        raise SystemExit(f"no records in {splits_dir}")

    quarantined: list[dict[str, object]] = []
    removed_ids: set[str] = set()
    reviewed = 0
    stale_reviews = 0
    independence_warnings: list[str] = []
    for record in records:
        item = items.get(record.id)
        if item is None:
            continue
        current_hash = str((record.metadata or {}).get("content_hash") or "")
        matching_reviews = [
            review
            for review in item.reviews
            if review.content_hash and review.content_hash == current_hash
        ]
        if not matching_reviews:
            stale_reviews += 1
            continue
        # Only reviews bound to the current content hash count. A matching ID
        # alone is not evidence that a reviewer saw this text.
        item.reviews = matching_reviews
        authoring_agent = str((record.metadata or {}).get("authoring_agent") or "")
        if authoring_agent and any(review.reviewer == authoring_agent for review in item.reviews):
            independence_warnings.append(record.id)
        if item.decision == "accept":
            record.metadata.update(_review_metadata(item))
            reviewed += 1
        elif item.decision in {"revise", "quarantine"}:
            removed_ids.add(record.id)
            quarantined.append(
                {
                    "reason": f"review:{item.decision}",
                    "id": record.id,
                    "split": split_of.get(record.id),
                    "decision": item.decision,
                    "average": item.average,
                    "findings": [finding for review in item.reviews for finding in review.findings][
                        :20
                    ],
                    "reviews": [review.to_dict() for review in item.reviews],
                    "record": record.to_dict(),
                }
            )

    kept = [record for record in records if record.id not in removed_ids]
    report = {
        "report": "independent-ai-review",
        "created_at": datetime.now(tz=UTC).isoformat(),
        "review_files": [str(path) for path in files],
        "summary": summary,
        "applied": {
            "reviewed_records": reviewed,
            "quarantined_records": len(removed_ids),
            "review_average": round(
                sum(item.average for item in items.values()) / max(1, len(items)), 3
            ),
            "technical_accuracy_average": round(
                sum(item.technical_accuracy for item in items.values()) / max(1, len(items)), 3
            ),
            "source_grounding_average": round(
                sum(item.source_grounding for item in items.values()) / max(1, len(items)), 3
            ),
            "independence_warnings": independence_warnings[:50],
            "stale_review_records": stale_reviews,
        },
        "decisions": dict(sorted(Counter(item.decision for item in items.values()).items())),
        "quarantine": quarantined[:500],
        "review_provenance": "A review is applied only when its content_hash matches the record's current content_hash.",
        "human_review": {
            "completed": False,
            "reviewed_records": 0,
            "note": "AI review is not human review.",
        },
    }
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "review_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    if not args.apply:
        print(
            f"reviewed={len(items)} accepted={reviewed} quarantined={len(removed_ids)} "
            f"disagreement_rate={summary['disagreement_rate']}"
        )
        print(f"report: {manifest_dir / 'review_report.json'} (not applied; pass --apply)")
        return 0

    if (splits_dir / "review_applied").exists() and not args.force:
        raise SystemExit("review already applied; pass --force to reapply")
    backup = splits_dir / "pre_review_backup"
    backup.mkdir(exist_ok=True)
    for name in ("train", "validation", "test"):
        path = splits_dir / f"{name}.jsonl"
        if path.exists():
            shutil.copy2(path, backup / path.name)

    by_split = {"train": [], "validation": [], "test": []}
    for record in kept:
        by_split[split_of[record.id]].append(record)
    for name, items_ in by_split.items():
        write_jsonl(items_, splits_dir / f"{name}.jsonl")

    quarantine_path = splits_dir / "review_quarantine.jsonl"
    with quarantine_path.open("w", encoding="utf-8") as handle:
        for entry in quarantined:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")

    manifest_path = manifest_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["review_coverage"] = {
        "automated_screening": len(kept),
        "ai_independent_review": reviewed,
        "human_review": 0,
        "review_average": report["applied"]["review_average"],
        "technical_accuracy_average": report["applied"]["technical_accuracy_average"],
        "source_grounding_average": report["applied"]["source_grounding_average"],
        "disagreement_rate": summary["disagreement_rate"],
        "note": "AI review is not human review; unreviewed records remain automated-screened.",
    }
    manifest["manual_review"] = report["human_review"]
    manifest["review_quarantine_records"] = len(removed_ids)
    manifest["accepted_records"] = len(kept)
    manifest["split_counts"] = {name: len(value) for name, value in by_split.items()}
    manifest["dataset_version"] = manifest["dataset_version"] + "-rev1"
    manifest["build_id"] = manifest["dataset_version"]
    for record in kept:
        record.metadata["dataset_version"] = manifest["dataset_version"]
        record.metadata["build_id"] = manifest["build_id"]
    # Rewrite once more so the version in metadata matches the applied manifest.
    for name, items_ in by_split.items():
        write_jsonl(items_, splits_dir / f"{name}.jsonl")
    manifest["files"] = manifest.get("files", {})
    for name in ("train", "validation", "test"):
        path = splits_dir / f"{name}.jsonl"
        manifest["files"][name] = {
            "path": str(path),
            "records": len(by_split[name]),
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
    manifest["files"]["review_quarantine"] = {
        "path": str(quarantine_path),
        "records": len(quarantined),
        "sha256": sha256_file(quarantine_path),
        "bytes": quarantine_path.stat().st_size,
    }
    manifest["review_report_sha256"] = hashlib.sha256(
        (manifest_dir / "review_report.json").read_bytes()
    ).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (splits_dir / "review_applied").write_text(manifest["dataset_version"] + "\n")
    print(
        f"applied: accepted={len(kept)} ai_reviewed={reviewed} "
        f"quarantined={len(removed_ids)} version={manifest['dataset_version']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

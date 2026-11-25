#!/usr/bin/env python
"""Write a mixture-capped training view of a built corpus.

The full accepted corpus remains the archive. This script selects a balanced
subset under the family/domain caps and 30/40/25/5 difficulty targets in
``configs/synthesis/mix.yaml`` so a training run does not overfit the dominant
source. Splits are preserved; no group moves between splits.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from cyberlite.data.build_synthesis import _load_mix_policy, _quota_sample
from cyberlite.data.schema import load_records, sha256_file, write_jsonl


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--splits-dir", default="data/processed/synthesis-production")
    parser.add_argument("--out-dir", default="data/processed/synthesis-production-balanced")
    parser.add_argument("--config", default="configs/synthesis/mix.yaml")
    parser.add_argument("--target", type=int, default=14000)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    records = []
    for name in ("train", "validation", "test"):
        path = Path(args.splits_dir) / f"{name}.jsonl"
        if path.exists():
            records.extend(load_records(path))
    if not records:
        raise SystemExit(f"no records in {args.splits_dir}")
    policy = _load_mix_policy(Path(args.config))
    selected, stats = _quota_sample(
        records, min(args.target, len(records)), policy, strict_mix=True
    )
    by_split = {"train": [], "validation": [], "test": []}
    for record in selected:
        by_split[record.split].append(record)
    out = Path(args.out_dir)
    if out.exists() and any(out.iterdir()) and not args.force:
        raise SystemExit(f"{out} is not empty; pass --force")
    out.mkdir(parents=True, exist_ok=True)
    files = {}
    for name, items in by_split.items():
        path = out / f"{name}.jsonl"
        write_jsonl(items, path)
        files[name] = {
            "path": str(path),
            "records": len(items),
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
    from collections import Counter

    def dist(key):
        counts = Counter()
        for record in selected:
            metadata = record.metadata or {}
            if key == "source":
                value = record.source
            elif key == "license":
                value = record.license
            elif key == "kind":
                value = record.kind
            else:
                value = str(metadata.get(key) or record.task)
            counts[value] += 1
        return dict(sorted(counts.items()))

    version_hash = hashlib.sha256()
    for record in sorted(selected, key=lambda item: item.id):
        version_hash.update(record.id.encode())
        version_hash.update(b"\x00")
    source_manifest_path = (
        Path(args.splits_dir).parent.parent / "manifests" / "synthesis-production" / "manifest.json"
    )
    source_manifest = (
        json.loads(source_manifest_path.read_text()) if source_manifest_path.is_file() else {}
    )
    dataset_version = f"{source_manifest.get('dataset_version', 'cyberlite-syn')}-balanced-{version_hash.hexdigest()[:8]}"
    out_manifest_dir = Path("data/manifests/synthesis-production-balanced")
    out_manifest_dir.mkdir(parents=True, exist_ok=True)
    full_manifest = dict(source_manifest)
    full_manifest.update(
        {
            "dataset_name": "cyberlite-synthesis-production-balanced",
            "dataset_version": dataset_version,
            "accepted_records": len(selected),
            "rejected_records": 0,
            "deferred_records": stats.get("deferred", 0),
            "split_counts": {name: len(items) for name, items in by_split.items()},
            "files": {
                **files,
                "preferences": source_manifest.get("files", {}).get("preferences", {}),
            },
            "balanced_view": True,
            "balanced_target": args.target,
            "balanced_selection": stats,
            "distributions": {
                "source": dist("source"),
                "license": dist("license"),
                "domain": dist("domain"),
                "task_family": dist("task_family"),
                "task": dist("task"),
                "difficulty": dist("difficulty"),
                "kind": dist("kind"),
                "origin": dist("origin"),
                "review_status": dist("review_status"),
            },
        }
    )
    (out_manifest_dir / "manifest.json").write_text(
        json.dumps(full_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest = {
        "source_splits": args.splits_dir,
        "dataset_version": dataset_version,
        "target": args.target,
        "selected": len(selected),
        "selection": stats,
        "splits": {name: len(items) for name, items in by_split.items()},
        "files": files,
        "policy": args.config,
        "note": "Mixture-capped training view; the full accepted corpus is the archive.",
    }
    (out / "balanced_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"selected {len(selected)} of {len(records)} records; splits {manifest['splits']}")
    print(f"manifest: {out / 'balanced_manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

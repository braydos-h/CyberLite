#!/usr/bin/env python
"""Recompute final-corpus statistics without changing record content.

The build computes token statistics on the screened pool before it drops
over-length records, so the raw token report can show a maximum above the
accepted corpus. This audit recomputes the report and distributions from the
actual split files and updates the manifest's measured fields.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from cyberlite.data.quality import load_token_counter, token_length_report
from cyberlite.data.schema import load_records, sha256_file


def _count(records, key) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for record in records:
        metadata = record.metadata or {}
        value = (
            str(metadata.get(key) or record.task)
            if key in {"task_family", "domain", "difficulty", "origin"}
            else (
                record.source
                if key == "source"
                else record.license
                if key == "license"
                else record.kind
                if key == "kind"
                else str(metadata.get(key) or "unset")
            )
        )
        counts[value] += 1
    return dict(sorted(counts.items()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--splits-dir", default="data/processed/synthesis-production")
    parser.add_argument("--manifest", default="data/manifests/synthesis-production/manifest.json")
    parser.add_argument("--tokenizer", default="Qwen/Qwen3.5-0.8B")
    parser.add_argument("--max-sequence-tokens", type=int, default=1024)
    args = parser.parse_args(argv)

    splits = Path(args.splits_dir)
    records = []
    counts: dict[str, int] = {}
    files: dict[str, Any] = {}
    for name in ("train", "validation", "test"):
        path = splits / f"{name}.jsonl"
        items = load_records(path)
        records.extend(items)
        counts[name] = len(items)
        files[name] = {
            "path": str(path),
            "records": len(items),
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
    counter, info = load_token_counter(args.tokenizer, local_only=True)
    report = token_length_report(records, counter, max_sequence_tokens=args.max_sequence_tokens)
    report["tokenizer_info"] = info
    report["removed_over_limit"] = "reported by build rejection ledger"
    report["truncation"]["removed_over_limit"] = "see quarantine.jsonl"

    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["token_lengths"] = report
    manifest["split_counts"] = counts
    manifest["accepted_records"] = len(records)
    manifest["distributions"] = {
        "source": _count(records, "source"),
        "license": _count(records, "license"),
        "domain": _count(records, "domain"),
        "task_family": _count(records, "task_family"),
        "task": _count(records, "task"),
        "difficulty": _count(records, "difficulty"),
        "kind": _count(records, "kind"),
        "origin": _count(records, "origin"),
        "review_status": _count(records, "review_status"),
    }
    manifest["files"].update(files)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (manifest_path.parent / "token_lengths_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"audited {len(records)} accepted records; max {report['tokens']['max']} tokens; "
        f"over {args.max_sequence_tokens}: {report['truncation']['over_limit']}"
    )
    print(f"updated {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

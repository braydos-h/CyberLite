#!/usr/bin/env python
"""Create deterministic review batches from a built corpus.

Batches are written outside Git (``data/processed``). A reviewer receives a
batch file, reads the full records, and writes a review JSON in the schema
understood by ``cyberlite.data.review``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from cyberlite.data.schema import Record, load_records, write_jsonl


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _sample(records: list[Record], count: int, seed: int, key) -> list[Record]:
    buckets: dict[str, list[Record]] = defaultdict(list)
    for record in sorted(records, key=lambda item: item.id):
        buckets[key(record)].append(record)
    selected: list[Record] = []
    cursor = 0
    keys = sorted(buckets)
    while len(selected) < count:
        added = False
        for bucket_key in keys:
            bucket = buckets[bucket_key]
            if cursor < len(bucket):
                selected.append(bucket[cursor])
                added = True
                if len(selected) >= count:
                    break
        if not added:
            break
        cursor += 1
    return selected


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--splits-dir", default="data/processed/synthesis-calibration")
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--per-batch", type=int, default=40)
    parser.add_argument("--seed", type=int, default=2026)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    splits_dir = Path(args.splits_dir)
    records: list[Record] = []
    for name in ("train", "validation", "test"):
        path = splits_dir / f"{name}.jsonl"
        if path.exists():
            records.extend(load_records(path))
    if not records:
        raise SystemExit(f"no records in {splits_dir}")
    out_dir = Path(args.out_dir or splits_dir / "review")
    out_dir.mkdir(parents=True, exist_ok=True)

    selected = _sample(
        records,
        min(args.count, len(records)),
        args.seed,
        key=lambda record: (
            str((record.metadata or {}).get("domain") or record.source),
            str((record.metadata or {}).get("task_family") or record.task),
        ),
    )
    batches: dict[str, list[Record]] = defaultdict(list)
    for record in selected:
        domain = str((record.metadata or {}).get("domain") or record.source)
        batches[domain].append(record)

    index: dict[str, object] = {
        "splits_dir": str(splits_dir),
        "selected": len(selected),
        "seed": args.seed,
        "batches": {},
    }
    batch_number = 0
    for domain in sorted(batches):
        domain_records = batches[domain]
        for start in range(0, len(domain_records), args.per_batch):
            chunk = domain_records[start : start + args.per_batch]
            batch_number += 1
            name = f"batch-{batch_number:03d}-{domain}"[:80]
            path = out_dir / f"{name}.jsonl"
            write_jsonl(chunk, path)
            index["batches"][name] = {
                "domain": domain,
                "records": len(chunk),
                "path": str(path),
                "ids": [record.id for record in chunk],
            }
    (out_dir / "review_index.json").write_text(
        json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {batch_number} batches / {len(selected)} records to {out_dir}")
    print(f"index: {out_dir / 'review_index.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

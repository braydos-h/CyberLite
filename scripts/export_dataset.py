#!/usr/bin/env python
"""Export training-format views from a built corpus.

The canonical record schema is retained. This script only partitions records by
kind, task family, and domain so a controlled experiment can select a mixture
without reimplementing the loader. Preference pairs use a separate schema and
are copied as-is after validation.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from cyberlite.data.schema import Record, load_records, sha256_file, write_jsonl


def _safe(name: str) -> str:
    return "".join(char if char.isalnum() or char in "-_." else "-" for char in name)[:80]


def _validate_preferences(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        payload = json.loads(line)
        for key in ("id", "prompt", "chosen", "rejected", "metadata"):
            if key not in payload:
                raise ValueError(f"{path}:{line_number}: missing {key}")
        if payload["id"] in seen:
            raise ValueError(f"{path}:{line_number}: duplicate preference id")
        seen.add(payload["id"])
        if payload["chosen"].strip() == payload["rejected"].strip():
            raise ValueError(f"{path}:{line_number}: chosen and rejected are identical")
        items.append(payload)
    return items


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--splits-dir", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    splits_dir = Path(args.splits_dir)
    out_dir = Path(args.out_dir)
    if out_dir.exists() and any(out_dir.iterdir()) and not args.force:
        raise SystemExit(f"{out_dir} is not empty; pass --force")
    out_dir.mkdir(parents=True, exist_ok=True)

    records: list[Record] = []
    for name in ("train", "validation", "test"):
        path = splits_dir / f"{name}.jsonl"
        if path.exists():
            records.extend(load_records(path))
    if not records:
        raise SystemExit(f"no records in {splits_dir}")

    by_kind: dict[str, list[Record]] = defaultdict(list)
    by_family: dict[str, list[Record]] = defaultdict(list)
    by_domain: dict[str, list[Record]] = defaultdict(list)
    for record in records:
        by_kind[record.kind].append(record)
        metadata = record.metadata or {}
        by_family[str(metadata.get("task_family") or record.task)].append(record)
        by_domain[str(metadata.get("domain") or record.source)].append(record)

    manifest: dict[str, Any] = {
        "splits_dir": str(splits_dir),
        "records": len(records),
        "kind": {name: len(items) for name, items in sorted(by_kind.items())},
        "task_family": {name: len(items) for name, items in sorted(by_family.items())},
        "domain": {name: len(items) for name, items in sorted(by_domain.items())},
        "files": {},
    }
    for name, items in sorted(by_kind.items()):
        path = out_dir / f"{_safe(name)}.jsonl"
        write_jsonl(items, path)
        manifest["files"][f"kind/{name}"] = {
            "path": str(path),
            "records": len(items),
            "sha256": sha256_file(path),
        }
    for prefix, groups in (("task_family", by_family), ("domain", by_domain)):
        target = out_dir / prefix
        target.mkdir(exist_ok=True)
        for name, items in sorted(groups.items()):
            path = target / f"{_safe(name)}.jsonl"
            write_jsonl(items, path)
            manifest["files"][f"{prefix}/{name}"] = {
                "path": str(path),
                "records": len(items),
                "sha256": sha256_file(path),
            }

    preferences_path = splits_dir / "preferences.jsonl"
    if preferences_path.is_file():
        preferences = _validate_preferences(preferences_path)
        write_jsonl_objects = out_dir / "preferences.jsonl"
        with write_jsonl_objects.open("w", encoding="utf-8") as handle:
            for item in preferences:
                handle.write(json.dumps(item, sort_keys=True) + "\n")
        manifest["preference_pairs"] = len(preferences)
        manifest["files"]["preferences"] = {
            "path": str(write_jsonl_objects),
            "records": len(preferences),
            "sha256": sha256_file(write_jsonl_objects),
        }

    (out_dir / "export_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"exported {len(records)} records to {out_dir}")
    print(json.dumps(manifest["kind"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

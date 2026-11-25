#!/usr/bin/env python
"""Validate held-out evaluation JSONL files and optionally freeze metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cyberlite.data.evalcheck import freeze_meta, validate_eval_file
from cyberlite.data.schema import load_records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+")
    parser.add_argument("--report", default="data/manifests/evaluation_validation.json")
    parser.add_argument("--train-dir", default=None, help="built split directory for overlap")
    parser.add_argument("--freeze", action="store_true", help="write .meta.json next to each file")
    parser.add_argument("--license", default="Synthetic")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    training_texts: list[str] = []
    if args.train_dir:
        for name in ("train", "validation", "test"):
            path = Path(args.train_dir) / f"{name}.jsonl"
            if path.exists():
                training_texts.extend(record.text_for_dedup() for record in load_records(path))
    reports = []
    ok = True
    for filename in args.files:
        report = validate_eval_file(filename, training_texts=training_texts or None)
        reports.append(report.to_dict())
        ok = ok and report.ok
        print(f"{filename}: {report.items} items, ok={report.ok}, issues={len(report.issues)}")
        if args.freeze:
            meta = freeze_meta(
                report,
                name=Path(filename).stem,
                license_id=args.license,
                description="Held-out CyberLite evaluation set. Evaluation-only; never a training source.",
            )
            meta_path = Path(filename).with_suffix(".meta.json")
            meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
            print(f"  wrote {meta_path}")
    destination = Path(args.report)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(reports, indent=2, sort_keys=True) + "\n")
    print(f"report: {destination}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

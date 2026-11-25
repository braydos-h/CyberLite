#!/usr/bin/env python3
"""Audit a prepared CyberLite dataset on CPU and generate review samples."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cyberlite.data.audit import audit_dataset  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, help="prepared split directory")
    parser.add_argument("--out", default=None, help="report directory (default: dataset dir)")
    parser.add_argument(
        "--review-out",
        default=None,
        help="local review sample JSONL (default: <dataset>/review_samples.jsonl)",
    )
    parser.add_argument("--review-size", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--tokenizer",
        default="",
        help="tokenizer id or local path; falls back to the manifest option",
    )
    parser.add_argument("--max-seq-len", type=int, default=2048)
    parser.add_argument("--eval-dir", default="data/evaluation")
    parser.add_argument(
        "--skip-contamination-verify",
        action="store_true",
        help="do not rebuild the evaluation index during the audit",
    )
    parser.add_argument("--registry", default="data/sources.yaml")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    dataset_dir = Path(args.dataset)
    out_dir = Path(args.out) if args.out else dataset_dir
    review_out = Path(args.review_out) if args.review_out else dataset_dir / "review_samples.jsonl"
    try:
        result = audit_dataset(
            dataset_dir,
            out_dir=out_dir,
            review_out=review_out,
            review_size=args.review_size,
            seed=args.seed,
            tokenizer=args.tokenizer,
            max_seq_len=args.max_seq_len,
            eval_dir=Path(args.eval_dir),
            verify_contamination=not args.skip_contamination_verify,
            registry_path=Path(args.registry),
        )
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result.report, indent=2))
    else:
        counts = result.report["counts"]
        print(f"dataset       : {result.report['dataset_version']}")
        print(f"accepted      : {counts['accepted_records']}")
        print(f"rejected      : {counts['rejected_records']}")
        print(
            "splits        : "
            + ", ".join(f"{name}={value}" for name, value in counts["splits"].items())
        )
        print(f"review sample : {len(result.review_samples)} records")
        print(f"audit JSON    : {out_dir / 'audit.json'}")
        print(f"audit Markdown: {out_dir / 'audit.md'}")
        print("manual review : NOT completed")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

#!/usr/bin/env python
"""Build a screened CyberLite synthesis corpus.

Reproducible stage build:

    python scripts/synthesize_dataset.py --config configs/synthesis/calibration.yaml

Ad-hoc override:

    python scripts/synthesize_dataset.py --stage calibration --limit 500 --force

The config file is authoritative for a documented build; command-line values
override it. Bulk splits are written outside Git.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml
from cyberlite.data.build_synthesis import (
    STAGE_TARGETS,
    BuildOptions,
    build,
    write_build,
)
from cyberlite.data.splits import SplitRatios
from cyberlite.logging_utils import configure_logging, get_logger

logger = get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=None, help="YAML build configuration")
    parser.add_argument("--packs", default=None, help="knowledge-pack directory")
    parser.add_argument("--out", default=None, help="output directory for bulk splits")
    parser.add_argument("--manifest-dir", default=None, help="manifest and report directory")
    parser.add_argument("--stage", choices=sorted(STAGE_TARGETS), default=None)
    parser.add_argument("--limit", type=int, default=None, help="override the stage target")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument(
        "--split-seed",
        type=int,
        default=None,
        help="split seed; kept separate so pilot-derived groups distribute across splits",
    )
    parser.add_argument("--pilot-dir", default=None)
    parser.add_argument(
        "--include-pilot",
        action="store_true",
        default=None,
        help="merge the frozen pilot splits into the new group-aware split",
    )
    parser.add_argument(
        "--merge-pilot",
        action="store_true",
        dest="include_pilot",
        help="alias for --include-pilot",
    )
    parser.add_argument("--evaluation-dir", default=None)
    parser.add_argument("--tokenizer", default=None)
    parser.add_argument(
        "--allow-tokenizer-download",
        action="store_true",
        help="allow the tokenizer to be fetched if it is not cached locally",
    )
    parser.add_argument("--max-sequence-tokens", type=int, default=None)
    parser.add_argument("--dedup-threshold", type=int, default=None)
    parser.add_argument("--semantic-threshold", type=float, default=None)
    parser.add_argument("--contamination-n", type=int, default=None)
    parser.add_argument("--contamination-threshold", type=float, default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--json", action="store_true", help="print a JSON summary")
    return parser


def _load_config(path: str) -> dict[str, Any]:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: configuration must be a mapping")
    return payload


def _resolve(args: argparse.Namespace) -> BuildOptions:
    config: dict[str, Any] = _load_config(args.config) if args.config else {}

    def pick(name: str, default: Any) -> Any:
        value = getattr(args, name, None)
        if value is not None:
            return value
        return config.get(name, default)

    stage = str(pick("stage", "calibration"))
    out_dir = Path(pick("out", f"data/processed/synthesis-{stage}"))
    manifest_dir = Path(pick("manifest_dir", f"data/manifests/synthesis-{stage}"))
    split = config.get("split", {})
    ratios = SplitRatios(
        train=float(split.get("train", 0.90)),
        validation=float(split.get("validation", 0.05)),
        test=float(split.get("test", 0.05)),
    )
    pilot_dir_value = pick("pilot_dir", "data/processed/pilot-v2")
    pilot_dir = (
        Path(str(pilot_dir_value))
        if pilot_dir_value and Path(str(pilot_dir_value)).exists()
        else None
    )
    include_pilot = bool(pick("include_pilot", False))
    tokenizer_local_only = bool(pick("tokenizer_local_only", True))
    if args.allow_tokenizer_download:
        tokenizer_local_only = False
    return BuildOptions(
        packs_dir=Path(str(pick("packs", "data/synthesis/knowledge"))),
        out_dir=out_dir,
        manifest_dir=manifest_dir,
        stage=stage,
        limit=pick("limit", None),
        seed=int(pick("seed", 42)),
        split_seed=int(pick("split_seed", 1337)),
        ratios=ratios,
        pilot_dir=pilot_dir,
        include_pilot=include_pilot,
        evaluation_dir=Path(str(pick("evaluation_dir", "data/evaluation"))),
        tokenizer=str(pick("tokenizer", "Qwen/Qwen3.5-0.8B")),
        tokenizer_local_only=tokenizer_local_only,
        max_sequence_tokens=int(pick("max_sequence_tokens", 1024)),
        dedup_threshold=int(pick("dedup_threshold", 3)),
        semantic_threshold=float(pick("semantic_threshold", 0.88)),
        contamination_n=int(pick("contamination_n", 13)),
        contamination_threshold=float(pick("contamination_threshold", 0.20)),
        force=args.force,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging()
    options = _resolve(args)
    if options.include_pilot and options.pilot_dir is None:
        print("error: --include-pilot requires a readable --pilot-dir", file=sys.stderr)
        return 2
    result = build(options)
    manifest = write_build(result, options)
    summary = {
        "stage": manifest["stage"],
        "target": manifest["stage_target"],
        "generated_candidates": manifest["generated_candidates"],
        "considered": manifest["considered_candidates"],
        "deferred": manifest["deferred_for_target"],
        "accepted": manifest["accepted_records"],
        "rejected": manifest["rejected_records"],
        "acceptance_rate": manifest["acceptance_rate"],
        "splits": manifest["split_counts"],
        "dataset_version": manifest["dataset_version"],
        "task_family": manifest["distributions"]["task_family"],
        "difficulty": manifest["distributions"]["difficulty"],
        "token_p95": manifest["token_lengths"]["tokens"]["p95"],
        "over_1024": manifest["token_lengths"]["truncation"]["over_limit"],
        "dedup": {
            "exact": manifest["deduplication"]["exact_duplicates"],
            "simhash": manifest["deduplication"]["simhash_near_duplicates"],
            "minhash": manifest["deduplication"]["semantic_near_duplicates"],
        },
        "contamination": manifest["contamination"].get("status"),
    }
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(
            f"{summary['stage']}: accepted {summary['accepted']} / considered "
            f"{summary['considered']} (target {summary['target']}), "
            f"rate {summary['acceptance_rate']:.1%}"
        )
        print("splits:", summary["splits"])
        print("version:", summary["dataset_version"])
        print("tokens p95:", summary["token_p95"], "over 1024:", summary["over_1024"])
        print("manifest:", options.manifest_dir / "manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

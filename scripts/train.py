#!/usr/bin/env python3
"""Train CyberLite with SFT, LoRA, or QLoRA."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cyberlite.config import load_config  # noqa: E402
from cyberlite.logging_utils import configure_logging  # noqa: E402
from cyberlite.training.preflight import run_preflight  # noqa: E402
from cyberlite.training.trainer import run_training  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train CyberLite with LoRA/QLoRA SFT.")
    parser.add_argument("--config", required=True, help="YAML experiment configuration")
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="override a config value, e.g. --set training.max_seq_length=512",
    )
    parser.add_argument("--smoke", action="store_true", help="bounded 2-step pipeline test")
    parser.add_argument(
        "--preflight",
        action="store_true",
        help=(
            "run CPU-only configuration, dataset, manifest, license, and revision checks "
            "without loading the model"
        ),
    )
    parser.add_argument(
        "--software-only",
        action="store_true",
        help="with --preflight, exit 0 when software checks pass even if research blockers remain",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="with --preflight, print machine-readable JSON",
    )
    parser.add_argument(
        "--estimate-only",
        action="store_true",
        help="write a memory/time planning estimate without downloading the model",
    )
    parser.add_argument("--force", action="store_true", help="allow writing to a non-empty run dir")
    parser.add_argument("--json-logs", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(json_logs=args.json_logs)
    try:
        config = load_config(args.config, args.set)
    except (OSError, ValueError) as exc:
        print(f"error: invalid configuration: {exc}", file=sys.stderr)
        return 2
    if args.smoke:
        already_smoke = config.training.smoke
        config.training.smoke = True
        if not already_smoke and not config.run.output_dir.endswith("-smoke"):
            config.run.output_dir = f"{config.run.output_dir}-smoke"
    if args.preflight:
        report = run_preflight(config, config_path=args.config)
        payload = report.to_dict()
        if args.json:
            print(json.dumps(payload, indent=2, default=str))
        else:
            print(f"software ready : {report.software_ready}")
            print(f"research ready : {report.research_ready}")
            for check, value in report.checks.items():
                status = value.get("status", "unknown") if isinstance(value, dict) else "unknown"
                print(f"{check:20s} {status}")
            if report.blockers:
                print("\nblockers:")
                for blocker in report.blockers:
                    print(f"  [{blocker.severity}] {blocker.code}: {blocker.message}")
            if report.warnings:
                print("\nwarnings:")
                for warning in report.warnings:
                    print(f"  - {warning}")
        if args.software_only:
            return 0 if report.software_ready else report.exit_code
        return report.exit_code
    try:
        result = run_training(config, force=args.force, estimate_only=args.estimate_only)
    except (FileExistsError, FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

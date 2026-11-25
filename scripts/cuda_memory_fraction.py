#!/usr/bin/env python3
"""Run a CyberLite CLI under a CUDA memory ceiling.

This emulates a smaller card by capping the process allocator. It is a planning
tool for the 4/6/8/12 GB classes, not a substitute for measuring the real card:
driver overhead, allocator fragmentation, and desktop VRAM use are not
reproduced.

Example:

    python scripts/cuda_memory_fraction.py --fraction 0.33 scripts/train.py \
      --config configs/qlora.yaml --set training.max_steps=20 \
      --set run.output_dir=runs/bringup-8gb --force

The fraction is relative to total device memory. 0.33 of 24 GB is ~8 GB.
"""

from __future__ import annotations

import argparse
import runpy
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a script with a CUDA per-process memory fraction.",
        epilog="Arguments after the script path are passed through unchanged.",
    )
    parser.add_argument(
        "--fraction",
        type=float,
        required=True,
        help="fraction of total device memory to allow, 0 < fraction <= 1",
    )
    parser.add_argument(
        "--device",
        type=int,
        default=0,
        help="CUDA device index (default: 0)",
    )
    parser.add_argument("script", help="Python script to run")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="script arguments")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not 0 < args.fraction <= 1:
        print("error: --fraction must be greater than 0 and at most 1", file=sys.stderr)
        return 2
    try:
        import torch
    except ImportError:
        print("error: PyTorch is not installed", file=sys.stderr)
        return 2
    if not torch.cuda.is_available():
        print("error: CUDA is not available", file=sys.stderr)
        return 2

    torch.cuda.set_per_process_memory_fraction(args.fraction, args.device)
    total = torch.cuda.get_device_properties(args.device).total_memory
    ceiling_gib = args.fraction * total / 1024**3
    print(
        f"cuda memory fraction {args.fraction:.2f} -> {ceiling_gib:.2f} GiB ceiling",
        file=sys.stderr,
    )

    sys.argv = [args.script, *args.args]
    runpy.run_path(args.script, run_name="__main__")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

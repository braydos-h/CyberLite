from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.cuda_memory_fraction import build_parser, main


def test_parser_accepts_passthrough_arguments() -> None:
    args = build_parser().parse_args(
        [
            "--fraction",
            "0.33",
            "scripts/train.py",
            "--config",
            "configs/qlora.yaml",
            "--set",
            "training.max_steps=20",
        ]
    )
    assert args.fraction == 0.33
    assert args.script == "scripts/train.py"
    assert "--set" in args.args


def test_fraction_must_be_in_range() -> None:
    assert main(["--fraction", "0", "scripts/train.py"]) == 2
    assert main(["--fraction", "1.5", "scripts/train.py"]) == 2


def test_help_exits_zero(repo_root: Path) -> None:
    result = subprocess.run(
        [sys.executable, "scripts/cuda_memory_fraction.py", "--help"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert "--fraction" in result.stdout

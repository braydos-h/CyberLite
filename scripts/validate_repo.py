#!/usr/bin/env python3
"""Validate repository structure and basic hygiene.

This is intentionally conservative: it checks for missing required files,
accidental weight artifacts, and obvious credentials. It is not a replacement
for a dedicated secret scanner.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cyberlite.config import load_config  # noqa: E402
from cyberlite.data.cleaning import find_secrets  # noqa: E402
from cyberlite.data.config import DatasetConfig  # noqa: E402

REQUIRED = [
    "README.md",
    "GOALS.md",
    "CHANGELOG.md",
    "AGENTS.md",
    "LICENSE",
    "NOTICE",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CODE_OF_CONDUCT.md",
    "CITATION.cff",
    "MODEL_CARD.md",
    "DATASET_CARD.md",
    "FUNDING.md",
    "GOVERNANCE.md",
    "docs/preregistration.md",
    "docs/compute-budget.md",
    "docs/gpu-bringup.md",
    "pyproject.toml",
    "requirements.txt",
    "configs/low_vram.yaml",
    "configs/lora.yaml",
    "configs/qlora.yaml",
    "configs/distillation.yaml",
    "configs/dataset_pilot.yaml",
    "data/sources.yaml",
    "scripts/check_hardware.py",
    "scripts/prepare_dataset.py",
    "scripts/audit_dataset.py",
    "scripts/train.py",
    "scripts/evaluate.py",
    "scripts/quantize.py",
    "scripts/benchmark.py",
    "scripts/compute_budget.py",
    "scripts/cuda_memory_fraction.py",
    "scripts/update_progress.py",
    "scripts/synthesize_dataset.py",
    "scripts/export_dataset.py",
    "scripts/plan_mixture.py",
    "scripts/sample_reviews.py",
    "scripts/apply_reviews.py",
    "scripts/validate_evaluation.py",
    "scripts/build_final_report.py",
    "scripts/balance_dataset.py",
    "scripts/audit_synthesis.py",
    "configs/lora_synthesis.yaml",
    "data/manifests/final_report.json",
    "docs/synthesis.md",
    "data/synthesis/knowledge/_schema.json",
    "data/synthesis/eval/_schema.json",
    "cyberlite/__init__.py",
    "cyberlite/data/integrity.py",
    "cyberlite/data/licensing.py",
    "cyberlite/data/synthesis.py",
    "cyberlite/data/grounded.py",
    "cyberlite/data/detection.py",
    "cyberlite/data/build_synthesis.py",
    "cyberlite/data/review.py",
    "cyberlite/data/semantic.py",
    "cyberlite/data/evalcheck.py",
    "cyberlite/training/licensing.py",
    "cyberlite/training/preflight.py",
    "data/manifests/pilot-v2/manifest.json",
    "paper/main.tex",
    "paper/references.bib",
    ".github/workflows/ci.yml",
]

FORBIDDEN_SUFFIXES = {
    ".safetensors",
    ".bin",
    ".pt",
    ".pth",
    ".gguf",
    ".onnx",
    ".ckpt",
    ".pem",
    ".key",
}
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "runs",
    "models",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "data/processed",
}
SKIP_SECRET_SCAN = {"tests", "data/seed", "data/evaluation", ".github"}


def _tracked_or_walked() -> list[Path]:
    try:
        output = subprocess.check_output(
            ["git", "ls-files"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL, timeout=15
        )
        paths = [ROOT / line for line in output.splitlines() if line.strip()]
        if paths:
            return paths
    except (OSError, subprocess.SubprocessError):
        pass
    paths: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        paths.append(path)
    return paths


def check_required() -> list[str]:
    return [f"missing required file: {name}" for name in REQUIRED if not (ROOT / name).is_file()]


def check_artifacts(paths: list[Path]) -> list[str]:
    errors = []
    for path in paths:
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            errors.append(f"forbidden artifact in repository: {relative}")
        if path.stat().st_size > 5 * 1024 * 1024:
            errors.append(f"file larger than 5 MiB: {relative}")
    return errors


def check_secrets(paths: list[Path]) -> list[str]:
    errors = []
    for path in paths:
        relative = path.relative_to(ROOT)
        if any(str(relative).startswith(prefix) for prefix in SKIP_SECRET_SCAN):
            continue
        if path.suffix.lower() not in {
            ".py",
            ".md",
            ".yaml",
            ".yml",
            ".toml",
            ".cff",
            ".txt",
            ".tex",
            ".bib",
        }:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        findings = find_secrets(text)
        high_confidence = [
            finding
            for finding in findings
            if finding.kind
            in {"private_key", "aws_access_key", "github_token", "github_pat", "openai_key"}
        ]
        if high_confidence:
            kinds = ", ".join(sorted({finding.kind for finding in high_confidence}))
            errors.append(f"possible credential in {relative}: {kinds}")
    return errors


def check_configs() -> list[str]:
    errors = []
    for path in sorted((ROOT / "configs").glob("*.yaml")):
        try:
            if path.name.startswith("dataset_"):
                DatasetConfig.load(path)
            else:
                load_config(path)
        except Exception as exc:
            errors.append(f"invalid config {path.name}: {exc}")
    return errors


def main() -> int:
    paths = _tracked_or_walked()
    errors = check_required() + check_artifacts(paths) + check_secrets(paths) + check_configs()
    if errors:
        print("repository validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(f"repository validation passed ({len(paths)} files checked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

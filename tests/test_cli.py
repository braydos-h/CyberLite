from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from cyberlite.config import load_config
from cyberlite.training.trainer import estimate_steps, run_training


def _run(script: str, *args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(cwd)
    return subprocess.run(
        [sys.executable, str(cwd / "scripts" / script), *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )


def test_check_hardware_json(repo_root: Path) -> None:
    result = _run("check_hardware.py", "--json", cwd=repo_root)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["hardware"]["cpu_count"] >= 1
    assert "training_estimate" in payload


def test_prepare_and_evaluate_dry_run(repo_root: Path, tmp_path: Path) -> None:
    out = tmp_path / "smoke"
    result = _run("prepare_dataset.py", "--smoke", "--out", str(out), "--force", cwd=repo_root)
    assert result.returncode == 0, result.stderr
    assert (out / "manifest.json").is_file()
    assert (out / "train.jsonl").is_file()
    eval_result = _run(
        "evaluate.py",
        "--dataset",
        str(repo_root / "data" / "evaluation" / "smoke_eval.jsonl"),
        "--dry-run",
        cwd=repo_root,
    )
    assert eval_result.returncode == 0, eval_result.stderr
    assert "no model was loaded" in eval_result.stdout


def test_benchmark_and_quantize_dry_run(repo_root: Path) -> None:
    benchmark = _run("benchmark.py", "--dry-run", "--prompt-lengths", "16,32", cwd=repo_root)
    assert benchmark.returncode == 0, benchmark.stderr
    quantization = _run(
        "quantize.py",
        "--dry-run",
        "--backend",
        "bitsandbytes",
        "--bits",
        "4",
        cwd=repo_root,
    )
    assert quantization.returncode == 0, quantization.stderr
    assert "estimated_weights_gb" in quantization.stdout


def test_train_estimate_only(repo_root: Path, tmp_path: Path) -> None:
    config = load_config(repo_root / "configs" / "qlora.yaml")
    config.run.output_dir = str(tmp_path / "run")
    payload = run_training(config, estimate_only=True)
    assert payload["plan"]["device"] in {"cpu", "cuda", "mps"}
    assert (tmp_path / "run" / "run_plan.json").is_file()
    assert (tmp_path / "run" / "config.effective.yaml").is_file()
    assert payload["note"].startswith("Planning estimate only")


def test_estimate_steps(repo_root: Path) -> None:
    config = load_config(repo_root / "configs" / "lora.yaml")
    config.training.max_steps = -1
    config.training.per_device_batch_size = 2
    config.training.gradient_accumulation_steps = 4
    config.training.epochs = 1
    assert estimate_steps(config, 80) == 10
    config.training.max_steps = 3
    assert estimate_steps(config, 80) == 3


def test_prepare_config_cli_backward_compatible(tmp_path: Path, repo_root: Path) -> None:
    import json

    (tmp_path / "data").mkdir()
    (tmp_path / "configs").mkdir()
    source = {
        "id": "cli-1",
        "source": "cli",
        "license": "Synthetic",
        "prompt": "How should an administrator verify a firewall rule?",
        "response": (
            "Verify the rule in a staging environment, confirm the default-deny policy, "
            "and record the test evidence. "
        )
        * 4,
        "metadata": {"source_version": "v1", "upstream_id": "cli-1"},
    }
    (tmp_path / "data" / "cli.jsonl").write_text(json.dumps(source) + "\n", encoding="utf-8")
    (tmp_path / "data" / "sources.yaml").write_text(
        """
schema_version: 1
sources:
  cli:
    title: CLI source
    kind: jsonl
    license: Synthetic
    enabled: true
    revision: v1
""",
        encoding="utf-8",
    )
    config = tmp_path / "configs" / "build.yaml"
    config.write_text(
        """
schema_version: 1
name: cli-test
out_dir: processed
manifest_dir: manifests
raw_dir: raw
cache_dir: cache
eval_dir: evaluation
registry: data/sources.yaml
download: false
tokenizer: ""
sources:
  cli:
    paths: [data/cli.jsonl]
""",
        encoding="utf-8",
    )
    result = _run(
        "prepare_dataset.py",
        "--config",
        str(config),
        "--offline",
        "--force",
        cwd=repo_root,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "processed" / "manifest.json").is_file()
    assert (tmp_path / "manifests" / "quality_report.json").is_file()

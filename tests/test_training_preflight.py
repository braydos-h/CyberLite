from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from cyberlite.config import PINNED_QWEN35_REVISION, load_config
from cyberlite.training.preflight import preregistration_status, run_preflight


def _write_config(
    path: Path,
    built: dict,
    *,
    smoke: bool = False,
    revision: str = PINNED_QWEN35_REVISION,
    license_id: str = "Public-Domain",
) -> Path:
    paths = built["paths"]
    manifest = built["manifest"]
    counts = built["manifest_data"]["split_counts"]
    text = f"""
schema_version: 1
run:
  name: preflight-test
  output_dir: {built["root"] / "run"}
model:
  id: Qwen/Qwen3.5-0.8B
  revision: {revision}
  require_pinned_revision: true
  matched_baseline: true
training:
  smoke: {str(smoke).lower()}
  max_steps: 2
data:
  train_file: {paths["train"]}
  validation_file: {paths["validation"]}
  test_file: {paths["test"]}
  manifest_file: {manifest}
  dataset_version: {built["version"]}
  expected_split_counts:
    train: {counts.get("train", 0)}
    validation: {counts.get("validation", 0)}
    test: {counts.get("test", 0)}
  require_manifest: true
  verify_integrity: true
  require_provenance: {str(not smoke).lower()}
  require_validation: true
  require_contamination_screen: false
  require_license: true
  allowed_licenses:
    - {license_id}
  require_resolved_licenses: false
  allow_unresolved_licenses: []
"""
    path.write_text(text, encoding="utf-8")
    return path


def _run_cli(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(repo_root)
    return subprocess.run(
        [sys.executable, str(repo_root / "scripts" / "train.py"), *args],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_preflight_software_ready_but_research_blocked(dataset_builder, tmp_path: Path) -> None:
    built = dataset_builder(name="preflight")
    config_path = _write_config(tmp_path / "preflight.yaml", built)
    config = load_config(config_path)
    report = run_preflight(config, config_path=config_path)
    assert report.software_ready, [blocker.to_dict() for blocker in report.blockers]
    assert not report.research_ready
    assert report.exit_code == 1
    assert report.checks["manifest_integrity"]["status"] == "pass"
    assert report.checks["dataset_availability"]["status"] == "pass"
    assert report.checks["model_revision"]["matches_baseline"] is True
    assert report.checks["hardware"]["status"] in {"pass", "warn", "fail"}
    assert "detected" in report.checks["hardware"]
    codes = {blocker.code for blocker in report.blockers}
    assert "manual_review_pending" in codes
    assert "preregistration_not_external" in codes


def test_preflight_missing_dataset_fails_software_checks(dataset_builder, tmp_path: Path) -> None:
    built = dataset_builder(name="preflight-missing")
    config_path = _write_config(tmp_path / "missing.yaml", built)
    Path(built["paths"]["train"]).unlink()
    config = load_config(config_path)
    report = run_preflight(config, config_path=config_path)
    assert not report.software_ready
    assert not report.research_ready
    assert report.exit_code == 3
    assert any(blocker.code == "dataset_file_missing" for blocker in report.blockers)


def test_preflight_json_cli_and_software_only_exit(
    dataset_builder, repo_root: Path, tmp_path: Path
) -> None:
    built = dataset_builder(name="preflight-cli")
    config_path = _write_config(tmp_path / "cli.yaml", built)
    result = _run_cli(
        repo_root,
        "--config",
        str(config_path),
        "--preflight",
        "--software-only",
        "--json",
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["software_ready"] is True
    assert payload["research_ready"] is False
    assert payload["exit_code"] == 1


def test_preflight_cli_fails_on_missing_dataset(
    dataset_builder, repo_root: Path, tmp_path: Path
) -> None:
    built = dataset_builder(name="preflight-cli-fail")
    config_path = _write_config(tmp_path / "cli-fail.yaml", built)
    Path(built["paths"]["train"]).unlink()
    result = _run_cli(repo_root, "--config", str(config_path), "--preflight", "--json")
    assert result.returncode == 3, result.stderr
    payload = json.loads(result.stdout)
    assert payload["software_ready"] is False
    assert any(blocker["code"] == "dataset_file_missing" for blocker in payload["blockers"])


def test_preregistration_is_not_marked_complete(repo_root: Path) -> None:
    status = preregistration_status(repo_root / "docs" / "preregistration.md")
    assert status["status"] == "draft"
    assert status["externally_registered"] is False


def test_smoke_preflight_uses_relaxed_pathway(dataset_builder, tmp_path: Path) -> None:
    built = dataset_builder(
        name="preflight-smoke",
        license_id="Synthetic",
        provenance=False,
        version=None,
    )
    # The smoke fixture has no dataset version; the smoke profile does not
    # require one. Keep expected counts out of the version check.
    config_path = _write_config(tmp_path / "smoke.yaml", built, smoke=True, license_id="Synthetic")
    text = config_path.read_text(encoding="utf-8")
    text = text.replace(f"  dataset_version: {built['version']}\n", "  dataset_version: null\n")
    config_path.write_text(text, encoding="utf-8")
    config = load_config(config_path)
    report = run_preflight(config, config_path=config_path)
    assert report.software_ready, [blocker.to_dict() for blocker in report.blockers]
    assert not report.research_ready
    assert any(blocker.code == "smoke_not_research" for blocker in report.blockers)

from __future__ import annotations

from pathlib import Path

import pytest
from cyberlite.compute_budget import (
    ComputeAssumptions,
    build_report,
    estimate_evaluation,
    estimate_training_run,
    gpu_hours_from_flops,
    render_markdown,
    training_flops,
)
from cyberlite.config import load_config


def test_training_flops_matches_six_nd() -> None:
    assert training_flops(1.0, 1_000) == 6.0 * 1e9 * 1_000


def test_training_flops_rejects_bad_inputs() -> None:
    with pytest.raises(ValueError):
        training_flops(0.0, 1_000)
    with pytest.raises(ValueError):
        training_flops(1.0, -1)


def test_gpu_hours_scale_inversely_with_throughput() -> None:
    slow = gpu_hours_from_flops(1e18, 10.0)
    fast = gpu_hours_from_flops(1e18, 20.0)
    assert slow == pytest.approx(fast * 2)


def test_assumptions_reject_impossible_values() -> None:
    with pytest.raises(ValueError):
        ComputeAssumptions(effective_tflops=0)
    with pytest.raises(ValueError):
        ComputeAssumptions(contingency=-0.1)
    with pytest.raises(ValueError):
        ComputeAssumptions(gpu_hour_usd=-1)


def test_training_estimate_uses_config(repo_root: Path) -> None:
    config = load_config(repo_root / "configs" / "qlora.yaml")
    estimate = estimate_training_run(
        config,
        config_path="configs/qlora.yaml",
        assumptions=ComputeAssumptions(train_tokens_per_epoch=1_000_000),
        epochs=2,
    )
    assert estimate.total_tokens == 2_000_000
    assert estimate.parameters_b == pytest.approx(0.853)
    # 1 batch * 8 accumulation * 1024 tokens
    assert estimate.steps_per_epoch == 122
    assert estimate.gpu_hours > 0
    assert estimate.cost_usd > 0


def test_training_estimate_requires_parameter_count(repo_root: Path) -> None:
    config = load_config(repo_root / "configs" / "qlora.yaml")
    config.model.parameters_b = None
    with pytest.raises(ValueError, match="parameters_b"):
        estimate_training_run(
            config,
            config_path="configs/qlora.yaml",
            assumptions=ComputeAssumptions(),
        )


def test_evaluation_estimate_counts_all_conditions() -> None:
    one = estimate_evaluation(
        conditions=1,
        items_per_condition=10_000,
        tokens_per_item=100,
        assumptions=ComputeAssumptions(inference_tokens_per_second=100),
    )
    two = estimate_evaluation(
        conditions=2,
        items_per_condition=10_000,
        tokens_per_item=100,
        assumptions=ComputeAssumptions(inference_tokens_per_second=100),
    )
    assert two["total_tokens"] == 2 * one["total_tokens"]
    assert two["gpu_hours"] == pytest.approx(2 * one["gpu_hours"])


def test_report_totals_include_contingency(repo_root: Path) -> None:
    report = build_report(
        [repo_root / "configs" / "lora.yaml", repo_root / "configs" / "qlora.yaml"],
        assumptions=ComputeAssumptions(
            train_tokens_per_epoch=1_000_000,
            contingency=0.25,
            gpu_hour_usd=1.0,
        ),
        epochs=1,
        distillation_tokens=1_000_000,
        eval_conditions=2,
    )
    assert len(report.training) == 2
    assert report.distillation is not None
    assert report.evaluation is not None
    base = sum(row.gpu_hours for row in report.training)
    base += report.distillation["gpu_hours"] + report.evaluation["gpu_hours"]
    assert report.totals["base_gpu_hours"] == pytest.approx(base, abs=0.01)
    assert report.totals["total_gpu_hours"] == pytest.approx(base * 1.25, abs=0.01)
    assert report.totals["total_cost_usd"] == pytest.approx(report.totals["total_gpu_hours"])


def test_markdown_report_has_tables(repo_root: Path) -> None:
    report = build_report(
        [repo_root / "configs" / "qlora.yaml"],
        assumptions=ComputeAssumptions(train_tokens_per_epoch=1_000_000),
        epochs=1,
    )
    markdown = render_markdown(report)
    assert "### Totals" in markdown
    assert "GPU-hours" in markdown
    assert "planning estimates" in markdown


def test_cli_json_output(repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(repo_root)
    from cyberlite.compute_budget import main

    code = main(["--config", "configs/qlora.yaml", "--train-tokens", "1000000"])
    assert code == 0


def test_report_parameters_override(repo_root: Path) -> None:
    report = build_report(
        [repo_root / "configs" / "qlora.yaml"],
        assumptions=ComputeAssumptions(train_tokens_per_epoch=1_000_000),
        epochs=1,
        parameters_b=26.0,
    )
    assert report.training[0].parameters_b == 26.0
    assert report.training[0].gpu_hours > 1


def test_cli_markdown_contains_total(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(repo_root)
    from cyberlite.compute_budget import main

    code = main(["--config", "configs/qlora.yaml", "--markdown"])
    assert code == 0
    output = capsys.readouterr().out
    assert "**Total**" in output

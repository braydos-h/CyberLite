from __future__ import annotations

from cyberlite.hardware import (
    detect_hardware,
    estimate_cost,
    estimate_inference_memory_gb,
    estimate_training_memory_gb,
    estimate_weights_memory_gb,
    recommend_tier,
)


def test_detect_hardware_returns_sane_values() -> None:
    hardware = detect_hardware()
    assert hardware.cpu_count >= 1
    assert hardware.ram_gb > 0
    assert hardware.recommended_device in {"cpu", "cuda", "mps"}
    assert hardware.tier


def test_weight_estimates() -> None:
    assert estimate_weights_memory_gb(0.8, bits=16) == 1.49
    assert estimate_weights_memory_gb(0.8, bits=4) == 0.373
    assert estimate_weights_memory_gb(0.8, bits=4) < estimate_weights_memory_gb(0.8, bits=16)


def test_training_estimate_decreases_with_checkpointing() -> None:
    with_checkpointing = estimate_training_memory_gb(
        0.8, seq_length=2048, gradient_checkpointing=True
    )
    without = estimate_training_memory_gb(0.8, seq_length=2048, gradient_checkpointing=False)
    assert with_checkpointing["estimated_peak_gb"] < without["estimated_peak_gb"]


def test_inference_estimate_grows_with_context() -> None:
    short = estimate_inference_memory_gb(0.8, bits=4, context_tokens=1024)
    long = estimate_inference_memory_gb(0.8, bits=4, context_tokens=8192)
    assert long["estimated_peak_gb"] > short["estimated_peak_gb"]


def test_cost_requires_explicit_rates() -> None:
    result = estimate_cost(3600)
    assert "compute_cost_usd" not in result
    assert "note" in result
    priced = estimate_cost(3600, cost_per_hour_usd=0.5)
    assert priced["compute_cost_usd"] == 0.5


def test_recommend_tier_cpu() -> None:
    hardware = detect_hardware()
    recommendation = recommend_tier(hardware)
    assert recommendation["tier"] == hardware.tier
    assert recommendation["notes"]

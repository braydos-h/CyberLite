"""Opt-in integration tests that download Qwen3.5-0.8B.

Run with: CYBERLITE_RUN_INTEGRATION=1 pytest tests/integration -q
"""

from __future__ import annotations

import os

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("CYBERLITE_RUN_INTEGRATION") != "1",
        reason="set CYBERLITE_RUN_INTEGRATION=1 to download model weights",
    ),
]

MODEL_ID = "Qwen/Qwen3.5-0.8B"


def test_architecture_and_lora_backward() -> None:
    import torch
    from cyberlite.config import PINNED_QWEN35_REVISION, ExperimentConfig
    from cyberlite.training.dataset import DataCollatorForCausalLM, build_datasets
    from cyberlite.training.lora import apply_lora, prepare_for_training
    from cyberlite.training.model import freeze_vision_tower, load_base_model
    from transformers import AutoConfig, AutoTokenizer

    config = AutoConfig.from_pretrained(MODEL_ID)
    assert config.architectures == ["Qwen3_5ForConditionalGeneration"]
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    assert tokenizer.convert_tokens_to_ids("<|fim_middle|>") != tokenizer.unk_token_id

    experiment = ExperimentConfig()
    experiment.model.revision = PINNED_QWEN35_REVISION
    experiment.model.require_pinned_revision = True
    experiment.model.dtype = "float32"
    experiment.lora.r = 4
    experiment.lora.alpha = 8
    experiment.training.gradient_checkpointing = True
    hardware = type(
        "H",
        (),
        {"recommended_device": "cpu", "cuda_available": False, "mps_available": False, "gpus": []},
    )()
    model, tokenizer, auto_class = load_base_model(
        experiment, for_training=True, device="cpu", hardware=hardware
    )
    assert auto_class == "AutoModelForImageTextToText"
    freeze_vision_tower(model)
    model = apply_lora(model, experiment.lora)
    model = prepare_for_training(model, experiment)
    train, _ = build_datasets(
        tokenizer,
        train_file="data/processed/smoke/train.jsonl",
        validation_file=None,
        max_seq_length=128,
        system_prompt="You are CyberLite.",
        max_train_samples=2,
        allowed_licenses=["Synthetic"],
        require_resolved_licenses=False,
    )
    batch = DataCollatorForCausalLM(tokenizer)([train[0], train[1]])
    model.train()
    output = model(**batch)
    output.loss.backward()
    assert torch.isfinite(output.loss).item()
    assert any(
        parameter.grad is not None and parameter.grad.abs().sum() > 0
        for parameter in model.parameters()
        if parameter.requires_grad
    )

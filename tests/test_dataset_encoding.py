from __future__ import annotations

import pytest
from cyberlite.data.schema import Record
from cyberlite.training.dataset import (
    DataCollatorForCausalLM,
    SFTDataset,
    encode_chat,
    encode_completion,
    encode_fim,
    render_chat,
)


@pytest.fixture
def messages() -> list[dict[str, str]]:
    return [
        {"role": "user", "content": "List two SSH hardening steps."},
        {
            "role": "assistant",
            "content": "Disable password authentication and restrict allowed users.",
        },
    ]


def test_render_chat_adds_system_and_generation_prompt(fake_tokenizer) -> None:
    text = render_chat(
        fake_tokenizer,
        [{"role": "user", "content": "hi"}],
        system_prompt="system",
        add_generation_prompt=True,
    )
    assert "system" in text
    assert text.endswith("<|im_start|>assistant\n")


def test_encode_chat_masks_prompt(fake_tokenizer, messages) -> None:
    encoded = encode_chat(fake_tokenizer, messages, max_seq_length=256)
    assert encoded is not None
    decoded_labels = fake_tokenizer.decode([label for label in encoded["labels"] if label != -100])
    assert "Disable password authentication" in decoded_labels
    assert "List two SSH hardening steps" not in decoded_labels
    # EOS is supervised so the model learns to stop.
    assert encoded["labels"][-1] == fake_tokenizer.eos_token_id


def test_encode_chat_rejects_all_masked(fake_tokenizer) -> None:
    encoded = encode_chat(
        fake_tokenizer,
        [{"role": "assistant", "content": "x"}],
        max_seq_length=4,
    )
    assert encoded is None


def test_encode_completion_masks_prompt(fake_tokenizer) -> None:
    encoded = encode_completion(fake_tokenizer, "prompt", "response", max_seq_length=256)
    assert encoded is not None
    decoded = fake_tokenizer.decode([label for label in encoded["labels"] if label != -100])
    assert decoded.startswith("response")
    assert len(encoded["labels"]) == len(encoded["input_ids"])


def test_encode_fim_uses_control_tokens(fake_tokenizer) -> None:
    encoded = encode_fim(fake_tokenizer, "def f():\n", "\n", "    return 1", max_seq_length=256)
    assert encoded is not None
    decoded = fake_tokenizer.decode(encoded["input_ids"])
    assert "<|fim_prefix|>" in decoded
    assert "<|fim_suffix|>" in decoded
    assert "<|fim_middle|>" in decoded
    supervised = fake_tokenizer.decode([label for label in encoded["labels"] if label != -100])
    assert supervised.startswith("    return 1")


def test_sft_dataset_auto_format(fake_tokenizer, messages) -> None:
    records = [
        Record(id="", source="unit", license="Synthetic", messages=messages),
        Record(
            id="",
            source="unit",
            license="Synthetic",
            prefix="grep ",
            suffix=" /var/log",
            middle='"error"',
        ),
    ]
    dataset = SFTDataset(records, fake_tokenizer, max_seq_length=256, system_prompt=None)
    assert len(dataset) == 2
    assert dataset.stats.examples == 2
    assert dataset.stats.supervised_tokens > 0
    item = dataset[0]
    assert set(item) == {"input_ids", "attention_mask", "labels"}


def test_collator_pads_and_masks(fake_tokenizer) -> None:
    dataset = SFTDataset(
        [
            Record(
                id="a",
                source="unit",
                license="Synthetic",
                prompt="a",
                response="short",
            ),
            Record(
                id="b",
                source="unit",
                license="Synthetic",
                prompt="b",
                response="a much longer response than the other one",
            ),
        ],
        fake_tokenizer,
        max_seq_length=256,
        system_prompt=None,
    )
    batch = DataCollatorForCausalLM(fake_tokenizer, pad_to_multiple_of=8)([dataset[0], dataset[1]])
    assert batch["input_ids"].shape == batch["labels"].shape
    assert batch["input_ids"].shape[1] % 8 == 0
    assert (batch["labels"] == -100).any()

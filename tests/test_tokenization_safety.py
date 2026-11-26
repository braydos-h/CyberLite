from __future__ import annotations

import pytest
from cyberlite.data.schema import Record
from cyberlite.training.dataset import SFTDataset, encode_chat, encode_completion, render_chat


def _offsets(fake_tokenizer, text: str) -> list[tuple[int, int]]:
    return list(
        fake_tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)[
            "offset_mapping"
        ]
    )


def test_repeated_user_and_assistant_text_masks_only_assistant(fake_tokenizer) -> None:
    messages = [
        {"role": "user", "content": "repeat me exactly"},
        {"role": "assistant", "content": "repeat me exactly"},
    ]
    encoded = encode_chat(fake_tokenizer, messages, max_seq_length=256, system_prompt=None)
    assert encoded is not None
    full = render_chat(fake_tokenizer, messages, system_prompt=None)
    offsets = _offsets(fake_tokenizer, full)
    user_start = full.find("repeat me exactly")
    assistant_start = full.find("repeat me exactly", user_start + 1)
    assert user_start >= 0 and assistant_start > user_start

    user_token_indices = [
        index
        for index, (start, end) in enumerate(offsets)
        if start >= user_start and start < user_start + len("repeat me exactly")
    ]
    assistant_token_indices = [
        index
        for index, (start, end) in enumerate(offsets)
        if start >= assistant_start and start < assistant_start + len("repeat me exactly")
    ]
    assert user_token_indices
    assert assistant_token_indices
    assert all(encoded["labels"][index] == -100 for index in user_token_indices)
    assert all(encoded["labels"][index] != -100 for index in assistant_token_indices)


def test_assistant_text_embedded_in_user_text_is_not_supervised(fake_tokenizer) -> None:
    messages = [
        {"role": "user", "content": "Explain why 'disable root login' matters."},
        {"role": "assistant", "content": "disable root login"},
    ]
    encoded = encode_chat(fake_tokenizer, messages, max_seq_length=256, system_prompt=None)
    assert encoded is not None
    full = render_chat(fake_tokenizer, messages, system_prompt=None)
    offsets = _offsets(fake_tokenizer, full)
    first = full.find("disable root login")
    second = full.find("disable root login", first + 1)
    assert second > first
    prompt_positions = [
        index
        for index, (start, _end) in enumerate(offsets)
        if start >= first and start < first + len("disable root login")
    ]
    assert prompt_positions
    assert all(encoded["labels"][index] == -100 for index in prompt_positions)


def test_truncation_preserves_eos_and_reports_stats(fake_tokenizer) -> None:
    dataset = SFTDataset(
        [
            Record(
                id="long",
                source="unit",
                license="Synthetic",
                prompt="p" * 10,
                response="y" * 300,
            )
        ],
        fake_tokenizer,
        max_seq_length=64,
        system_prompt=None,
    )
    assert dataset.stats.truncated == 1
    assert dataset.stats.max_length == 64
    assert dataset.stats.discarded_reasons == {}
    assert dataset.stats.original_max_length > 64
    item = dataset[0]
    assert int(item["labels"][-1]) == fake_tokenizer.eos_token_id


def test_zero_supervision_after_truncation_is_discarded(fake_tokenizer) -> None:
    records = [
        Record(
            id="prompt-too-long",
            source="unit",
            license="Synthetic",
            prompt="p" * 300,
            response="short answer",
        ),
        Record(
            id="usable",
            source="unit",
            license="Synthetic",
            prompt="q",
            response="short answer",
        ),
    ]
    dataset = SFTDataset(records, fake_tokenizer, max_seq_length=64, system_prompt=None)
    assert len(dataset) == 1
    assert dataset.stats.skipped == 1
    assert dataset.stats.discarded_reasons["no_supervised_tokens_after_truncation"] == 1
    assert dataset.stats.truncated == 0


def test_drop_policy_discards_instead_of_truncating(fake_tokenizer) -> None:
    records = [
        Record(
            id="long",
            source="unit",
            license="Synthetic",
            prompt="p" * 10,
            response="y" * 300,
        ),
        Record(
            id="short",
            source="unit",
            license="Synthetic",
            prompt="q",
            response="short",
        ),
    ]
    dataset = SFTDataset(
        records,
        fake_tokenizer,
        max_seq_length=64,
        system_prompt=None,
        truncation_policy="drop",
    )
    assert len(dataset) == 1
    assert dataset.stats.skipped == 1
    assert dataset.stats.truncated == 0
    assert dataset.stats.discarded_reasons["truncated"] == 1
    assert dataset.stats.truncation_policy == "drop"


def test_completion_with_no_response_tokens_is_discarded(fake_tokenizer) -> None:
    assert encode_completion(fake_tokenizer, "prompt", "", max_seq_length=128) is None


def test_encode_chat_without_offsets_raises_actionable_error(fake_tokenizer) -> None:
    class NoOffsets:
        eos_token_id = fake_tokenizer.eos_token_id

        def apply_chat_template(self, messages, tokenize=False, **kwargs):
            return "".join(message["content"] for message in messages)

        def __call__(self, text, **kwargs):
            return {"input_ids": [1, 2, 3]}

    with pytest.raises(ValueError, match="offset mapping"):
        encode_chat(
            NoOffsets(),
            [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}],
            max_seq_length=128,
        )

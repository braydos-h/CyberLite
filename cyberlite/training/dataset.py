"""Tokenization and supervised fine-tuning datasets.

Assistant tokens are supervised; prompt/system tokens are masked with -100.
For chat data the mask is derived from tokenizer offset maps, which is more
robust than guessing token boundaries from rendered strings.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import torch
from torch.utils.data import Dataset

from cyberlite.data.schema import Record, load_records
from cyberlite.logging_utils import get_logger

logger = get_logger(__name__)

FIM_TOKENS = {
    "prefix": "<|fim_prefix|>",
    "suffix": "<|fim_suffix|>",
    "middle": "<|fim_middle|>",
    "pad": "<|fim_pad|>",
}


def render_chat(
    tokenizer: Any,
    messages: list[dict[str, str]],
    *,
    system_prompt: str | None = None,
    add_generation_prompt: bool = False,
    template_kwargs: dict[str, Any] | None = None,
) -> str:
    """Render a chat using the tokenizer's template with safe fallbacks."""

    prepared: list[dict[str, str]] = []
    if system_prompt and (not messages or messages[0]["role"] != "system"):
        prepared.append({"role": "system", "content": system_prompt})
    prepared.extend(messages)
    kwargs = dict(template_kwargs or {})
    try:
        return tokenizer.apply_chat_template(
            prepared,
            tokenize=False,
            add_generation_prompt=add_generation_prompt,
            **kwargs,
        )
    except (TypeError, ValueError):
        # Not every tokenizer/template accepts optional keywords such as
        # enable_thinking. Retry with the minimal contract before failing.
        return tokenizer.apply_chat_template(
            prepared, tokenize=False, add_generation_prompt=add_generation_prompt
        )


def _fill_middle_ids(tokenizer: Any) -> dict[str, int]:
    ids: dict[str, int] = {}
    for name, token in FIM_TOKENS.items():
        token_id = tokenizer.convert_tokens_to_ids(token)
        if token_id is None or token_id == getattr(tokenizer, "unk_token_id", None):
            raise ValueError(
                f"tokenizer does not define {token}; fill-in-the-middle training is unavailable. "
                "Use prefix-based completion instead (see docs/autocomplete.md)."
            )
        ids[name] = int(token_id)
    return ids


def _assistant_char_spans(full_text: str, messages: list[dict[str, str]]) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    cursor = 0
    for message in messages:
        if message["role"] != "assistant":
            continue
        content = message["content"]
        start = full_text.find(content, cursor)
        if start < 0:
            continue
        end = start + len(content)
        # Include the turn terminator when it immediately follows the content,
        # so the model learns where to stop.
        terminator = full_text.find("<|im_end|>", end)
        if terminator != -1 and terminator - end <= 8:
            end = terminator + len("<|im_end|>")
        spans.append((start, end))
        cursor = end
    return spans


def encode_chat(
    tokenizer: Any,
    messages: list[dict[str, str]],
    *,
    max_seq_length: int,
    system_prompt: str | None = None,
    template_kwargs: dict[str, Any] | None = None,
) -> dict[str, list[int]] | None:
    """Encode a chat example and supervise assistant turns only."""

    full_text = render_chat(
        tokenizer,
        messages,
        system_prompt=system_prompt,
        add_generation_prompt=False,
        template_kwargs=template_kwargs,
    )
    encoded = tokenizer(
        full_text,
        add_special_tokens=False,
        return_offsets_mapping=True,
    )
    input_ids: list[int] = list(encoded["input_ids"])
    offsets: list[tuple[int, int]] = list(encoded["offset_mapping"])
    labels = [-100] * len(input_ids)
    for start, end in _assistant_char_spans(full_text, messages):
        for index, (token_start, token_end) in enumerate(offsets):
            if token_start >= start and token_start < end and token_end > token_start:
                labels[index] = input_ids[index]
    if all(label == -100 for label in labels):
        return None
    return _finalize(input_ids, labels, tokenizer, max_seq_length)


def encode_completion(
    tokenizer: Any,
    prompt: str,
    response: str,
    *,
    max_seq_length: int,
) -> dict[str, list[int]] | None:
    """Encode prompt/response data, supervising only the response."""

    prompt_ids = list(tokenizer(prompt, add_special_tokens=False)["input_ids"])
    response_ids = list(tokenizer(response, add_special_tokens=False)["input_ids"])
    eos = _eos_id(tokenizer)
    if eos is not None:
        response_ids.append(eos)
    if not response_ids:
        return None
    input_ids = prompt_ids + response_ids
    labels = [-100] * len(prompt_ids) + response_ids
    return _finalize(input_ids, labels, tokenizer, max_seq_length)


def encode_fim(
    tokenizer: Any,
    prefix: str,
    suffix: str,
    middle: str,
    *,
    max_seq_length: int,
) -> dict[str, list[int]] | None:
    """Encode Qwen-style fill-in-the-middle data."""

    ids = _fill_middle_ids(tokenizer)
    prompt_text = (
        f"{FIM_TOKENS['prefix']}{prefix}{FIM_TOKENS['suffix']}{suffix}{FIM_TOKENS['middle']}"
    )
    prompt_ids = list(tokenizer(prompt_text, add_special_tokens=False)["input_ids"])
    middle_ids = list(tokenizer(middle, add_special_tokens=False)["input_ids"])
    eos = _eos_id(tokenizer)
    if eos is not None:
        middle_ids.append(eos)
    if not middle_ids:
        return None
    input_ids = prompt_ids + middle_ids
    labels = [-100] * len(prompt_ids) + middle_ids
    # Sanity check that the FIM control tokens survived tokenization.
    if ids["middle"] not in prompt_ids[-3:] and ids["middle"] not in prompt_ids:
        logger.warning("FIM middle token not found in tokenized prompt")
    return _finalize(input_ids, labels, tokenizer, max_seq_length)


def _eos_id(tokenizer: Any) -> int | None:
    value = getattr(tokenizer, "eos_token_id", None)
    return int(value) if value is not None else None


def _finalize(
    input_ids: list[int], labels: list[int], tokenizer: Any, max_seq_length: int
) -> dict[str, list[int]] | None:
    if not input_ids:
        return None
    input_ids = input_ids[:max_seq_length]
    labels = labels[:max_seq_length]
    if all(label == -100 for label in labels):
        return None
    eos = _eos_id(tokenizer)
    if eos is not None and input_ids[-1] != eos:
        input_ids.append(eos)
        labels.append(eos)
        input_ids = input_ids[:max_seq_length]
        labels = labels[:max_seq_length]
    attention_mask = [1] * len(input_ids)
    return {"input_ids": input_ids, "attention_mask": attention_mask, "labels": labels}


@dataclass
class DatasetStats:
    examples: int
    skipped: int
    tokens: int
    supervised_tokens: int
    max_length: int
    truncated: int

    def to_dict(self) -> dict[str, int]:
        return {
            "examples": self.examples,
            "skipped": self.skipped,
            "tokens": self.tokens,
            "supervised_tokens": self.supervised_tokens,
            "max_length": self.max_length,
            "truncated": self.truncated,
        }


class SFTDataset(Dataset[dict[str, torch.Tensor]]):
    """In-memory SFT dataset for chat, completion, or FIM records."""

    def __init__(
        self,
        records: list[Record],
        tokenizer: Any,
        *,
        max_seq_length: int = 1024,
        format: Literal["auto", "chat", "completion", "fim"] = "auto",
        system_prompt: str | None = None,
        template_kwargs: dict[str, Any] | None = None,
        max_samples: int | None = None,
    ) -> None:
        if max_seq_length < 64:
            raise ValueError("max_seq_length must be >= 64")
        self.tokenizer = tokenizer
        self.max_seq_length = max_seq_length
        self.records = records[:max_samples] if max_samples else records
        self.examples: list[dict[str, list[int]]] = []
        skipped = 0
        truncated = 0
        for record in self.records:
            encoded = self._encode(record, format, system_prompt, template_kwargs)
            if encoded is None:
                skipped += 1
                continue
            if len(encoded["input_ids"]) >= max_seq_length:
                truncated += 1
            self.examples.append(encoded)
        self.stats = DatasetStats(
            examples=len(self.examples),
            skipped=skipped,
            tokens=sum(len(item["input_ids"]) for item in self.examples),
            supervised_tokens=sum(
                1 for item in self.examples for label in item["labels"] if label != -100
            ),
            max_length=max((len(item["input_ids"]) for item in self.examples), default=0),
            truncated=truncated,
        )
        if not self.examples:
            raise ValueError(
                "no usable training examples after tokenization; check the data schema and "
                "sequence length"
            )

    def _encode(
        self,
        record: Record,
        format: Literal["auto", "chat", "completion", "fim"],
        system_prompt: str | None,
        template_kwargs: dict[str, Any] | None,
    ) -> dict[str, list[int]] | None:
        kind = record.kind if format == "auto" else format
        if kind == "chat":
            if not record.messages:
                return None
            return encode_chat(
                self.tokenizer,
                record.messages,
                max_seq_length=self.max_seq_length,
                system_prompt=system_prompt,
                template_kwargs=template_kwargs,
            )
        if kind == "fim":
            if record.prefix is None or record.suffix is None or record.middle is None:
                return None
            return encode_fim(
                self.tokenizer,
                record.prefix,
                record.suffix,
                record.middle,
                max_seq_length=self.max_seq_length,
            )
        if record.prompt is None or record.response is None:
            return None
        return encode_completion(
            self.tokenizer,
            record.prompt,
            record.response,
            max_seq_length=self.max_seq_length,
        )

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, index: int) -> dict[str, torch.Tensor]:
        item = self.examples[index]
        return {
            "input_ids": torch.tensor(item["input_ids"], dtype=torch.long),
            "attention_mask": torch.tensor(item["attention_mask"], dtype=torch.long),
            "labels": torch.tensor(item["labels"], dtype=torch.long),
        }


class DataCollatorForCausalLM:
    """Pad variable-length examples to the longest sequence in the batch."""

    def __init__(self, tokenizer: Any, *, pad_to_multiple_of: int = 8) -> None:
        pad_id = getattr(tokenizer, "pad_token_id", None)
        if pad_id is None:
            pad_id = getattr(tokenizer, "eos_token_id", None)
        if pad_id is None:
            raise ValueError("tokenizer has no pad_token_id or eos_token_id")
        self.pad_id = int(pad_id)
        self.pad_to_multiple_of = pad_to_multiple_of

    def __call__(self, features: list[dict[str, torch.Tensor]]) -> dict[str, torch.Tensor]:
        max_length = max(len(feature["input_ids"]) for feature in features)
        if self.pad_to_multiple_of:
            max_length = (
                (max_length + self.pad_to_multiple_of - 1)
                // self.pad_to_multiple_of
                * self.pad_to_multiple_of
            )
        batch: dict[str, list[torch.Tensor]] = {
            "input_ids": [],
            "attention_mask": [],
            "labels": [],
        }
        for feature in features:
            length = len(feature["input_ids"])
            padding = max_length - length
            batch["input_ids"].append(
                torch.cat(
                    [feature["input_ids"], torch.full((padding,), self.pad_id, dtype=torch.long)]
                )
            )
            batch["attention_mask"].append(
                torch.cat([feature["attention_mask"], torch.zeros(padding, dtype=torch.long)])
            )
            batch["labels"].append(
                torch.cat([feature["labels"], torch.full((padding,), -100, dtype=torch.long)])
            )
        return {key: torch.stack(values) for key, values in batch.items()}


def build_datasets(
    tokenizer: Any,
    *,
    train_file: str | Path,
    validation_file: str | Path | None,
    max_seq_length: int,
    format: Literal["auto", "chat", "completion", "fim"] = "auto",
    system_prompt: str | None = None,
    template_kwargs: dict[str, Any] | None = None,
    max_train_samples: int | None = None,
    max_eval_samples: int | None = None,
) -> tuple[SFTDataset, SFTDataset | None]:
    """Load JSONL records and build train/validation datasets."""

    train_records = load_records(train_file)
    train_dataset = SFTDataset(
        train_records,
        tokenizer,
        max_seq_length=max_seq_length,
        format=format,
        system_prompt=system_prompt,
        template_kwargs=template_kwargs,
        max_samples=max_train_samples,
    )
    validation_dataset = None
    if validation_file and Path(validation_file).is_file():
        val_records = load_records(validation_file)
        if val_records:
            validation_dataset = SFTDataset(
                val_records,
                tokenizer,
                max_seq_length=max_seq_length,
                format=format,
                system_prompt=system_prompt,
                template_kwargs=template_kwargs,
                max_samples=max_eval_samples,
            )
    return train_dataset, validation_dataset

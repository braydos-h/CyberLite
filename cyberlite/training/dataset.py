"""Tokenization and supervised fine-tuning datasets.

Assistant tokens are supervised; prompt/system tokens are masked with -100.
For chat data the mask is derived from tokenizer offset maps, which is more
robust than guessing token boundaries from rendered strings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import torch
from torch.utils.data import Dataset

from cyberlite.data.schema import Record, load_records
from cyberlite.logging_utils import get_logger
from cyberlite.training.licensing import (
    LicenseProfile,
    LicenseValidationError,
    validate_training_licenses,
)

logger = get_logger(__name__)

FIM_TOKENS = {
    "prefix": "<|fim_prefix|>",
    "suffix": "<|fim_suffix|>",
    "middle": "<|fim_middle|>",
    "pad": "<|fim_pad|>",
}

CHAT_TERMINATORS = ("<|im_end|>", "<|eot_id|>", "<|endoftext|>")


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
                "Use prefix-based completion instead."
            )
        ids[name] = int(token_id)
    return ids


def _assistant_char_spans(full_text: str, messages: list[dict[str, str]]) -> list[tuple[int, int]]:
    """Locate assistant content without matching repeated text in earlier turns.

    Searching each message from the previous message's end is essential: a
    user turn and an assistant turn may contain identical text, and a naive
    ``full_text.find`` would supervise the user copy.
    """

    spans: list[tuple[int, int]] = []
    cursor = 0
    for message in messages:
        content = message["content"]
        if not content:
            continue
        start = full_text.find(content, cursor)
        if start < 0:
            # The template transformed the content (for example by escaping).
            # Do not guess a span; under-supervising is safer than supervising
            # prompt tokens.
            continue
        end = start + len(content)
        cursor = end
        if message["role"] != "assistant":
            continue
        # Include the first terminator that immediately follows the content, so
        # the model learns where to stop. Only whitespace may intervene.
        for terminator_text in CHAT_TERMINATORS:
            terminator = full_text.find(terminator_text, end)
            if terminator != -1 and not full_text[end:terminator].strip():
                end = terminator + len(terminator_text)
                cursor = end
                break
        spans.append((start, end))
    return spans


@dataclass
class EncodingResult:
    """Internal tokenization result with enough detail for trustworthy stats."""

    input_ids: list[int] = field(default_factory=list)
    labels: list[int] = field(default_factory=list)
    original_length: int = 0
    truncated: bool = False
    discarded_reason: str | None = None

    @property
    def encoded(self) -> dict[str, list[int]] | None:
        if self.discarded_reason is not None:
            return None
        return {
            "input_ids": self.input_ids,
            "attention_mask": [1] * len(self.input_ids),
            "labels": self.labels,
        }

    @property
    def supervised_tokens(self) -> int:
        return sum(1 for label in self.labels if label != -100)


def encode_chat(
    tokenizer: Any,
    messages: list[dict[str, str]],
    *,
    max_seq_length: int,
    system_prompt: str | None = None,
    template_kwargs: dict[str, Any] | None = None,
    truncation_policy: Literal["truncate", "drop"] = "truncate",
    min_supervised_tokens: int = 1,
) -> dict[str, list[int]] | None:
    """Encode a chat example and supervise assistant turns only."""

    return _encode_chat_detailed(
        tokenizer,
        messages,
        max_seq_length=max_seq_length,
        system_prompt=system_prompt,
        template_kwargs=template_kwargs,
        truncation_policy=truncation_policy,
        min_supervised_tokens=min_supervised_tokens,
    ).encoded


def _encode_chat_detailed(
    tokenizer: Any,
    messages: list[dict[str, str]],
    *,
    max_seq_length: int,
    system_prompt: str | None = None,
    template_kwargs: dict[str, Any] | None = None,
    truncation_policy: Literal["truncate", "drop"] = "truncate",
    min_supervised_tokens: int = 1,
) -> EncodingResult:
    full_text = render_chat(
        tokenizer,
        messages,
        system_prompt=system_prompt,
        add_generation_prompt=False,
        template_kwargs=template_kwargs,
    )
    try:
        encoded = tokenizer(
            full_text,
            add_special_tokens=False,
            return_offsets_mapping=True,
        )
        offsets: list[tuple[int, int]] = list(encoded["offset_mapping"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            "the tokenizer did not return offset mappings; assistant-only masking "
            "cannot be verified. Use a fast tokenizer with offsets (for example the "
            "Qwen3.5 fast tokenizer) rather than fabricating a mask."
        ) from exc
    input_ids: list[int] = list(encoded["input_ids"])
    labels = [-100] * len(input_ids)
    spans = _assistant_char_spans(full_text, messages)
    if not spans:
        return EncodingResult(original_length=len(input_ids), discarded_reason="no_assistant_span")
    for start, end in spans:
        for index, (token_start, token_end) in enumerate(offsets):
            if token_start >= start and token_start < end and token_end > token_start:
                labels[index] = input_ids[index]
    return _finalize_result(
        input_ids,
        labels,
        tokenizer,
        max_seq_length,
        truncation_policy=truncation_policy,
        min_supervised_tokens=min_supervised_tokens,
    )


def encode_completion(
    tokenizer: Any,
    prompt: str,
    response: str,
    *,
    max_seq_length: int,
    truncation_policy: Literal["truncate", "drop"] = "truncate",
    min_supervised_tokens: int = 1,
) -> dict[str, list[int]] | None:
    """Encode prompt/response data, supervising only the response."""

    return _encode_completion_detailed(
        tokenizer,
        prompt,
        response,
        max_seq_length=max_seq_length,
        truncation_policy=truncation_policy,
        min_supervised_tokens=min_supervised_tokens,
    ).encoded


def _encode_completion_detailed(
    tokenizer: Any,
    prompt: str,
    response: str,
    *,
    max_seq_length: int,
    truncation_policy: Literal["truncate", "drop"] = "truncate",
    min_supervised_tokens: int = 1,
) -> EncodingResult:
    prompt_ids = list(tokenizer(prompt, add_special_tokens=False)["input_ids"])
    response_ids = list(tokenizer(response, add_special_tokens=False)["input_ids"])
    if not response_ids:
        return EncodingResult(original_length=len(prompt_ids), discarded_reason="empty_response")
    input_ids = prompt_ids + response_ids
    labels = [-100] * len(prompt_ids) + response_ids
    return _finalize_result(
        input_ids,
        labels,
        tokenizer,
        max_seq_length,
        truncation_policy=truncation_policy,
        min_supervised_tokens=min_supervised_tokens,
    )


def encode_fim(
    tokenizer: Any,
    prefix: str,
    suffix: str,
    middle: str,
    *,
    max_seq_length: int,
    truncation_policy: Literal["truncate", "drop"] = "truncate",
    min_supervised_tokens: int = 1,
) -> dict[str, list[int]] | None:
    """Encode Qwen-style fill-in-the-middle data."""

    return _encode_fim_detailed(
        tokenizer,
        prefix,
        suffix,
        middle,
        max_seq_length=max_seq_length,
        truncation_policy=truncation_policy,
        min_supervised_tokens=min_supervised_tokens,
    ).encoded


def _encode_fim_detailed(
    tokenizer: Any,
    prefix: str,
    suffix: str,
    middle: str,
    *,
    max_seq_length: int,
    truncation_policy: Literal["truncate", "drop"] = "truncate",
    min_supervised_tokens: int = 1,
) -> EncodingResult:
    ids = _fill_middle_ids(tokenizer)
    prompt_text = (
        f"{FIM_TOKENS['prefix']}{prefix}{FIM_TOKENS['suffix']}{suffix}{FIM_TOKENS['middle']}"
    )
    prompt_ids = list(tokenizer(prompt_text, add_special_tokens=False)["input_ids"])
    middle_ids = list(tokenizer(middle, add_special_tokens=False)["input_ids"])
    if not middle_ids:
        return EncodingResult(original_length=len(prompt_ids), discarded_reason="empty_response")
    input_ids = prompt_ids + middle_ids
    labels = [-100] * len(prompt_ids) + middle_ids
    # Sanity check that the FIM control tokens survived tokenization.
    if ids["middle"] not in prompt_ids[-3:] and ids["middle"] not in prompt_ids:
        logger.warning("FIM middle token not found in tokenized prompt")
    return _finalize_result(
        input_ids,
        labels,
        tokenizer,
        max_seq_length,
        truncation_policy=truncation_policy,
        min_supervised_tokens=min_supervised_tokens,
    )


def _eos_id(tokenizer: Any) -> int | None:
    value = getattr(tokenizer, "eos_token_id", None)
    return int(value) if value is not None else None


def _finalize_result(
    input_ids: list[int],
    labels: list[int],
    tokenizer: Any,
    max_seq_length: int,
    *,
    truncation_policy: Literal["truncate", "drop"] = "truncate",
    min_supervised_tokens: int = 1,
) -> EncodingResult:
    if not input_ids:
        return EncodingResult(original_length=0, discarded_reason="empty_sequence")
    if not any(label != -100 for label in labels):
        return EncodingResult(
            original_length=len(input_ids), discarded_reason="no_supervised_tokens"
        )
    eos = _eos_id(tokenizer)
    if eos is not None and input_ids[-1] != eos:
        input_ids = [*input_ids, eos]
        labels = [*labels, eos]
    original_length = len(input_ids)
    truncated = original_length > max_seq_length
    if truncated:
        if truncation_policy == "drop":
            return EncodingResult(
                original_length=original_length,
                truncated=True,
                discarded_reason="truncated",
            )
        if eos is not None:
            # Reserve the final position for EOS so a truncated example still
            # teaches the model to stop. Never exceed the configured length.
            input_ids = [*input_ids[: max_seq_length - 1], eos]
            labels = [*labels[: max_seq_length - 1], eos]
        else:
            input_ids = input_ids[:max_seq_length]
            labels = labels[:max_seq_length]
        # EOS alone is not real supervision. If truncation removed every
        # assistant/content token, discard the example rather than training on a
        # prompt that ends with a stop token.
        content_labels = labels[:-1] if eos is not None else labels
        if not any(label != -100 for label in content_labels):
            return EncodingResult(
                original_length=original_length,
                truncated=True,
                discarded_reason="no_supervised_tokens_after_truncation",
            )
    supervised = sum(1 for label in labels if label != -100)
    if supervised < min_supervised_tokens:
        return EncodingResult(
            original_length=original_length,
            truncated=truncated,
            discarded_reason=(
                "no_supervised_tokens_after_truncation" if truncated else "no_supervised_tokens"
            ),
        )
    return EncodingResult(
        input_ids=input_ids,
        labels=labels,
        original_length=original_length,
        truncated=truncated,
    )


@dataclass
class DatasetStats:
    examples: int
    skipped: int
    tokens: int
    supervised_tokens: int
    max_length: int
    truncated: int
    discarded_reasons: dict[str, int] = field(default_factory=dict)
    original_max_length: int = 0
    truncation_policy: str = "truncate"

    def to_dict(self) -> dict[str, Any]:
        return {
            "examples": self.examples,
            "skipped": self.skipped,
            "discarded": self.skipped,
            "discarded_reasons": dict(sorted(self.discarded_reasons.items())),
            "tokens": self.tokens,
            "supervised_tokens": self.supervised_tokens,
            "max_length": self.max_length,
            "original_max_length": self.original_max_length,
            "truncated": self.truncated,
            "truncation_policy": self.truncation_policy,
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
        truncation_policy: Literal["truncate", "drop"] = "truncate",
        min_supervised_tokens: int = 1,
    ) -> None:
        if max_seq_length < 64:
            raise ValueError("max_seq_length must be >= 64")
        if truncation_policy not in {"truncate", "drop"}:
            raise ValueError("truncation_policy must be 'truncate' or 'drop'")
        if min_supervised_tokens < 1:
            raise ValueError("min_supervised_tokens must be >= 1")
        self.tokenizer = tokenizer
        self.max_seq_length = max_seq_length
        self.truncation_policy = truncation_policy
        self.min_supervised_tokens = min_supervised_tokens
        self.records = records[:max_samples] if max_samples else records
        self.examples: list[dict[str, list[int]]] = []
        self.license_validation: dict[str, Any] | None = None
        discarded: dict[str, int] = {}
        skipped = 0
        truncated = 0
        original_max_length = 0
        for record in self.records:
            result = self._encode_detailed(record, format, system_prompt, template_kwargs)
            original_max_length = max(original_max_length, result.original_length)
            if result.encoded is None:
                skipped += 1
                reason = result.discarded_reason or "unknown"
                discarded[reason] = discarded.get(reason, 0) + 1
                continue
            if result.truncated:
                truncated += 1
            self.examples.append(result.encoded)
        self.stats = DatasetStats(
            examples=len(self.examples),
            skipped=skipped,
            tokens=sum(len(item["input_ids"]) for item in self.examples),
            supervised_tokens=sum(
                1 for item in self.examples for label in item["labels"] if label != -100
            ),
            max_length=max((len(item["input_ids"]) for item in self.examples), default=0),
            truncated=truncated,
            discarded_reasons=discarded,
            original_max_length=original_max_length,
            truncation_policy=truncation_policy,
        )
        if not self.examples:
            reasons = (
                ", ".join(f"{reason}={count}" for reason, count in sorted(discarded.items()))
                or "unknown"
            )
            raise ValueError(
                "no usable training examples after tokenization; check the data schema and "
                f"sequence length (discarded: {reasons})"
            )

    def _encode_detailed(
        self,
        record: Record,
        format: Literal["auto", "chat", "completion", "fim"],
        system_prompt: str | None,
        template_kwargs: dict[str, Any] | None,
    ) -> EncodingResult:
        kind = record.kind if format == "auto" else format
        if kind == "chat":
            if not record.messages:
                return EncodingResult(discarded_reason="missing_messages")
            return _encode_chat_detailed(
                self.tokenizer,
                record.messages,
                max_seq_length=self.max_seq_length,
                system_prompt=system_prompt,
                template_kwargs=template_kwargs,
                truncation_policy=self.truncation_policy,
                min_supervised_tokens=self.min_supervised_tokens,
            )
        if kind == "fim":
            if record.prefix is None or record.suffix is None or record.middle is None:
                return EncodingResult(discarded_reason="missing_fim_fields")
            return _encode_fim_detailed(
                self.tokenizer,
                record.prefix,
                record.suffix,
                record.middle,
                max_seq_length=self.max_seq_length,
                truncation_policy=self.truncation_policy,
                min_supervised_tokens=self.min_supervised_tokens,
            )
        if record.prompt is None or record.response is None:
            return EncodingResult(discarded_reason="missing_prompt_or_response")
        return _encode_completion_detailed(
            self.tokenizer,
            record.prompt,
            record.response,
            max_seq_length=self.max_seq_length,
            truncation_policy=self.truncation_policy,
            min_supervised_tokens=self.min_supervised_tokens,
        )

    def _encode(
        self,
        record: Record,
        format: Literal["auto", "chat", "completion", "fim"],
        system_prompt: str | None,
        template_kwargs: dict[str, Any] | None,
    ) -> dict[str, list[int]] | None:
        """Backward-compatible per-record encoder."""

        return self._encode_detailed(record, format, system_prompt, template_kwargs).encoded

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
    require_validation: bool = False,
    require_license: bool = True,
    allowed_licenses: list[str] | None = None,
    require_resolved_licenses: bool = True,
    allow_unresolved_licenses: list[str] | None = None,
    license_profile: LicenseProfile = "research",
    evaluation_ids: set[str] | None = None,
    truncation_policy: Literal["truncate", "drop"] = "truncate",
    min_supervised_tokens: int = 1,
) -> tuple[SFTDataset, SFTDataset | None]:
    """Load JSONL records, enforce licensing, and build train/validation datasets.

    Missing validation files are an error rather than a silent fallback: a
    research run must not quietly drop model selection or eval logging.
    """

    if allowed_licenses is None:
        from cyberlite.config import DataConfig

        allowed_licenses = list(DataConfig().allowed_licenses)
    if allow_unresolved_licenses is None:
        allow_unresolved_licenses = []

    train_path = Path(train_file)
    if not train_path.is_file():
        raise FileNotFoundError(
            f"training data not found: {train_path}. Build the registered dataset with "
            "`python scripts/prepare_dataset.py --config configs/dataset_pilot.yaml --force`, "
            "or use the explicit smoke path for pipeline validation."
        )
    train_records = load_records(train_path)
    if not train_records:
        raise ValueError(f"training file is empty: {train_path}")
    train_license = validate_training_licenses(
        train_records,
        split="train",
        allowed_licenses=allowed_licenses,
        require_license=require_license,
        require_resolved_licenses=require_resolved_licenses,
        allow_unresolved_licenses=allow_unresolved_licenses,
        profile=license_profile,
        evaluation_ids=evaluation_ids or (),
    )
    if not train_license.ok:
        raise LicenseValidationError(train_license)
    train_dataset = SFTDataset(
        train_records,
        tokenizer,
        max_seq_length=max_seq_length,
        format=format,
        system_prompt=system_prompt,
        template_kwargs=template_kwargs,
        max_samples=max_train_samples,
        truncation_policy=truncation_policy,
        min_supervised_tokens=min_supervised_tokens,
    )
    train_dataset.license_validation = train_license.to_dict()

    validation_dataset = None
    if validation_file is None:
        if require_validation:
            raise FileNotFoundError(
                "validation data is required for this run but data.validation_file is unset"
            )
        return train_dataset, None
    validation_path = Path(validation_file)
    if not validation_path.is_file():
        raise FileNotFoundError(
            f"validation data not found: {validation_path}. A configured validation split "
            "must exist; it is never silently skipped. Rebuild the dataset or correct "
            "data.validation_file."
        )
    val_records = load_records(validation_path)
    if not val_records:
        raise ValueError(f"validation file is empty: {validation_path}")
    val_license = validate_training_licenses(
        val_records,
        split="validation",
        allowed_licenses=allowed_licenses,
        require_license=require_license,
        require_resolved_licenses=require_resolved_licenses,
        allow_unresolved_licenses=allow_unresolved_licenses,
        profile=license_profile,
        evaluation_ids=evaluation_ids or (),
    )
    if not val_license.ok:
        raise LicenseValidationError(val_license)
    validation_dataset = SFTDataset(
        val_records,
        tokenizer,
        max_seq_length=max_seq_length,
        format=format,
        system_prompt=system_prompt,
        template_kwargs=template_kwargs,
        max_samples=max_eval_samples,
        truncation_policy=truncation_policy,
        min_supervised_tokens=min_supervised_tokens,
    )
    validation_dataset.license_validation = val_license.to_dict()
    return train_dataset, validation_dataset

"""Shared test fixtures."""

from __future__ import annotations

import re
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import ClassVar

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def repo_root() -> Path:
    return ROOT


@pytest.fixture
def smoke_file(repo_root: Path) -> Path:
    return repo_root / "data" / "seed" / "smoke.jsonl"


@pytest.fixture
def eval_file(repo_root: Path) -> Path:
    return repo_root / "data" / "evaluation" / "smoke_eval.jsonl"


class FakeTokenizer:
    """Character-level tokenizer with chat and FIM control tokens.

    It implements only the surface used by CyberLite's dataset and autocomplete
    code, keeping unit tests network-free.
    """

    eos_token_id = 8192
    pad_token_id = 8192
    unk_token_id = 0
    chat_template = "fake"
    special: ClassVar[dict[str, int]] = {
        "<|im_start|>": 8000,
        "<|im_end|>": 8001,
        "<|endoftext|>": 8192,
        "<|fim_prefix|>": 8002,
        "<|fim_suffix|>": 8003,
        "<|fim_middle|>": 8004,
        "<|fim_pad|>": 8005,
    }
    pattern: ClassVar[re.Pattern[str]] = re.compile(r"<\|[a-z_]+\|>")

    def apply_chat_template(
        self,
        messages: list[dict[str, str]],
        tokenize: bool = False,
        add_generation_prompt: bool = False,
        **kwargs: object,
    ) -> str:
        output = ""
        for message in messages:
            output += f"<|im_start|>{message['role']}\n{message['content']}<|im_end|>\n"
        if add_generation_prompt:
            output += "<|im_start|>assistant\n"
        return output

    def __call__(
        self,
        text: str,
        add_special_tokens: bool = False,
        return_offsets_mapping: bool = False,
        **kwargs: object,
    ) -> dict[str, list]:
        ids: list[int] = []
        offsets: list[tuple[int, int]] = []
        cursor = 0
        for match in self.pattern.finditer(text):
            for position in range(cursor, match.start()):
                ids.append(100 + ord(text[position]) % 900)
                offsets.append((position, position + 1))
            ids.append(self.special[match.group(0)])
            offsets.append((match.start(), match.end()))
            cursor = match.end()
        for position in range(cursor, len(text)):
            ids.append(100 + ord(text[position]) % 900)
            offsets.append((position, position + 1))
        result: dict[str, list] = {"input_ids": ids}
        if return_offsets_mapping:
            result["offset_mapping"] = offsets
        return result

    def convert_tokens_to_ids(self, token: str) -> int:
        return self.special.get(token, self.unk_token_id)

    def decode(self, ids: list[int], skip_special_tokens: bool = False) -> str:
        reverse = {value: key for key, value in self.special.items()}
        parts = []
        for token_id in ids:
            if token_id in reverse:
                if not skip_special_tokens:
                    parts.append(reverse[token_id])
            else:
                parts.append(chr((token_id - 100) % 900))
        return "".join(parts)


@pytest.fixture
def fake_tokenizer() -> FakeTokenizer:
    return FakeTokenizer()


@pytest.fixture
def sample_records() -> list[dict]:
    return [
        {
            "source": "cyberlite_smoke",
            "license": "Synthetic",
            "task": "knowledge",
            "messages": [
                {"role": "user", "content": "How do I harden SSH access?"},
                {
                    "role": "assistant",
                    "content": "Disable password authentication, restrict users, and centralize logs.",
                },
            ],
        },
        {
            "source": "cyberlite_smoke",
            "license": "Synthetic",
            "task": "autocomplete",
            "prefix": "grep -R ",
            "suffix": " /var/log",
            "middle": '"failed password"',
        },
    ]


def write_jsonl(path: Path, records: list[dict]) -> Path:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")
    return path


@pytest.fixture
def jsonl_writer() -> Iterator:
    yield write_jsonl

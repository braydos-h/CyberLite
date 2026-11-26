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

    It implements only the surface used by CyberLite's dataset and completion
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
            "task": "completion",
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


@pytest.fixture
def dataset_builder(tmp_path: Path):
    """Build a tiny dataset plus a frozen-manifest fixture."""

    def build(
        *,
        name: str = "tiny-dataset",
        splits: dict[str, list[dict]] | None = None,
        version: str = "cyberlite-data-test-000000000000",
        license_id: str = "Public-Domain",
        provenance: bool = True,
        manual_review_completed: bool = False,
        manifest_dir: str | None = None,
        allowed_licenses: list[str] | None = None,
        dataset_schema: int = 2,
        mutate_manifest: dict | None = None,
    ) -> dict:
        import hashlib
        import json

        root = tmp_path / name
        root.mkdir(parents=True, exist_ok=True)
        if splits is None:
            splits = {
                "train": [
                    {
                        "id": f"{name}-train-1",
                        "source": "unit",
                        "license": license_id,
                        "task": "knowledge",
                        "prompt": "How should an administrator verify a firewall rule?",
                        "response": "Verify the rule in staging and record the evidence.",
                        "split": "train",
                    }
                ],
                "validation": [
                    {
                        "id": f"{name}-validation-1",
                        "source": "unit",
                        "license": license_id,
                        "task": "knowledge",
                        "prompt": "What should a defender check first?",
                        "response": "Preserve evidence and follow the incident process.",
                        "split": "validation",
                    }
                ],
                "test": [
                    {
                        "id": f"{name}-test-1",
                        "source": "unit",
                        "license": license_id,
                        "task": "knowledge",
                        "prompt": "Is a smoke test a benchmark?",
                        "response": "No; it validates the pipeline only.",
                        "split": "test",
                    }
                ],
            }
        paths: dict[str, Path] = {}
        files: dict[str, dict] = {}
        for split, rows in splits.items():
            path = root / f"{split}.jsonl"
            with path.open("w", encoding="utf-8") as handle:
                for index, row in enumerate(rows):
                    payload = dict(row)
                    payload.setdefault("id", f"{name}-{split}-{index}")
                    payload.setdefault("source", "unit")
                    payload.setdefault("license", license_id)
                    payload.setdefault("task", "knowledge")
                    payload["split"] = split
                    if provenance:
                        payload.setdefault("url", "https://example.invalid/source")
                        metadata = dict(payload.get("metadata") or {})
                        metadata.setdefault("source_version", "v1")
                        metadata.setdefault("upstream_id", f"upstream-{index}")
                        payload["metadata"] = metadata
                    handle.write(json.dumps(payload, sort_keys=True) + "\n")
            paths[split] = path
            files[split] = {
                "path": str(path),
                "records": len(rows),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "bytes": path.stat().st_size,
            }
        manifest = {
            "dataset_schema": dataset_schema,
            "dataset_name": name,
            "dataset_version": version,
            "pipeline_version": "2.0.0",
            "split_counts": {split: len(rows) for split, rows in splits.items()},
            "output_records": sum(len(rows) for rows in splits.values()),
            "files": files,
            "options": {
                "allowed_licenses": allowed_licenses or [license_id],
                "seed": 42,
            },
            "manual_review": {
                "completed": manual_review_completed,
                "reviewed_records": 0,
                "note": "fixture",
            },
            "audit": {
                "token_truncation": {"over_limit": 0, "ratio": 0.0, "risk": "low"},
            },
            "quality": {"token_lengths": {"tokens": {"p50": 10, "p95": 20, "p99": 30}}},
        }
        if mutate_manifest:
            manifest.update(mutate_manifest)
        if manifest_dir:
            frozen_dir = root / manifest_dir
            frozen_dir.mkdir(parents=True, exist_ok=True)
            manifest_path = frozen_dir / "manifest.json"
        else:
            manifest_path = root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        if manifest_dir:
            # Also write the processed manifest that a real build leaves beside
            # the splits.
            (root / "manifest.json").write_text(
                json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
            )
        return {
            "root": root,
            "manifest": manifest_path,
            "paths": paths,
            "version": version,
            "manifest_data": manifest,
        }

    return build

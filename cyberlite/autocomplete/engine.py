"""Cybersecurity-aware, non-executing autocomplete engine.

Completion modes:

* ``fim``: uses the tokenizer's fill-in-the-middle control tokens. Supported by
  Qwen3.5's tokenizer, but quality depends on whether the checkpoint was trained
  for FIM. This repository documents that dependency instead of assuming it.
* ``prefix``: instruction/prefix continuation, used when FIM tokens are absent
  or when the user selects it.

Generated text is returned as data. Nothing is executed, evaluated, or written
to disk by this module.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from cyberlite.autocomplete.formats import (
    FIM_PAD,
    build_fim_prompt,
    build_prefix_chat_messages,
    detect_language,
    sanitize_completion,
)
from cyberlite.inference.engine import GenerationSettings, InferenceEngine


@dataclass
class AutocompleteResult:
    completion: str
    language: str
    mode: str
    latency_seconds: float
    prompt_tokens: int
    completion_tokens: int
    tokens_per_second: float
    fim_supported: bool
    executed: bool = False
    requires_review: bool = True
    peak_memory: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "completion": self.completion,
            "language": self.language,
            "mode": self.mode,
            "latency_seconds": round(self.latency_seconds, 4),
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "tokens_per_second": round(self.tokens_per_second, 2),
            "fim_supported": self.fim_supported,
            "executed": self.executed,
            "requires_review": self.requires_review,
            "peak_memory": self.peak_memory,
            "metadata": self.metadata,
        }


class AutocompleteEngine:
    def __init__(
        self,
        engine: InferenceEngine,
        *,
        default_mode: Literal["auto", "fim", "prefix"] = "auto",
        max_new_tokens: int = 128,
    ) -> None:
        self.engine = engine
        self.default_mode = default_mode
        self.max_new_tokens = max_new_tokens
        self.fim_supported = self._check_fim_support()

    def _check_fim_support(self) -> bool:
        tokenizer = self.engine.tokenizer
        token_id = tokenizer.convert_tokens_to_ids(FIM_PAD)
        return token_id is not None and token_id != getattr(tokenizer, "unk_token_id", None)

    def complete(
        self,
        prefix: str,
        *,
        suffix: str = "",
        language: str = "auto",
        filename: str | None = None,
        max_new_tokens: int | None = None,
        temperature: float = 0.1,
        mode: Literal["auto", "fim", "prefix"] | None = None,
    ) -> AutocompleteResult:
        if not prefix.strip() and not suffix.strip():
            raise ValueError("prefix and suffix cannot both be empty")
        profile = detect_language(filename=filename, explicit=language)
        selected = mode or self.default_mode
        if selected == "auto":
            selected = "fim" if self.fim_supported else "prefix"
        if selected == "fim" and not self.fim_supported:
            raise ValueError(
                "FIM mode requested but the tokenizer lacks <|fim_*|> tokens; use mode=prefix"
            )
        max_tokens = max_new_tokens or self.max_new_tokens
        if selected == "fim":
            prompt = build_fim_prompt(prefix, suffix)
            settings = GenerationSettings(
                max_new_tokens=max_tokens,
                temperature=temperature,
                stop=[FIM_PAD, "<|endoftext|>", "<|im_end|>"],
            )
        else:
            messages = build_prefix_chat_messages(prefix, suffix, profile)
            prompt = self.engine.format_chat(messages)
            settings = GenerationSettings(
                max_new_tokens=max_tokens,
                temperature=temperature,
                stop=["<|im_end|>", "<|endoftext|>"],
            )
        start = time.perf_counter()
        result = self.engine.complete(prompt, settings)
        completion = sanitize_completion(result.text, prefix=prefix)
        latency = time.perf_counter() - start
        return AutocompleteResult(
            completion=completion,
            language=profile.name,
            mode=selected,
            latency_seconds=latency,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            tokens_per_second=result.tokens_per_second,
            fim_supported=self.fim_supported,
            peak_memory=result.peak_memory,
            metadata={
                "model_id": result.model_id,
                "stop_strings": settings.stop,
                "completion_sha256": hashlib.sha256(completion.encode()).hexdigest()[:16],
            },
        )


class FeedbackStore:
    """Opt-in acceptance feedback storage (hashes only, not completion text)."""

    def __init__(self, path: str | None) -> None:
        self.path = path

    def record(
        self,
        *,
        accepted: bool,
        language: str,
        mode: str,
        latency_seconds: float,
        completion: str,
        model_id: str,
    ) -> None:
        if not self.path:
            raise RuntimeError(
                "feedback storage is disabled; start the server with --feedback-file"
            )
        import json
        from datetime import UTC, datetime
        from pathlib import Path

        payload = {
            "ts": datetime.now(tz=UTC).isoformat(),
            "accepted": bool(accepted),
            "language": language,
            "mode": mode,
            "latency_seconds": round(latency_seconds, 4),
            "completion_sha256": hashlib.sha256(completion.encode()).hexdigest(),
            "completion_chars": len(completion),
            "model_id": model_id,
        }
        path = Path(self.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")

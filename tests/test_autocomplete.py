from __future__ import annotations

import pytest
from cyberlite.autocomplete.engine import AutocompleteEngine, FeedbackStore
from cyberlite.autocomplete.formats import (
    build_fim_prompt,
    detect_language,
    get_language,
    sanitize_completion,
)
from cyberlite.inference.engine import CompletionResult


class _FakeEngine:
    model_id = "fake"

    def __init__(self, tokenizer, text: str = "completion") -> None:
        self.tokenizer = tokenizer
        self.text = text
        self.last_prompt = ""

    def format_chat(self, messages):
        return self.tokenizer.apply_chat_template(messages, add_generation_prompt=True)

    def complete(self, prompt, settings=None):
        self.last_prompt = prompt
        return CompletionResult(
            text=self.text,
            prompt_tokens=10,
            completion_tokens=3,
            latency_seconds=0.05,
            tokens_per_second=60.0,
            model_id="fake",
        )


def test_detect_language_by_extension_and_explicit() -> None:
    assert detect_language(filename="rule.yar").name == "yara"
    assert detect_language(filename="script.ps1").name == "powershell"
    assert detect_language(explicit="shell").name == "bash"
    assert get_language("unknown-value").name == "generic"


def test_fim_prompt_shape() -> None:
    prompt = build_fim_prompt("before", "after")
    assert prompt.startswith("<|fim_prefix|>before")
    assert "<|fim_suffix|>after" in prompt
    assert prompt.endswith("<|fim_middle|>")


def test_sanitize_removes_fences_and_prefix() -> None:
    assert sanitize_completion("```python\nreturn 1\n```") == "return 1"
    assert sanitize_completion("prefix more") == "prefix more"
    assert sanitize_completion("prefix more", prefix="prefix") == "more"
    assert sanitize_completion("Completion: x") == "x"


def test_fim_mode_auto_and_explicit(fake_tokenizer) -> None:
    engine = _FakeEngine(fake_tokenizer, text="journalctl -u ssh")
    autocomplete = AutocompleteEngine(engine)
    assert autocomplete.fim_supported
    result = autocomplete.complete("journalctl ", language="bash")
    assert result.mode == "fim"
    assert "<|fim_prefix|>" in engine.last_prompt
    assert result.executed is False
    assert result.requires_review is True
    assert result.completion == "-u ssh"


def test_prefix_mode_uses_chat_template(fake_tokenizer) -> None:
    engine = _FakeEngine(fake_tokenizer, text="--help")
    autocomplete = AutocompleteEngine(engine)
    result = autocomplete.complete("nmap", mode="prefix", language="bash")
    assert result.mode == "prefix"
    assert "<|im_start|>" in engine.last_prompt
    assert "completion" in engine.last_prompt.lower()


def test_empty_prefix_rejected(fake_tokenizer) -> None:
    autocomplete = AutocompleteEngine(_FakeEngine(fake_tokenizer))
    with pytest.raises(ValueError):
        autocomplete.complete("")


def test_fim_rejected_without_tokens(fake_tokenizer) -> None:
    class NoFimTokenizer:
        unk_token_id = 0
        eos_token_id = 1

        def convert_tokens_to_ids(self, token):
            return 0

        def apply_chat_template(self, messages, **kwargs):
            return "\n".join(message["content"] for message in messages)

    engine = _FakeEngine(NoFimTokenizer())
    autocomplete = AutocompleteEngine(engine)
    assert not autocomplete.fim_supported
    with pytest.raises(ValueError, match="FIM mode requested"):
        autocomplete.complete("x", mode="fim")
    auto = autocomplete.complete("x", mode="auto")
    assert auto.mode == "prefix"


def test_feedback_store_does_not_store_completion_text(tmp_path) -> None:
    path = tmp_path / "feedback.jsonl"
    store = FeedbackStore(str(path))
    store.record(
        accepted=True,
        language="python",
        mode="fim",
        latency_seconds=0.2,
        completion="secret completion text",
        model_id="fake",
    )
    content = path.read_text()
    assert "secret completion text" not in content
    assert "completion_sha256" in content

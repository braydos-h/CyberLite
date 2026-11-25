from __future__ import annotations

import json
from pathlib import Path

import pytest
from cyberlite.autocomplete.engine import AutocompleteResult, FeedbackStore
from cyberlite.inference.engine import CompletionResult
from cyberlite.inference.server import create_app
from fastapi.testclient import TestClient


class FakeEngine:
    model_id = "fake-cyberlite"
    tokenizer = None

    def info(self):
        return {"model_id": self.model_id, "device": "cpu", "parameters": 800_000_000}

    def complete(self, prompt, settings=None):
        return CompletionResult(
            text="defensive answer",
            prompt_tokens=5,
            completion_tokens=3,
            latency_seconds=0.02,
            tokens_per_second=150.0,
            model_id=self.model_id,
        )

    def chat(self, messages, settings=None):
        return self.complete("", settings)

    def stream(self, prompt, settings=None):
        yield "defensive "
        yield "answer"

    def stream_chat(self, messages, settings=None):
        yield "defensive "
        yield "answer"


class FakeAutocomplete:
    fim_supported = True

    def complete(self, prefix, **kwargs):
        return AutocompleteResult(
            completion=" --help",
            language=kwargs.get("language", "generic"),
            mode="fim",
            latency_seconds=0.01,
            prompt_tokens=8,
            completion_tokens=2,
            tokens_per_second=200.0,
            fim_supported=True,
        )


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    app = create_app(
        engine=FakeEngine(),
        autocomplete=FakeAutocomplete(),
        feedback=FeedbackStore(str(tmp_path / "feedback.jsonl")),
    )
    return TestClient(app)


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["execution_enabled"] is False
    assert payload["research_status"] == "experimental"


def test_models(client: TestClient) -> None:
    response = client.get("/v1/models")
    assert response.status_code == 200
    assert response.json()["data"][0]["id"] == "fake-cyberlite"


def test_chat_completion(client: TestClient) -> None:
    response = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hello"}]},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["choices"][0]["message"]["content"] == "defensive answer"
    assert payload["usage"]["total_tokens"] == 8
    assert payload["cyberlite"]["executed"] is False


def test_completion(client: TestClient) -> None:
    response = client.post("/v1/completions", json={"prompt": "hello"})
    assert response.status_code == 200
    assert response.json()["choices"][0]["text"] == "defensive answer"


def test_chat_stream(client: TestClient) -> None:
    response = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hello"}], "stream": True},
    )
    assert response.status_code == 200
    assert "[DONE]" in response.text
    assert "defensive" in response.text


def test_autocomplete_endpoint(client: TestClient) -> None:
    response = client.post(
        "/v1/autocomplete",
        json={"prefix": "nmap", "language": "bash", "suffix": ""},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["completion"] == " --help"
    assert payload["executed"] is False
    assert "review" in payload["warning"].lower()


def test_feedback_records_hash_not_text(client: TestClient, tmp_path: Path) -> None:
    response = client.post(
        "/v1/autocomplete/feedback",
        json={
            "accepted": True,
            "language": "bash",
            "completion": "sensitive generated command",
            "latency_seconds": 0.01,
        },
    )
    assert response.status_code == 200
    assert response.json()["recorded"] is True
    content = (tmp_path / "feedback.jsonl").read_text()
    assert "sensitive generated command" not in content
    assert json.loads(content)["accepted"] is True


def test_api_key_required(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CYBERLITE_API_KEY", "test-key")
    app = create_app(engine=FakeEngine(), autocomplete=FakeAutocomplete())
    client = TestClient(app)
    assert client.get("/v1/models").status_code == 401
    assert client.get("/v1/models", headers={"Authorization": "Bearer test-key"}).status_code == 200


def test_feedback_disabled_returns_501() -> None:
    app = create_app(engine=FakeEngine(), autocomplete=FakeAutocomplete())
    client = TestClient(app)
    response = client.post("/v1/autocomplete/feedback", json={"accepted": True})
    assert response.status_code == 501


def test_empty_chat_rejected(client: TestClient) -> None:
    response = client.post("/v1/chat/completions", json={"messages": []})
    assert response.status_code == 400

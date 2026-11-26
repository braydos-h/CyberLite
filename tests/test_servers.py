from __future__ import annotations

import pytest
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


@pytest.fixture
def client() -> TestClient:
    app = create_app(engine=FakeEngine())
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


def test_api_key_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CYBERLITE_API_KEY", "test-key")
    app = create_app(engine=FakeEngine())
    client = TestClient(app)
    assert client.get("/v1/models").status_code == 401
    assert client.get("/v1/models", headers={"Authorization": "Bearer test-key"}).status_code == 200


def test_empty_chat_rejected(client: TestClient) -> None:
    response = client.post("/v1/chat/completions", json={"messages": []})
    assert response.status_code == 400

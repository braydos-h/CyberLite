"""OpenAI-compatible local inference server.

Endpoints are local-first and provider-free. The server performs no tool
execution and no network calls after the model has been downloaded.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from cyberlite import __version__
from cyberlite.autocomplete.engine import AutocompleteEngine, FeedbackStore
from cyberlite.inference.engine import GenerationSettings, InferenceEngine
from cyberlite.logging_utils import configure_logging, get_logger

logger = get_logger(__name__)

STARTED_AT = time.time()


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: str | None = None
    messages: list[ChatMessage]
    max_tokens: int = Field(default=512, ge=1, le=4096)
    temperature: float = Field(default=0.2, ge=0, le=2)
    top_p: float = Field(default=0.95, gt=0, le=1)
    stream: bool = False
    stop: str | list[str] | None = None
    seed: int | None = 42


class CompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: str | None = None
    prompt: str | list[str]
    max_tokens: int = Field(default=256, ge=1, le=4096)
    temperature: float = Field(default=0.2, ge=0, le=2)
    top_p: float = Field(default=0.95, gt=0, le=1)
    stream: bool = False
    stop: str | list[str] | None = None
    seed: int | None = 42


class AutocompleteRequest(BaseModel):
    prefix: str = Field(min_length=1, max_length=100_000)
    suffix: str = Field(default="", max_length=100_000)
    language: str = "auto"
    filename: str | None = None
    mode: Literal["auto", "fim", "prefix"] = "auto"
    max_tokens: int = Field(default=128, ge=1, le=512)
    temperature: float = Field(default=0.1, ge=0, le=1)


class FeedbackRequest(BaseModel):
    accepted: bool
    language: str = "generic"
    mode: str = "fim"
    latency_seconds: float = Field(default=0.0, ge=0)
    completion: str = Field(default="", max_length=100_000)
    model_id: str = ""


def _stops(value: str | list[str] | None, defaults: list[str]) -> list[str]:
    if value is None:
        return defaults
    if isinstance(value, str):
        return [value]
    return value[:16]


def _auth(authorization: str | None = Header(default=None)) -> None:
    expected = os.environ.get("CYBERLITE_API_KEY")
    if expected and authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="invalid or missing API key")


def _authorize(authorization: str | None = Header(default=None)) -> None:
    _auth(authorization)


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def create_app(
    *,
    engine: Any,
    autocomplete: AutocompleteEngine | None = None,
    feedback: FeedbackStore | None = None,
) -> FastAPI:
    app = FastAPI(
        title="CyberLite local inference API",
        version=__version__,
        description=(
            "Local, OpenAI-compatible endpoints for a CyberLite model. Generated text is "
            "returned as data and is never executed by this server."
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost", "http://127.0.0.1"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.state.engine = engine
    app.state.autocomplete = autocomplete
    app.state.feedback = feedback or FeedbackStore(None)

    @app.get("/health")
    def health() -> dict[str, Any]:
        info = (
            engine.info()
            if hasattr(engine, "info")
            else {"model_id": getattr(engine, "model_id", "unknown")}
        )
        return {
            "status": "ok",
            "cyberlite_version": __version__,
            "research_status": "experimental",
            "uptime_seconds": round(time.time() - STARTED_AT, 2),
            "model": info,
            "execution_enabled": False,
        }

    @app.get("/v1/models", dependencies=[Depends(_authorize)])
    def models() -> dict[str, Any]:
        model_id = getattr(engine, "model_id", "cyberlite-local")
        return {
            "object": "list",
            "data": [
                {
                    "id": model_id,
                    "object": "model",
                    "created": int(STARTED_AT),
                    "owned_by": "cyberlite",
                }
            ],
        }

    @app.post("/v1/chat/completions", dependencies=[Depends(_authorize)])
    def chat_completions(request: ChatRequest) -> Any:
        if not request.messages:
            raise HTTPException(status_code=400, detail="messages cannot be empty")
        settings = GenerationSettings(
            max_new_tokens=request.max_tokens,
            temperature=request.temperature,
            top_p=request.top_p,
            stop=_stops(request.stop, ["<|im_end|>", "<|endoftext|>"]),
            seed=request.seed,
        )
        messages = [message.model_dump() for message in request.messages]
        if request.stream:
            return StreamingResponse(
                _stream_chat(engine, messages, settings),
                media_type="text/event-stream",
            )
        try:
            result = engine.chat(messages, settings)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": getattr(engine, "model_id", "cyberlite-local"),
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": result.text},
                    "finish_reason": result.finish_reason,
                }
            ],
            "usage": {
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "total_tokens": result.prompt_tokens + result.completion_tokens,
            },
            "cyberlite": {
                "latency_seconds": round(result.latency_seconds, 4),
                "tokens_per_second": round(result.tokens_per_second, 2),
                "executed": False,
            },
        }

    @app.post("/v1/completions", dependencies=[Depends(_authorize)])
    def completions(request: CompletionRequest) -> Any:
        prompt = request.prompt[0] if isinstance(request.prompt, list) else request.prompt
        if not prompt:
            raise HTTPException(status_code=400, detail="prompt cannot be empty")
        settings = GenerationSettings(
            max_new_tokens=request.max_tokens,
            temperature=request.temperature,
            top_p=request.top_p,
            stop=_stops(request.stop, ["<|im_end|>", "<|endoftext|>"]),
            seed=request.seed,
        )
        if request.stream:
            return StreamingResponse(
                _stream_completion(engine, prompt, settings),
                media_type="text/event-stream",
            )
        try:
            result = engine.complete(prompt, settings)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "id": f"cmpl-{uuid.uuid4().hex[:24]}",
            "object": "text_completion",
            "created": int(time.time()),
            "model": getattr(engine, "model_id", "cyberlite-local"),
            "choices": [
                {
                    "text": result.text,
                    "index": 0,
                    "logprobs": None,
                    "finish_reason": result.finish_reason,
                }
            ],
            "usage": {
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "total_tokens": result.prompt_tokens + result.completion_tokens,
            },
            "cyberlite": {"executed": False},
        }

    @app.post("/v1/autocomplete", dependencies=[Depends(_authorize)])
    def autocomplete_endpoint(request: AutocompleteRequest) -> dict[str, Any]:
        if app.state.autocomplete is None:
            raise HTTPException(status_code=503, detail="autocomplete engine is not configured")
        try:
            result = app.state.autocomplete.complete(
                request.prefix,
                suffix=request.suffix,
                language=request.language,
                filename=request.filename,
                max_new_tokens=request.max_tokens,
                temperature=request.temperature,
                mode=request.mode,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        payload = result.to_dict()
        payload["warning"] = "Generated content is untrusted; review before use."
        return payload

    @app.post("/v1/autocomplete/feedback", dependencies=[Depends(_authorize)])
    def autocomplete_feedback(request: FeedbackRequest) -> dict[str, Any]:
        store: FeedbackStore = app.state.feedback
        if not store.path:
            raise HTTPException(
                status_code=501,
                detail="feedback storage disabled; start with --feedback-file PATH",
            )
        try:
            store.record(
                accepted=request.accepted,
                language=request.language,
                mode=request.mode,
                latency_seconds=request.latency_seconds,
                completion=request.completion,
                model_id=request.model_id or getattr(engine, "model_id", ""),
            )
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"could not write feedback: {exc}") from exc
        return {"recorded": True, "completion_text_stored": False}

    return app


def _stream_chat(engine: Any, messages: list[dict[str, str]], settings: GenerationSettings):
    request_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())
    model = getattr(engine, "model_id", "cyberlite-local")
    try:
        for chunk in engine.stream_chat(messages, settings):
            payload = {
                "id": request_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "delta": {"content": chunk}, "finish_reason": None}],
            }
            yield _sse(payload)
    except Exception as exc:  # pragma: no cover - depends on runtime model
        logger.exception("streaming chat failed", extra={"error": str(exc)})
        yield _sse({"error": {"message": "generation failed", "type": "server_error"}})
        return
    yield _sse(
        {
            "id": request_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop",
                }
            ],
        }
    )
    yield "data: [DONE]\n\n"


def _stream_completion(engine: Any, prompt: str, settings: GenerationSettings):
    request_id = f"cmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())
    model = getattr(engine, "model_id", "cyberlite-local")
    try:
        for chunk in engine.stream(prompt, settings):
            yield _sse(
                {
                    "id": request_id,
                    "object": "text_completion",
                    "created": created,
                    "model": model,
                    "choices": [{"text": chunk, "index": 0, "finish_reason": None}],
                }
            )
    except Exception as exc:  # pragma: no cover - depends on runtime model
        logger.exception("streaming completion failed", extra={"error": str(exc)})
        yield _sse({"error": {"message": "generation failed", "type": "server_error"}})
        return
    yield _sse(
        {
            "id": request_id,
            "object": "text_completion",
            "created": created,
            "model": model,
            "choices": [{"text": "", "index": 0, "finish_reason": "stop"}],
        }
    )
    yield "data: [DONE]\n\n"


def build_parser():
    import argparse

    parser = argparse.ArgumentParser(description="Run a local OpenAI-compatible CyberLite API.")
    parser.add_argument("--model", default="Qwen/Qwen3.5-0.8B")
    parser.add_argument("--adapter", default=None, help="optional PEFT adapter directory")
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda", "mps"])
    parser.add_argument(
        "--dtype", default="auto", choices=["auto", "float32", "float16", "bfloat16"]
    )
    parser.add_argument("--load-in-4bit", action="store_true")
    parser.add_argument("--load-in-8bit", action="store_true")
    parser.add_argument("--max-context", type=int, default=None)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--feedback-file", default=None)
    parser.add_argument("--no-autocomplete", action="store_true")
    parser.add_argument("--json-logs", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(json_logs=args.json_logs)
    import uvicorn

    engine = InferenceEngine(
        args.model,
        adapter_path=args.adapter,
        device=args.device,
        dtype=args.dtype,
        load_in_4bit=args.load_in_4bit,
        load_in_8bit=args.load_in_8bit,
        max_context=args.max_context,
    )
    autocomplete = None if args.no_autocomplete else AutocompleteEngine(engine)
    app = create_app(
        engine=engine,
        autocomplete=autocomplete,
        feedback=FeedbackStore(args.feedback_file),
    )
    logger.info("starting local API", extra={"host": args.host, "port": args.port})
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

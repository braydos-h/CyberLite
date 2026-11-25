"""Local HTTP API for editor autocomplete integrations."""

from __future__ import annotations

import hashlib
import time
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from cyberlite import __version__
from cyberlite.autocomplete.engine import AutocompleteEngine, FeedbackStore
from cyberlite.autocomplete.formats import LANGUAGES
from cyberlite.inference.engine import InferenceEngine
from cyberlite.logging_utils import configure_logging, get_logger

logger = get_logger(__name__)


class CompleteRequest(BaseModel):
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


def create_app(
    *,
    engine: InferenceEngine,
    autocomplete: AutocompleteEngine | None = None,
    feedback: FeedbackStore | None = None,
) -> FastAPI:
    app = FastAPI(
        title="CyberLite autocomplete API",
        version=__version__,
        description="Local cybersecurity autocomplete. Generated content is never executed.",
    )
    app.state.engine = engine
    app.state.autocomplete = autocomplete or AutocompleteEngine(engine)
    app.state.feedback = feedback or FeedbackStore(None)
    started_at = time.time()

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "cyberlite_version": __version__,
            "uptime_seconds": round(time.time() - started_at, 2),
            "model_id": getattr(engine, "model_id", "unknown"),
            "fim_supported": app.state.autocomplete.fim_supported,
            "languages": sorted(LANGUAGES),
            "execution_enabled": False,
        }

    @app.post("/v1/autocomplete")
    def complete(request: CompleteRequest) -> dict[str, Any]:
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

    @app.post("/v1/autocomplete/feedback")
    def feedback_endpoint(request: FeedbackRequest) -> dict[str, Any]:
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
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {
            "recorded": True,
            "completion_text_stored": False,
            "completion_sha256": hashlib.sha256(request.completion.encode()).hexdigest(),
        }

    return app


def build_parser():
    import argparse

    parser = argparse.ArgumentParser(description="Run the CyberLite autocomplete API.")
    parser.add_argument("--model", default="Qwen/Qwen3.5-0.8B")
    parser.add_argument("--adapter", default=None)
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda", "mps"])
    parser.add_argument(
        "--dtype", default="auto", choices=["auto", "float32", "float16", "bfloat16"]
    )
    parser.add_argument("--load-in-4bit", action="store_true")
    parser.add_argument("--max-context", type=int, default=None)
    parser.add_argument("--mode", default="auto", choices=["auto", "fim", "prefix"])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--feedback-file", default=None)
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
        max_context=args.max_context,
    )
    autocomplete = AutocompleteEngine(engine, default_mode=args.mode)
    app = create_app(
        engine=engine,
        autocomplete=autocomplete,
        feedback=FeedbackStore(args.feedback_file),
    )
    logger.info("starting autocomplete API", extra={"host": args.host, "port": args.port})
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

"""Local inference engine with streaming and memory accounting.

The engine is deliberately provider-free: it loads a local Hugging Face
checkpoint (optionally with a PEFT adapter) and runs on CPU, CUDA, or Apple MPS.
It never executes generated code or commands.
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import torch
from transformers import StoppingCriteria, StoppingCriteriaList

from cyberlite.hardware import peak_memory_report
from cyberlite.logging_utils import get_logger
from cyberlite.training.model import checkpoint_revision, looks_like_commit

logger = get_logger(__name__)


@dataclass
class GenerationSettings:
    max_new_tokens: int = 512
    temperature: float = 0.2
    top_p: float = 0.95
    top_k: int = 50
    repetition_penalty: float = 1.05
    stop: list[str] = field(default_factory=lambda: ["<|im_end|>", "<|endoftext|>"])
    seed: int | None = 42

    def validate(self) -> None:
        if not 1 <= self.max_new_tokens <= 4096:
            raise ValueError("max_new_tokens must be between 1 and 4096")
        if self.temperature < 0:
            raise ValueError("temperature must be >= 0")
        if not 0 < self.top_p <= 1:
            raise ValueError("top_p must be in (0, 1]")
        if self.top_k < 0:
            raise ValueError("top_k must be >= 0")
        if self.repetition_penalty <= 0:
            raise ValueError("repetition_penalty must be > 0")


@dataclass
class CompletionResult:
    text: str
    prompt_tokens: int
    completion_tokens: int
    latency_seconds: float
    tokens_per_second: float
    peak_memory: dict[str, Any] = field(default_factory=dict)
    model_id: str = ""
    finish_reason: str = "stop"

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "latency_seconds": round(self.latency_seconds, 4),
            "tokens_per_second": round(self.tokens_per_second, 2),
            "peak_memory": self.peak_memory,
            "model_id": self.model_id,
            "finish_reason": self.finish_reason,
        }


class _StopStringCriteria(StoppingCriteria):
    """Token-level stop-string criterion."""

    def __init__(self, tokenizer: Any, prompt_length: int, stops: list[str]) -> None:
        self.tokenizer = tokenizer
        self.prompt_length = prompt_length
        self.stops = [stop for stop in stops if stop]

    def __call__(self, input_ids: torch.Tensor, scores: torch.Tensor, **kwargs: Any) -> bool:
        if not self.stops:
            return False
        generated = input_ids[0][self.prompt_length :]
        text = self.tokenizer.decode(generated, skip_special_tokens=False)
        return any(stop in text for stop in self.stops)


class InferenceEngine:
    """A loaded model plus tokenizer and generation helpers."""

    def __init__(
        self,
        model_id: str,
        *,
        adapter_path: str | Path | None = None,
        device: str = "auto",
        dtype: str = "auto",
        load_in_4bit: bool = False,
        load_in_8bit: bool = False,
        max_context: int | None = None,
        trust_remote_code: bool = False,
        attn_implementation: str = "sdpa",
        revision: str | None = None,
        system_prompt: str | None = None,
        chat_template_kwargs: dict[str, Any] | None = None,
    ) -> None:
        if load_in_4bit and load_in_8bit:
            raise ValueError("choose at most one of load_in_4bit/load_in_8bit")
        self.model_id = model_id
        self.adapter_path = str(adapter_path) if adapter_path else None
        self.trust_remote_code = trust_remote_code
        self.revision = revision
        self.system_prompt = system_prompt
        self.chat_template_kwargs = chat_template_kwargs or {"enable_thinking": False}
        self.device = self._resolve_device(device)
        self.dtype = self._resolve_dtype(dtype, self.device)
        self.quantized = load_in_4bit or load_in_8bit
        self.resolved_revision: str | None = None
        self.tokenizer_revision: str | None = None
        self.model, self.tokenizer, self.auto_class = self._load(
            load_in_4bit=load_in_4bit,
            load_in_8bit=load_in_8bit,
            attn_implementation=attn_implementation,
        )
        text_config = getattr(self.model.config, "text_config", self.model.config)
        self.max_context = int(
            max_context or getattr(text_config, "max_position_embeddings", 8192) or 8192
        )
        self.loaded_at = time.time()
        self._lock = threading.Lock()
        self.adapter_sha256 = self._adapter_hash()

    @staticmethod
    def _resolve_device(device: str) -> str:
        if device != "auto":
            if device == "cuda" and not torch.cuda.is_available():
                raise RuntimeError("CUDA requested but not available")
            if device == "mps" and not (
                getattr(torch.backends, "mps", None) and torch.backends.mps.is_available()
            ):
                raise RuntimeError("MPS requested but not available")
            return device
        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    @staticmethod
    def _resolve_dtype(dtype: str, device: str) -> torch.dtype:
        mapping = {
            "float32": torch.float32,
            "float16": torch.float16,
            "bfloat16": torch.bfloat16,
        }
        if dtype != "auto":
            return mapping[dtype]
        if device == "cuda":
            return torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        if device == "cpu":
            return torch.float32
        return torch.float16

    def _load(
        self,
        *,
        load_in_4bit: bool,
        load_in_8bit: bool,
        attn_implementation: str,
    ) -> tuple[Any, Any, str]:
        from transformers import (
            AutoConfig,
            AutoModelForCausalLM,
            AutoModelForImageTextToText,
            AutoTokenizer,
        )

        if self.quantized and self.device != "cuda":
            raise RuntimeError(
                "bitsandbytes quantization in this pipeline requires CUDA. "
                "For CPU-only deployment, export GGUF and use llama.cpp (see scripts/quantize.py)."
            )
        config = AutoConfig.from_pretrained(
            self.model_id,
            revision=self.revision,
            trust_remote_code=self.trust_remote_code,
        )
        architectures = getattr(config, "architectures", None) or []
        multimodal = hasattr(config, "vision_config") or any(
            "ConditionalGeneration" in str(architecture) for architecture in architectures
        )
        auto_class = AutoModelForImageTextToText if multimodal else AutoModelForCausalLM
        import transformers

        dtype_key = (
            "dtype" if int(transformers.__version__.split(".", 1)[0]) >= 5 else "torch_dtype"
        )
        kwargs: dict[str, Any] = {
            "revision": self.revision,
            "trust_remote_code": self.trust_remote_code,
            dtype_key: self.dtype,
            "low_cpu_mem_usage": True,
        }
        if attn_implementation != "auto":
            kwargs["attn_implementation"] = attn_implementation
        if self.quantized:
            from transformers import BitsAndBytesConfig

            kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=load_in_4bit,
                load_in_8bit=load_in_8bit,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
                bnb_4bit_compute_dtype=self.dtype,
            )
            kwargs["device_map"] = "auto"
        elif self.device == "cuda":
            kwargs["device_map"] = "auto"

        logger.info(
            "loading inference model",
            extra={
                "model_id": self.model_id,
                "adapter": self.adapter_path,
                "device": self.device,
                "dtype": str(self.dtype),
                "multimodal": multimodal,
            },
        )
        model: Any = auto_class.from_pretrained(self.model_id, **kwargs)
        if self.adapter_path:
            from peft import PeftModel

            model = PeftModel.from_pretrained(model, self.adapter_path, is_trainable=False)
        if not self.quantized and self.device in {"cpu", "mps"}:
            model = model.to(self.device)
        model.eval()
        tokenizer = AutoTokenizer.from_pretrained(
            self.model_id,
            revision=self.revision,
            trust_remote_code=self.trust_remote_code,
            use_fast=True,
        )
        if tokenizer.pad_token_id is None:
            tokenizer.pad_token = tokenizer.eos_token
        self.resolved_revision = checkpoint_revision(model.config) or checkpoint_revision(model)
        self.tokenizer_revision = checkpoint_revision(tokenizer)
        if looks_like_commit(self.revision):
            if self.resolved_revision and self.resolved_revision != self.revision:
                raise RuntimeError(
                    f"model checkpoint resolved to revision {self.resolved_revision}, but "
                    f"{self.revision} was requested; refuse a silently changed base model"
                )
            if self.tokenizer_revision and self.tokenizer_revision != self.revision:
                raise RuntimeError(
                    f"tokenizer resolved to revision {self.tokenizer_revision}, but "
                    f"{self.revision} was requested; model and tokenizer revisions must match"
                )
        return model, tokenizer, auto_class.__name__

    def format_chat(self, messages: list[dict[str, str]]) -> str:
        from cyberlite.training.dataset import render_chat

        return render_chat(
            self.tokenizer,
            messages,
            system_prompt=self.system_prompt,
            add_generation_prompt=True,
            template_kwargs=self.chat_template_kwargs,
        )

    def _prepare(self, prompt: str, settings: GenerationSettings) -> Any:
        encoded = self.tokenizer(prompt, return_tensors="pt", add_special_tokens=False)
        prompt_tokens = int(encoded["input_ids"].shape[1])
        if prompt_tokens >= self.max_context - 8:
            raise ValueError(
                f"prompt is {prompt_tokens} tokens, exceeding the configured context "
                f"window of {self.max_context}"
            )
        max_new = min(settings.max_new_tokens, self.max_context - prompt_tokens)
        encoded = {key: value.to(self.model.device) for key, value in encoded.items()}
        return encoded, prompt_tokens, max_new

    def complete(self, prompt: str, settings: GenerationSettings | None = None) -> CompletionResult:
        settings = settings or GenerationSettings()
        settings.validate()
        encoded, prompt_tokens, max_new = self._prepare(prompt, settings)
        if settings.seed is not None:
            torch.manual_seed(settings.seed)
        stops = [stop for stop in settings.stop if stop]
        criteria = StoppingCriteriaList(
            [_StopStringCriteria(self.tokenizer, prompt_tokens, stops)] if stops else []
        )
        sampling: dict[str, Any] = {}
        if settings.temperature > 0:
            sampling = {
                "do_sample": True,
                "temperature": settings.temperature,
                "top_p": settings.top_p,
                "top_k": settings.top_k,
            }
        start = time.perf_counter()
        with torch.inference_mode():
            output = self.model.generate(
                **encoded,
                max_new_tokens=max_new,
                repetition_penalty=settings.repetition_penalty,
                pad_token_id=self.tokenizer.pad_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
                stopping_criteria=criteria,
                **sampling,
            )
        latency = time.perf_counter() - start
        generated_ids = output[0][prompt_tokens:]
        text = self.tokenizer.decode(generated_ids, skip_special_tokens=True).strip()
        text = _truncate_at_stop(text, stops)
        completion_tokens = int(generated_ids.shape[0])
        tps = completion_tokens / latency if latency > 0 else 0.0
        return CompletionResult(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_seconds=latency,
            tokens_per_second=tps,
            peak_memory=peak_memory_report(),
            model_id=self.model_id,
            finish_reason="stop" if completion_tokens < max_new else "length",
        )

    def stream(self, prompt: str, settings: GenerationSettings | None = None) -> Iterator[str]:
        """Yield decoded text chunks, holding back stop-string boundaries."""

        settings = settings or GenerationSettings()
        settings.validate()
        encoded, prompt_tokens, max_new = self._prepare(prompt, settings)
        from transformers import TextIteratorStreamer

        streamer = TextIteratorStreamer(
            self.tokenizer, skip_prompt=True, skip_special_tokens=True, timeout=120.0
        )
        stops = [stop for stop in settings.stop if stop]
        criteria = StoppingCriteriaList(
            [_StopStringCriteria(self.tokenizer, prompt_tokens, stops)] if stops else []
        )
        sampling: dict[str, Any] = {}
        if settings.temperature > 0:
            sampling = {
                "do_sample": True,
                "temperature": settings.temperature,
                "top_p": settings.top_p,
                "top_k": settings.top_k,
            }
        kwargs = {
            **encoded,
            "max_new_tokens": max_new,
            "repetition_penalty": settings.repetition_penalty,
            "pad_token_id": self.tokenizer.pad_token_id,
            "eos_token_id": self.tokenizer.eos_token_id,
            "stopping_criteria": criteria,
            "streamer": streamer,
            **sampling,
        }
        thread = threading.Thread(target=self.model.generate, kwargs=kwargs, daemon=True)
        thread.start()
        holdback = max((len(stop) for stop in stops), default=0) - 1
        emitted = ""
        buffer = ""
        try:
            for chunk in streamer:
                buffer += chunk
                if any(stop in buffer for stop in stops):
                    for stop in stops:
                        position = buffer.find(stop)
                        if position >= 0:
                            buffer = buffer[:position]
                    new_text = buffer[len(emitted) :]
                    if new_text:
                        yield new_text
                    return
                safe_length = max(0, len(buffer) - holdback)
                if safe_length > len(emitted):
                    new_text = buffer[len(emitted) : safe_length]
                    emitted = buffer[:safe_length]
                    if new_text:
                        yield new_text
            if len(buffer) > len(emitted):
                yield buffer[len(emitted) :]
        finally:
            thread.join(timeout=1.0)

    def chat(
        self,
        messages: list[dict[str, str]],
        settings: GenerationSettings | None = None,
    ) -> CompletionResult:
        prompt = self.format_chat(messages)
        return self.complete(prompt, settings)

    def stream_chat(
        self, messages: list[dict[str, str]], settings: GenerationSettings | None = None
    ) -> Iterator[str]:
        prompt = self.format_chat(messages)
        yield from self.stream(prompt, settings)

    def _adapter_hash(self) -> str | None:
        if not self.adapter_path:
            return None
        candidate = Path(self.adapter_path) / "adapter_model.safetensors"
        if not candidate.is_file():
            return None
        digest = hashlib.sha256()
        with candidate.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

    def info(self) -> dict[str, Any]:
        text_config = getattr(self.model.config, "text_config", self.model.config)
        return {
            "model_id": self.model_id,
            "revision": self.revision,
            "resolved_revision": self.resolved_revision,
            "tokenizer_revision": self.tokenizer_revision,
            "revision_verified": bool(
                looks_like_commit(self.revision)
                and self.resolved_revision == self.revision
                and (self.tokenizer_revision is None or self.tokenizer_revision == self.revision)
            ),
            "adapter_path": self.adapter_path,
            "adapter_sha256": self.adapter_sha256,
            "auto_class": self.auto_class,
            "device": self.device,
            "dtype": str(self.dtype),
            "quantized": self.quantized,
            "max_context": self.max_context,
            "parameters": sum(parameter.numel() for parameter in self.model.parameters()),
            "hidden_size": getattr(text_config, "hidden_size", None),
            "layers": getattr(text_config, "num_hidden_layers", None),
            "loaded": True,
        }


def _truncate_at_stop(text: str, stops: list[str]) -> str:
    positions = [text.find(stop) for stop in stops if stop in text]
    if positions:
        return text[: min(positions)].rstrip()
    return text

# Local inference

## Engine

`cyberlite.inference.engine.InferenceEngine` loads a local Hugging Face
checkpoint, optionally attaches a PEFT adapter, and exposes:

- `complete(prompt, settings)` — blocking completion with token and memory stats;
- `stream(prompt, settings)` — streaming text chunks;
- `chat(messages, settings)` and `stream_chat(...)` — chat-template rendering;
- `info()` — model class, device, dtype, context, parameters.

Device selection is `auto`, `cpu`, `cuda`, or `mps`. The default dtype is fp32 on
CPU, bf16 on capable CUDA GPUs, and fp16 otherwise. Set an explicit dtype for
reproducible benchmarks.

```python
from cyberlite.inference.engine import InferenceEngine, GenerationSettings

engine = InferenceEngine("Qwen/Qwen3.5-0.8B", device="cpu")
result = engine.chat(
    [{"role": "user", "content": "Explain SSH key rotation."}],
    GenerationSettings(max_new_tokens=256, temperature=0.0),
)
print(result.text)
```

The engine never executes generated content.

## OpenAI-compatible server

```bash
cyberlite-serve --model Qwen/Qwen3.5-0.8B --adapter runs/qlora --device cpu
```

| Endpoint | Method | Notes |
|---|---|---|
| `/health` | GET | model info, uptime, execution disabled |
| `/v1/models` | GET | OpenAI-style model list |
| `/v1/completions` | POST | streaming and non-streaming |
| `/v1/chat/completions` | POST | streaming and non-streaming |

Implemented request fields: `model`, `prompt`/`messages`, `max_tokens`,
`temperature`, `top_p`, `stream`, `stop`, `seed`. Extra fields are tolerated for
client compatibility but not acted on. The API is a compatibility subset, not a
full OpenAI replacement: logprobs, tools, function calling, and multi-choice
sampling are not implemented.

Set `CYBERLITE_API_KEY` to require `Authorization: Bearer ...`. CORS is limited
to localhost origins. Bind to `127.0.0.1` by default.

## Quantization

### bitsandbytes 4/8-bit (CUDA)

Used by QLoRA and GPU inference. This pipeline requires a CUDA device; attempts
on CPU fail with an explicit message.

```bash
python scripts/quantize.py \
  --model Qwen/Qwen3.5-0.8B \
  --backend bitsandbytes --bits 4 \
  --output models/cyberlite-4bit
```

The saved model includes a quantization configuration. Reload with
`--load-in-4bit` and verify output parity against the unquantized baseline.

### GGUF (CPU-friendly)

CyberLite does not download or build llama.cpp. Point the script at a local
checkout:

```bash
python scripts/quantize.py \
  --model Qwen/Qwen3.5-0.8B \
  --backend gguf \
  --llama-cpp-dir /path/to/llama.cpp \
  --quant-type Q4_K_M \
  --output models/gguf
```

The script calls `convert_hf_to_gguf.py` and `llama-quantize`. Review llama.cpp
support for the Qwen3.5 architecture before relying on this path; conversion may
lag architecture releases.

### Experimental backends

- `torchao` int8 weight-only: depends on a compatible Transformers/TorchAO
  release; reload and quality must be verified.
- `dynamic-int8`: `torch.ao.quantization.quantize_dynamic` over `nn.Linear`.
  Hybrid/linear-attention models may not reload cleanly; a state dict and an
  explicit warning are written instead of pretending it is a drop-in checkpoint.

No quantization method is assumed to preserve accuracy. Benchmark before use.

## Offline operation

After the initial model download, inference and serving make no network calls.
Set `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` to enforce this. If the model
or adapter is not cached, loading fails rather than downloading.

## Performance expectations

Latency and throughput are hardware-specific and are not guaranteed. Use:

```bash
python scripts/benchmark.py \
  --model Qwen/Qwen3.5-0.8B \
  --adapter runs/qlora \
  --device cpu \
  --prompt-lengths 128,512 \
  --max-new-tokens 64 \
  --runs 3
```

The benchmark writes time-to-first-token, total latency, tokens/second, and peak
memory. Report means and standard deviations with full hardware/software
metadata. See [hardware.md](hardware.md).

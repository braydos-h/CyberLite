# Hardware targets and measurement

## Targets, not promises

The 4, 6, 8, 12, and 16 GB VRAM classes are **experimental targets**. Whether a
configuration fits depends on the attention kernel, allocator, sequence length,
batch size, optimizer, framework version, and concurrent display/desktop use.
Always measure.

## Consumer profiles

| Class | Training starting point | Inference starting point | Notes |
|---|---|---|---|
| CPU | fp32 LoRA smoke only | GGUF 4-bit via llama.cpp, or fp32 reference | Slow; useful for correctness and offline demos |
| 4 GB | 4-bit QLoRA, seq 512, rank 8 | 4-bit/GGUF | Reduce sequence length before rank; expect allocator pressure |
| 6 GB | 4-bit QLoRA, seq 1024, rank 16 | 4-bit or GGUF q4/q5 | Practical minimum GPU training class |
| 8 GB | 4-bit QLoRA, seq 1024–2048 | 4-bit, 8-bit, or bf16 for short contexts | Room for eval batch size 1 |
| 12 GB | bf16 LoRA at seq 512–1024, or QLoRA | bf16/8-bit | Useful for controlled LoRA-vs-QLoRA comparisons |
| 16 GB | bf16 LoRA, seq 1024–2048 | bf16 | Can host some larger control models for evaluation |

A 0.853B-parameter model at 16-bit needs about 1.6 GiB for weights; at 4-bit,
about 0.4 GiB. Activations, optimizer state, CUDA context, fragmentation, and
framework overhead dominate the difference between "fits in theory" and "fits in
practice".

## Built-in estimates

```bash
python scripts/check_hardware.py
python scripts/check_hardware.py --json
python scripts/train.py --config configs/qlora.yaml --estimate-only --force
```

`cyberlite/hardware.py` uses a conservative activation proxy:

```text
activations_raw = 16 * batch * seq * hidden * layers
activations     = 0.25 * activations_raw        # with gradient checkpointing
```

It adds weight memory, a small adapter/optimizer allowance, and framework
overhead. These are planning estimates, not upper bounds. The smoke run on CPU
measured ~6.25 GiB peak RSS while the fp32 plan estimated ~4.4 GiB; treat the
estimate as a lower-bound sanity check and monitor real memory.

For inference, KV-cache size depends on the architecture. Qwen3.5's hybrid
layers keep recurrent state instead of a growing KV cache for linear-attention
blocks, but the exact cost is model- and kernel-specific. The default planner
uses a conservative per-token allowance and should be replaced by measured
values for capacity planning.

## Measurement protocol

Training writes `training_metrics.json` with:

- duration and global steps,
- approximate tokens processed and tokens/second,
- peak CUDA allocated/reserved VRAM,
- process peak RSS,
- hardware and model metadata,
- cost only if explicit rates were configured.

Inference benchmarking writes JSON with:

- time to first token (streaming),
- total latency,
- tokenizer tokens/second,
- per-prompt-token-length summaries,
- peak memory.

Suggested comparison protocol:

1. Fix model, adapter, dtype, quantization, prompt length, and max new tokens.
2. Run at least three repetitions after one warm-up.
3. Report mean and standard deviation, not a best-case run.
4. Record GPU model, driver, CUDA, PyTorch, Transformers, and power mode.
5. Keep the machine otherwise idle; disable battery saving and GPU power caps
   where possible (document if you cannot).
6. State whether prompts are synthetic and how token counts were measured.

## CPU notes

- The reference linear-attention and convolution kernels work on CPU. They are
  correct but slow.
- `bitsandbytes` 4/8-bit loading in this pipeline requires CUDA. For CPU
  deployment, export GGUF and run llama.cpp, or use fp32/bf16.
- Apple MPS is supported by the inference engine for standard operations; not
  every custom kernel is available. Test before relying on it.

## Cost reporting

No price is assumed. Supply explicit rates:

```bash
python scripts/evaluate.py ... --cost-per-hour-usd 0.40
```

or configure `reporting.electricity_cost_per_kwh_usd` and
`reporting.hardware_watts` for an energy estimate. Cost figures are only
meaningful with stated assumptions; the repository never invents a cloud price.

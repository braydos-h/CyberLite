# Compute budget

This page explains how the GPU request is priced. Every figure is a **planning
estimate** produced from the assumptions below; none is a quote or a
measurement. The model is implemented in
[`cyberlite/compute_budget.py`](../cyberlite/compute_budget.py).

```bash
make budget
# or, with explicit assumptions:
python scripts/compute_budget.py \
  --config configs/lora.yaml \
  --config configs/qlora.yaml \
  --config configs/low_vram.yaml \
  --config configs/distillation.yaml \
  --train-tokens 30000000 --epochs 3 \
  --distill-tokens 10000000 --eval-conditions 8 \
  --effective-tflops 30 --gpu-hour-usd 0.60 --contingency 0.30 \
  --markdown
```

Change an assumption, regenerate the table, and quote the command with the
number. Do not quote a table without its assumptions.

## Method

| Quantity | Formula | Why |
|---|---|---|
| Training FLOPs | `6 × N × D` | Forward + backward per token; the standard dense-equivalent approximation |
| LoRA/QLoRA adjustment | none | Frozen weights still receive the full forward and backward pass; adapter gradients are small |
| Training GPU-hours | `FLOPs / (effective TFLOP/s × 3600)` | Uses achievable throughput, not datasheet peak |
| Generation GPU-hours | `tokens / tokens-per-second / 3600` | Token generation is memory-bandwidth bound, so FLOPs are a poor predictor |
| Cost | `GPU-hours × explicit $/hour` | No hidden rate is invented |

`effective TFLOP/s` is the only number that must come from hardware. The default
of **30 TFLOP/s** is a conservative placeholder for a 24 GB Ada-class card
running bf16 LoRA with gradient checkpointing and Python-side overhead. Replace
it with the measured value from the bring-up report
([docs/gpu-bringup.md](gpu-bringup.md)) before quoting a budget.

## Core assumptions

| Assumption | Default | Rationale |
|---|---:|---|
| Effective training throughput | 30 TFLOP/s | Conservative for one consumer/prosumer GPU in bf16 with checkpointing |
| Training tokens per epoch | 30,000,000 | A pilot corpus target, not a measured dataset size |
| Epochs | 3 | Common small-model SFT schedule; the configs default to 1 |
| Teacher | 4B parameters | `configs/distillation.yaml` default |
| Teacher generation throughput | 30 tokens/s | Local bf16 teacher on one 24 GB card |
| Distillation tokens | 10,000,000 | Planning target for a reviewed pilot corpus |
| Inference throughput | 120 tokens/s | 4-bit/bfloat16 small-model generation on a modern GPU |
| Evaluation | 8 conditions × 4,000 items × 200 tokens | The E0–E7 matrix |
| Notional GPU-hour rate | $0.60/GPU-hour | Amortised hardware + electricity for comparison only; not a rental price |
| Contingency | 30% | Failed runs, re-runs, and scheduler overhead |

Hardware purchase, electricity, storage, and human review are **excluded** from
the estimator and priced separately below. The scenario dollar columns are a
comparison device, not the funding request; the request is the hardware bill of
materials.

## Scenario A — Tier 0 (unblock)

Four training configurations, three epochs, one distillation corpus, eight
evaluation conditions.

| Item | GPU-hours | Notional cost at $0.60/h |
|---|---:|---:|
| Four training runs (bf16 LoRA, QLoRA, low-VRAM QLoRA, distilled) | 17.04 | $10.22 |
| Distillation generation (4B teacher, 10M tokens) | 92.59 | $55.56 |
| Evaluation (8 × 4,000 items × 200 tokens) | 14.81 | $8.89 |
| Contingency (30%) | 37.33 | $22.40 |
| **Total** | **161.77** | **$97.06** |

## Scenario B — Full matrix

Twelve runs (rank/sequence ablations and controls), same distillation and
evaluation:

| Item | GPU-hours | Notional cost at $0.60/h |
|---|---:|---:|
| Twelve training runs | 51.12 | $30.67 |
| Distillation generation | 92.59 | $55.56 |
| Evaluation | 14.81 | $8.89 |
| Contingency (30%) | 47.56 | $28.53 |
| **Total** | **206.08** | **$123.65** |

## Measured CPU evaluation (not the bottleneck)

On 2026-11-25 the full 2,182-item SecEval file was evaluated on the reference CPU
host (i5-9500T, 6 threads, 15.4 GiB RAM, fp32, no GPU):

```bash
python scripts/evaluate.py \
  --dataset data/evaluation/seceval_v1.jsonl \
  --protocol seceval --group-by topics --max-new-tokens 5 \
  --out results/baseline/e0-instruct-seceval \
  --seed 42 --temperature 0 --device cpu --dtype float32
```

| Measurement | Value |
|---|---:|
| Items | 2,182 |
| Wall clock | 3,555.8 s (59 m 16 s) |
| Mean latency per item | 1.63 s |
| Median / p95 | 1.23 s / 2.00 s |
| Peak RSS | 5.45 GB |

A full pass costs about an hour, so seven evaluation conditions are roughly
seven hours. **Evaluation is affordable on CPU.** The GPU request is not about
scoring; it is about training and teacher generation.

## Why training and distillation are the bottleneck

| Workload | On this CPU | On one 24 GB card |
|---|---:|---:|
| 10M-token teacher corpus | ≈451 hours at 6.16 tokens/s (≈19 days) | ≈93 hours at 30 tokens/s |
| One 30M-token training epoch | ≥1,350 hours at 6 tokens/s (≈56 days, forward-only lower bound) | ≈4 GPU-hours at 30 TFLOP/s |
| 2,182-item evaluation | ≈1 hour | minutes, but not the constraint |

The CPU numbers use the measured 6.16 tokens/s inference rate; backward passes
make training slower than that lower bound. The GPU numbers are planning
estimates from the same model, not measurements. This is the case for one card:
it turns a multi-week teacher corpus into four days, and an impractical training
epoch into an afternoon.

## Bill of materials (hardware only)

No cloud credits, rentals, or subscriptions are requested. Prices are
order-of-magnitude and move; re-check before quoting.

| Item | Tier | Planning cost | Notes |
|---|---|---:|---|
| Used 24 GB card (3090 class) | 0 | ≈$800–1,100 | The unblock. Any CUDA-capable 24 GB card works |
| New 24 GB card (4090 class) | 0 alternative | ≈$1,600–2,200 | Faster iteration; same VRAM class |
| PSU (850 W) | 0/1 | ≈$100–150 | Only if the host supply is insufficient |
| 1 TB NVMe | 0/1 | ≈$60–100 | Weights, checkpoints, corpora |
| 8 GB card (used) | 1 | ≈$200–300 | Smallest realistic training class |
| 16 GB card (new) | 1 | ≈$450–600 | bf16 LoRA at short sequences |
| 48 GB card (used) | 2 | ≈$4,000–7,000 | 26B 4-bit QLoRA; bf16 still needs 80 GB |

Host CPU/RAM is assumed to exist; 32 GB system RAM is recommended. A used
workstation with a suitable PSU can be cheaper than upgrading a desktop.

**Specific recommendation:** a used RTX 3090 (24 GB) is the best price-per-VRAM
for Tier 0. It needs two 8-pin connectors and a 750–850 W PSU. A 12 GB card is
not enough for the reference bf16 run, and a 16 GB card is only for the boundary
test, not the main matrix.

**Electricity:** 200 GPU-hours at ~350 W is ~70 kWh. At $0.15–0.25/kWh that is
**$10–18**; a full system adds the CPU and monitors. This is small compared with
the hardware. The ask is a one-time capital purchase, not a recurring credit
balance.

**Why not rent instead:** the 4–8 GB classes are not generally available for
rent, allocator ceilings are only a proxy, and fixed hardware is part of the
reproducibility claim. Renting would be cheaper in cash for a few hundred hours;
that is stated rather than hidden, and the tradeoff is accepted deliberately.

**Memory-class testing without five cards:** `scripts/cuda_memory_fraction.py`
caps the process allocator to approximate a smaller card (0.25 of 24 GB ≈ 6 GB,
0.33 ≈ 8 GB, 0.50 ≈ 12 GB). MIG partitions are a better approximation where
available. Neither reproduces driver overhead, allocator fragmentation, or
desktop VRAM use. Report emulated results as emulated; the 4 and 8 GB classes
should be confirmed on real hardware before publishing a deployment claim.

## What is deliberately excluded

- Maintainer time. This is a single-person project; the budget does not include a
  salary, contractor, or second engineer.
- Paid external review of the distillation corpus and generated security
  guidance (priced separately in Tiers 1–2 of [FUNDING.md](../FUNDING.md)).
- Storage and egress (a few GB; negligible at this scale).
- Benchmark license fees (none are currently planned; some datasets are
  evaluation-only).
- A larger teacher model. A 30B-class teacher changes the distillation line by
  roughly an order of magnitude and should be a separate, justified line item.

## Scaling to a 26B control

The estimator accepts a parameter-count override so a conditional control model
can be priced before a config exists:

```bash
python scripts/compute_budget.py \
  --config configs/qlora.yaml \
  --parameters-b 26 \
  --train-tokens 30000000 --epochs 3 \
  --effective-tflops 120 --markdown
```

That yields ≈32.5 GPU-hours per three-epoch run at 120 TFLOP/s, before
distillation and evaluation. Memory is a separate question: 26B is ≈52 GB in
bf16 and ≈13 GB at 4-bit for weights alone, so bf16 LoRA needs an 80 GB card
while 4-bit QLoRA is plausible on 24–48 GB. This is a projection from the same
formula, not a 26B measurement. The current request intentionally excludes it;
see [FUNDING.md](../FUNDING.md#beyond-tier-2--the-26b-rung).

## Replacing assumptions with measurements

After the bring-up run, update this page with:

1. measured tokens/s at 128, 512, and 2,048 prompt tokens;
2. measured peak VRAM for bf16 LoRA and 4-bit QLoRA;
3. measured seconds per optimizer step at 1,024 tokens;
4. the exact GPU, driver, CUDA, PyTorch, Transformers, and bitsandbytes versions.

Then re-run `make budget` with the measured throughput. Keep the old estimate in
the changelog so the planning error is visible; that comparison is itself useful
evidence for the next request.

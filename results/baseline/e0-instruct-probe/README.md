# E0 — capability and throughput probe (baseline)

Frozen "how capable and how fast is the starting point" measurement for
`Qwen/Qwen3.5-0.8B` before any adapter training. Later LoRA, QLoRA, distilled,
RAG, and quantized conditions can be compared against the same probe and the
same throughput protocol.

> **A small project-authored probe, not a standardized benchmark.** The 36 items
> were written for this repository and have not been validated as a psychometric
> or security benchmark. The score is a regression signal, not an IQ score or a
> claim of cybersecurity capability. Do not promote it to the README benchmark
> table or the paper.

## Run identity

| Field | Value |
|---|---|
| Condition | E0 — instruct reference, no adapter |
| Model | `Qwen/Qwen3.5-0.8B` |
| Model revision | `2fc06364715b967f1860aea9cf38778875588b17` |
| Parameters | 852,985,920 |
| Device / dtype | CPU / `torch.float32` |
| Prompt style | `chat` (auto-selected) |
| Decoding | temperature 0, seed 42, per-task `max_new_tokens` defaults |
| Repository commit | `923643b235bdc222a4074de34f9b2940b1e06540` |
| Evaluation run (UTC) | 2026-11-25T02:17:31Z |
| Throughput run (UTC) | 2026-11-25T02:18:24Z |

## Probe data

`data/evaluation/baseline_probe_v1.jsonl`, project-authored, synthetic.

| Field | Value |
|---|---|
| File SHA-256 | `f5a7055c5168e77529b52e0d572cf8f987c60d15e6e5c49a0d3099b70857baf4` |
| Harness example hash | `074afb896c33ae1c1e943fb26b6daf728e80a1b77dc0f0619b49314ddeff359c` |
| Items | 36 — 24 MCQ, 12 classification |
| MCQ answer balance | 6 each of A/B/C/D, interleaved so answer position cannot explain a high score (position-only play ≈ 25%) |
| Classification balance | 6 `vulnerable`, 6 `benign`, interleaved |
| Source / license | `project-authored-probe-v1`, synthetic / Apache-2.0-compatible |

## Capability measurements

| Task | n | Metric | Measured | Naive baseline |
|---|---:|---|---:|---:|
| MCQ | 24 | accuracy | **0.958** | 0.25 (random) |
| MCQ | 24 | accuracy 95% bootstrap CI | 0.875–1.000 | — |
| MCQ | 24 | invalid / unparseable | 0.000 | — |
| Classification | 12 | accuracy | **0.500** | 0.500 (majority class) |
| Classification | 12 | macro F1 | **0.333** | — |
| Classification | 12 | false-positive rate (`vulnerable`) | **1.000** | — |

Reading the two tasks together:

- **Knowledge is strong for this checkpoint:** 23/24 MCQ. The single miss was
  `probe-mcq-22` (native Windows log format); the model answered `A` instead of
  `D` (`EVTX`). Because answer positions are balanced and interleaved, the result
  is not an answer-position artifact.
- **Discrimination is absent:** the model answered `vulnerable` for all 12
  classification items. Accuracy therefore equals the majority-class baseline,
  and the false-positive rate is 1.0. This is the more important starting-point
  weakness: the base model knows labels but does not apply them selectively.
- A single aggregate "smartness" score would hide that split, so none is
  reported.

## Throughput measurements

Measured with `scripts/benchmark.py`: deterministic synthetic prompts, 64 new
tokens per run, 2 runs per prompt length, temperature 0.

| Prompt tokens | TPS mean | TPS stdev | TTFT mean | Total latency mean | Peak RSS |
|---:|---:|---:|---:|---:|---:|
| 128 | **6.63** | 0.54 | **1.12 s** | 9.72 s | 5.396 GB |
| 512 | **5.79** | 0.02 | **2.59 s** | 11.07 s | 5.504 GB |

Aggregate across both prompt lengths: **6.16 tokens/s**, 256 generated tokens.

These are CPU-only numbers for this host (Intel Core i5-9500T, 6 threads,
15.4 GiB RAM, PyTorch 2.15.0+cpu). `causal_conv1d` and
`flash-linear-attention` are not installed, so the model uses slower reference
kernels; optimized stacks will differ. Compare only on the same host and
software stack.

## Artifacts and verification

Committed with this snapshot (small JSON/JSONL only; bulk output stays ignored):

| File | SHA-256 |
|---|---|
| `summary.json` | `d6c1e2ff29aff21f1e70fa9de0b089bb2e730b6c0bfb003c26159a384ad21ec2` |
| `predictions.jsonl` | `5de132aaadc436ec08ebde67da0d784e87d274771c8b3ad9e2d9453d83ea5d72` |
| `inference_benchmark.json` | `7cb654d249aeaa394f094d5cb1ff61d859467b6c62a410abda6ea35488077177` |

Evaluation `run_sha256`:
`1e4fac943e79a552a9208b178450060fb97b74f8678f158fd966b722c3c8bd86`.

## Reproduce

```bash
python scripts/evaluate.py \
  --model Qwen/Qwen3.5-0.8B \
  --dataset data/evaluation/baseline_probe_v1.jsonl \
  --out results/baseline/e0-instruct-probe \
  --seed 42 --temperature 0 --device cpu --prompt-style auto

python scripts/benchmark.py \
  --model Qwen/Qwen3.5-0.8B \
  --device cpu \
  --prompt-lengths 128,512 \
  --max-new-tokens 64 \
  --runs 2 \
  --temperature 0 \
  --out results/baseline/e0-instruct-probe/inference_benchmark.json
```

## Compare a later condition

- Keep `baseline_probe_v1.jsonl` byte-identical; a changed probe is a new
  version, not a comparison.
- Add `--adapter runs/<name>` and record the adapter SHA-256 from `summary.json`.
- Compare per-item predictions as well as aggregates; with n=24, one MCQ item is
  4.2 points, and with n=12 one classification item is 8.3 points.
- Re-run the throughput benchmark on the same host, device, dtype, and software
  versions. Do not compare GPU or quantized numbers to this CPU fp32 table
  without labeling the difference.

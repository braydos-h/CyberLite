# E0 — pre-training reference snapshot (smoke set)

**Purpose:** a frozen, reproducible "where the project started" measurement of the
unadapted checkpoint on the committed smoke evaluation set. Later post-training
conditions (LoRA, QLoRA, distilled, RAG, quantized) can be compared against this
run without re-deriving the starting point.

> **This is a pipeline baseline, not a research result.** It uses the eight
> original synthetic items in `data/evaluation/smoke_eval.jsonl`, which the
> dataset card explicitly says are not a scientific benchmark. Do not copy these
> numbers into the README benchmark table, the paper, or any claim of model
> quality.

## Run identity

| Field | Value |
|---|---|
| Condition | E0 — base/instruct reference, no adapter |
| Model | `Qwen/Qwen3.5-0.8B` (instruct; `AutoModelForImageTextToText`) |
| Model revision | `2fc06364715b967f1860aea9cf38778875588b17` (HF `main` at run time) |
| Parameters | 852,985,920 |
| Adapter | none |
| Device / dtype | CPU / `torch.float32` |
| Prompt style | `chat` (auto-selected; checkpoint is not `-base`) |
| Decoding | temperature 0, seed 42, per-task `max_new_tokens` (32 MCQ/cls, 512 gen, 128 completion) |
| Repository commit | `5e7f592a5292f575d1eb91526bbdaaba24482868` (clean) |
| Run started (UTC) | 2026-11-25T02:05:28Z |
| CyberLite version | 0.1.0 |

## Data

| Field | Value |
|---|---|
| File | `data/evaluation/smoke_eval.jsonl` |
| File SHA-256 | `111132beb36f65d9bc57bdb42efe9d801d5971d0f355f23b08723e7b6be5fc3d` |
| Harness dataset hash | `350ab9a509ddfb92f742f90ba65a8acc3c2949a45c54e82a97a500f6cf422102` |
| Items | 8 (4 MCQ, 2 classification, 1 generation, 1 completion) |
| Source / license | `synthetic-heldout`, project-authored synthetic |

## Measured metrics

| Task | n | Metric | Value |
|---|---:|---|---:|
| MCQ | 4 | accuracy | 1.00 |
| MCQ | 4 | invalid rate | 0.00 |
| Classification | 2 | accuracy | 0.50 |
| Classification | 2 | macro F1 | 0.333 |
| Classification | 2 | false-positive rate (`vulnerable`) | 1.00 |
| Generation | 1 | exact match | 0.00 |
| Generation | 1 | token F1 | 0.071 |
| Generation | 1 | unsupported-token proxy | 0.930 |
| Generation | 1 | refusal / execution-claim rate | 0.00 / 0.00 |
| Completion | 1 | exact match | 0.00 |
| Completion | 1 | token F1 / edit similarity | 0.250 / 0.255 |
| Completion | 1 | syntax-valid rate | 1.00 |

### Reading these numbers

- **MCQ accuracy is not evidence of skill.** All four answer keys are `A`, and
  the model answered `A` every time. The 95% bootstrap interval `[1.0, 1.0]` is
  an artifact of n=4 and a degenerate answer key.
- The classification model predicted `vulnerable` for both items (one correct,
  one false positive), so accuracy and FPR reflect a constant-output strategy,
  not discrimination.
- The generation output reached the 512-token cap and scored low on lexical
  overlap; the unsupported-token proxy is lexical only, not a truth measure.
- The completion used FIM mode and returned syntactically valid but incorrect
  Python.

## Operational measurements

| Metric | Value |
|---|---:|
| Wall clock (harness) | 74.1 s |
| Mean latency per item | 9.26 s |
| Median / max latency | 0.74 s / 67.8 s |
| Generated tokens | 540 |
| Throughput | 7.29 tokens/s |
| Peak process RSS | 5.329 GB |
| Hardware | Intel Core i5-9500T (6 threads), 15.4 GiB RAM, no GPU |
| Software | Python 3.12.3, PyTorch 2.15.0+cpu, Transformers 5.24.1, PEFT 0.22.0 |

## Artifacts and verification

Committed with this snapshot (small JSON/JSONL only; bulk output stays ignored):

| File | SHA-256 |
|---|---|
| `summary.json` | `780c8085e4a875c3334c51988ab67e171ce8044ab48aba810cc0703f8cbaf2eb` |
| `predictions.jsonl` | `8be318ef5cd57a0c5198e6b26847e52d1a4d608d6384b5ecc7388f1b6fd258ab` |

The harness-reported `run_sha256` is
`0134da210a0da5a11ab473b49bf8df80842ef6677cd50155e2b9eb17f6000713`.

## Reproduce

```bash
python scripts/evaluate.py \
  --model Qwen/Qwen3.5-0.8B \
  --dataset data/evaluation/smoke_eval.jsonl \
  --out results/baseline/e0-instruct-smoke \
  --seed 42 --temperature 0 --device cpu --prompt-style auto
```

## Compare a later condition

Use the same dataset file, seed, temperature, prompt style, and device; add
`--adapter runs/<name>` and a new `--out` directory. Record the adapter
SHA-256 from the resulting `summary.json`.

- Keep `smoke_eval.jsonl` byte-identical while comparing. If the set changes,
  freeze this baseline and treat the new set as a new version.
- Changing device, dtype, or quantization changes numerics; report it rather
  than mixing runs.
- Compare per-item predictions, not only aggregate metrics: with n=8, one item
  moves accuracy by 25 points (MCQ) or 50 points (classification).
- Never promote these numbers to `results/` publication tables; the set is
  synthetic and unrepresentative.

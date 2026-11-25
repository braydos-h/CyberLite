# E0 — SecEval baseline (full benchmark)

Frozen "before" measurement of `Qwen/Qwen3.5-0.8B` on the real SecEval
benchmark, before any adapter training. Later LoRA, QLoRA, distilled, and RAG
conditions should reuse the same items, prompt, scoring rule, and seed.

> **This is the base model, not a CyberLite checkpoint.** SecEval is
> CC BY-NC-SA 4.0 and evaluation-only; the items are not redistributed here. The
> aggregate score is a starting point for measuring improvement, not a claim of
> cybersecurity capability.

## Headline

| Slice | n | Exact-set accuracy | 95% bootstrap CI | Invalid |
|---|---:|---:|---:|---:|
| **SecEval overall** | **2,182** | **0.346** | **0.327–0.365** | 0.000 |
| Single-answer items | 1,257 | 0.591 | 0.562–0.619 | 0.000 |
| Multi-answer items | 925 | 0.014 | 0.008–0.023 | 0.000 |

The overall number is dominated by a failure mode that matters for later
comparisons: the model almost always answers with one letter even when several
choices are correct. It produced a single letter for 1,909 of 2,182 items
(87.5%). Only 13 of 925 multi-answer items were exactly correct.

## Run identity

| Field | Value |
|---|---|
| Condition | E0 — instruct reference, no adapter |
| Model | `Qwen/Qwen3.5-0.8B` |
| Model revision | `2fc06364715b967f1860aea9cf38778875588b17` |
| Parameters | 852,985,920 |
| Device / dtype | CPU / `torch.float32` |
| Prompt style | chat (auto-selected) |
| Protocol | `seceval` — upstream chat instruction, one worked example, choices as `A: ...` |
| Decoding | temperature 0, seed 42, `max_new_tokens=5` |
| Evaluation run (UTC) | 2026-11-25T05:02:40Z |
| Wall clock | 3,555.8 s (59.26 min) |
| Repository HEAD | `2301b8d9cb72f5e5a71528c5d6fbaf4a3e2dcd17` |
| Working tree at run time | dirty; the evaluation code is pinned by file hashes below |

## Dataset

| Field | Value |
|---|---|
| Benchmark | SecEval |
| Upstream | <https://huggingface.co/datasets/XuanwuAI/SecEval> |
| Upstream revision | `205dab7b0888a06f4b53ca7d9c7093e1326683e1` |
| Access date | 2026-11-25 |
| License | CC BY-NC-SA 4.0 — evaluation only, no training use, no redistribution |
| Upstream `questions.json` SHA-256 | `194c3a511104be422a678675a71d44315d0c0392b040745155aeebc321e692e0` |
| Converted JSONL SHA-256 | `6ae74b2c9c45d1024f99453be00ae82d00567f0b5f1ffa1cc4109a2fa4ef1c03` |
| Harness dataset hash | `c3bd9a852924da17a05fefc954d60032f4a146a86861ad4cd40ec0350233064b` |
| Items | 2,182 usable of 2,189 upstream |
| Excluded | 7 items with an empty answer key |
| Answer balance | 1,257 single-answer, 925 multi-answer (2–4 correct choices) |
| Conversion | `python scripts/prepare_benchmarks.py --download --force` |

The converted file lives at `data/evaluation/seceval_v1.jsonl` and is ignored by
Git. It is in that directory so the training-data preparation pipeline screens
against it automatically.

## Protocol

SecEval's upstream evaluation script uses a fixed instruction, one worked
example, five new tokens, and exact match over the set of answer letters. The
`seceval` protocol reproduces that shape:

- system instruction: *"Below are multiple-choice questions concerning
  cybersecurity. Please select the correct answers and respond with the letters
  ABCD only."*
- one-shot example: `Question: Which mitigation prevent stack overflow bug? ...`
  → `Answer: ABC`
- choices rendered as `A: ... B: ... C: ... D: ...`
- temperature 0, `max_new_tokens=5`, seed 42, batching off
- prediction is the set of uppercase `A`–`D` letters in the output; an item is
  correct only when that set exactly equals the key
- the 6 items that hit the five-token cap are still parsed; 0 outputs were
  unparseable

## Per-topic results

Items can carry more than one topic, so topic counts sum above 2,182.

| Topic | n | Accuracy | 95% CI |
|---|---:|---:|---:|
| PenTest | 473 | **0.412** | 0.370–0.457 |
| WebSecurity | 771 | **0.393** | 0.361–0.427 |
| Vulnerability | 334 | 0.338 | 0.287–0.389 |
| SoftwareSecurity | 232 | 0.332 | 0.276–0.397 |
| ApplicationSecurity | 807 | 0.326 | 0.295–0.359 |
| SystemSecurity | 1,062 | 0.318 | 0.290–0.347 |
| NetworkSecurity | 228 | 0.290 | 0.237–0.347 |
| MemorySafety | 48 | 0.208 | 0.104–0.333 |
| Cryptography | 14 | 0.143 | 0.000–0.357 |

The two largest slices, SystemSecurity (1,062) and ApplicationSecurity (807),
are both below the overall score. PenTest and WebSecurity are the relative
strengths. Cryptography and MemorySafety are too small for stable conclusions;
their intervals span most of the plausible range.

## Answer-composition analysis

Computed from the local `predictions.jsonl` (hash below). "Exact set" means the
predicted set equalled the key.

| Gold set size | n | Answered one letter | Answered more than one | Exact set |
|---|---:|---:|---:|---:|
| 1 | 1,257 | 1,179 | 78 | 743 (59.1%) |
| 2 | 736 | 588 | 148 | 10 (1.4%) |
| 3 | 176 | 135 | 41 | 2 (1.1%) |
| 4 | 13 | 7 | 6 | 1 (7.7%) |

This is the main finding for the "before" state: the checkpoint has usable
single-choice knowledge (59.1%) but has not learned SecEval's multi-select
convention. A later adapter that only improves single-choice accuracy can still
look flat overall unless multi-answer formatting improves too; report both
slices.

## Operational measurements

| Metric | Value |
|---|---|
| Wall clock | 3,555.8 s (59.26 min) |
| Latency mean / median | 1.628 s / 1.229 s |
| Latency p95 / max | 2.001 s / 42.577 s |
| Generated tokens | 4,391 (2.01 per item) |
| Generated tokens per second | 1.236 (generated tokens / summed item latency) |
| Peak process RSS | 5.446 GB |

The tokens-per-second value is generated tokens divided by summed per-item
latency, so it includes prompt prefill and is not comparable to the separate
throughput protocol in `scripts/benchmark.py`. Use the E0 probe table for a
like-for-like throughput comparison on the same host.

## Limitations

- Single run, one prompt, one decoding setting. No prompt-sensitivity study.
- SecEval's pretraining contamination for this checkpoint is unknown. The
  repository screens its own training data, not the base model's pretraining.
- Seven upstream items were dropped because their answer key is empty.
- SecEval is non-commercial and share-alike; do not use its items for training
  and do not redistribute the converted file.
- Published SecEval leaderboard numbers use the same benchmark but different
  model families, prompts, and evaluation dates. Do not compare a 0.8B
  CPU-run number to them as if compute were matched.
- Aggregate scores hide the single/multi split. Always report both, plus the
  per-topic breakdown.

## Artifacts and verification

| File | SHA-256 | Git |
|---|---|---|
| `summary.json` | `40af2995d922541f28d503693a58ef0cf3c49f591c0a39c47614f06f96f64b62` | committed |
| `predictions.jsonl` | `a23026ae7453b1344624dd286316263247f0db5ce486595f05591beb4f9c84e9` | local only (SecEval license) |
| `cyberlite/evaluation/harness.py` | `ec0b29205b7678546faf6f73606d10a465ae60b326850fcfab93ccb353405bb6` | — |
| `cyberlite/evaluation/metrics.py` | `041ef5e1977d9f12ad74874f8e4496e185fa43339f4a35e515f50e61ad91648a` | — |
| `cyberlite/evaluation/seceval.py` | `8d218008123d8bef237fe23318a73aa0b60e7fff69ab44c1d1a628bafcea8e99` | — |
| `scripts/prepare_benchmarks.py` | `221764921367516d6e43999df67a270a22ed09ad9683626865ed9e4c20fa7471` | — |

Evaluation `run_sha256`:
`0f2d45e576924a9d6dfb92e77a22dd5b3cc881da3aec95a87ec3a319bc9da90d`.

## Reproduce

```bash
python scripts/prepare_benchmarks.py --download --force

python scripts/evaluate.py \
  --model Qwen/Qwen3.5-0.8B \
  --dataset data/evaluation/seceval_v1.jsonl \
  --out results/baseline/e0-instruct-seceval \
  --device cpu --prompt-style auto \
  --protocol seceval --group-by topics \
  --seed 42 --temperature 0 --max-new-tokens 5
```

## Compare a later condition

- Keep `seceval_v1.jsonl` byte-identical; a changed upstream revision is a new
  version, not a comparison.
- Keep `--protocol seceval`, `--group-by topics`, `--seed 42`, temperature 0,
  and `--max-new-tokens 5`.
- Add `--adapter runs/<name>` and record the adapter SHA-256 from `summary.json`.
- Compare overall, single-answer, multi-answer, and per-topic accuracy, not only
  the headline. On the 925 multi-answer items, a model that never emits
  multi-letter answers cannot exceed roughly the single-choice rate there.
- For speed, re-run `scripts/benchmark.py` on the same host, device, and
  software stack. Do not compare this CPU fp32 table to a GPU or quantized run
  without labeling the difference.

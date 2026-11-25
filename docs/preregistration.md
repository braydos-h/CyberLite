# Pre-registration draft

**Status: draft, not externally registered.** This document fixes the
hypotheses, thresholds, and analysis plan *before* any adapter is trained. To
count as pre-registration it must be timestamped outside this repository (OSF,
Zenodo, or an arXiv v1) and that identifier recorded here. Until then, treat it
as a public commitment, not a registration.

The point is to make the project falsifiable and to prevent the results table
from being written after the numbers arrive.

## Research question

Can a sub-billion-parameter model (`Qwen/Qwen3.5-0.8B`, 852,985,920 parameters)
be post-trained into a useful defensive-security assistant that trains and runs
on consumer hardware, and which of LoRA, QLoRA, distillation, and retrieval
contribute measurably at matched compute?

## Conditions

| ID | Condition | Purpose |
|---|---|---|
| E0 | Base/instruct, no adapter | Reference |
| E1 | bf16 LoRA | Quality reference for parameter-efficient tuning |
| E2 | 4-bit QLoRA | Consumer-hardware condition |
| E3 | Offline-distilled student | Teacher-data condition at matched student compute |
| E4 | E2 + BM25 retrieval | Grounding condition |
| E5 | E2 quantized at inference (4/8-bit, GGUF) | Deployment parity |
| E6 | CPU-only deployment | Offline/air-gapped condition |
| E7 | Larger general model (control) | Optional; only if compute allows |

All conditions use the same frozen data manifest, prompt templates, seeds, and
decoding settings. Any deviation is logged.

## Hypotheses and thresholds

These are the numbers that decide success. They were chosen to be meaningful for
a defensive assistant, not to be easy to hit.

### H1 — Task capability (primary)

4-bit QLoRA improves held-out security multiple-choice accuracy by **at least 10
percentage points** over E0, with the 95% bootstrap confidence interval
excluding zero.

Secondary within H1: vulnerability classification false-positive rate falls
**below 20%** (E0 measures 100% on the project probe) while macro F1 is at least
0.60.

### H2 — Quantization parity (primary)

E2 retains **≥95%** of E1's accuracy on the primary benchmark, and the general
retention score drops by **≤2 percentage points** relative to E1.

### H3 — Retrieval grounding (primary)

E4 improves grounded-QA token F1 by **≥5 points** over E2, and the
unsupported-token proxy falls by **≥10% relative**, with citations present on
≥95% of answers that make a factual claim.

### H4 — Distillation (secondary)

At matched student compute and matched token budget, E3 is **non-inferior** to
E2 within 2 points, and strictly better by **≥3 points** on at least one
reasoning or generation task. A negative result is reported as a negative result.

### H5 — Deployment (secondary)

On an 8 GB device at 4-bit: **≥15 tokens/s** generation, **≤2 s** time to first
token at a 512-token prompt, and **≤7.0 GB** peak device memory. Numbers are
reported per device, with the exact quantization format.

### H6 — Safety (secondary, non-negotiable)

No condition increases the execution-claim rate or the unsafe-compliance rate
relative to E0 by more than **5 percentage points**. An increase blocks release
of that adapter regardless of benchmark gains.

### H7 — Autocomplete (exploratory)

On held-out completion tasks across the documented language profiles, syntax-valid
rate **≥95%** and exact-match improves by **≥5 points** over E0. A small
authorized-user acceptance study (n ≥ 5) reports acceptance rate with its
interval; it is exploratory and will not be reported as a product metric.

## Primary benchmark

The primary benchmark must be **external and license-compatible**; the
project-authored probe is a regression signal only and cannot carry H1.

The benchmark choice is recorded in `benchmarks/<name>/SOURCE.md` with its
license before any adapter is trained. If no suitable external benchmark can be
licensed, H1 is reported on a frozen, independently authored held-out set and the
limitation is stated in the abstract.

## Analysis plan

- **Splits:** fixed before training; test items never enter training or model
  selection. Contamination screening at 13-gram overlap is run against every
  evaluation file.
- **Intervals:** 10,000-resample bootstrap, percentile method, reported for every
  headline accuracy, F1, and FPR.
- **Paired comparisons:** McNemar's test for MCQ conditions on identical items;
  paired bootstrap for continuous metrics. Report effect size, not only p.
- **Multiplicity:** Holm–Bonferroni across the three primary hypotheses (H1–H3).
  Secondary and exploratory results are labeled as such.
- **Seeds and runs:** one seed for the main matrix, three seeds for the headline
  condition if budget allows. All runs are reported, including failed ones.
- **Exclusions:** no post-hoc item removal. If an item is invalid, the rule and
  the count are reported before unblinding scores.
- **Missing data:** an unparseable answer counts as incorrect; the invalid rate
  is reported separately.
- **Negative results:** published with the same artifacts as positive ones.

## Freezing and deviations

| Item | Frozen at | Identifier |
|---|---|---|
| Data manifest | before first adapter | |
| Evaluation sets | before first adapter | |
| Prompt templates | before first adapter | |
| Decoding parameters | before first adapter | |
| Analysis code | before scoring | |

Deviations are appended here with a date and reason, not silently applied:

| Date | Deviation | Reason | Impact |
|---|---|---|---|
| | | | |

## Stopping rules

- If E0 already scores **≥90%** on the primary benchmark, the ceiling is too low
  to test H1; the study pivots to discrimination, FPR, and grounding, and says so.
- If general retention falls by **>10 points**, training stops and the run is
  reported as catastrophic forgetting rather than tuned around.
- If the 4-bit condition fails H6, it is not released even if H1 passes.
- If the GPU bring-up cannot produce a stable run, no research-scale claim is
  made; the engineering failure is reported instead.

## What would falsify the project thesis

A well-measured result where the 0.85B model, after the full matrix, remains at
or below the base model on the primary benchmark while costing more than the base
model to deploy. That is a publishable negative result and will be reported as
one.

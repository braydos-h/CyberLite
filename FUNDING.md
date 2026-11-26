# Funding and compute request

**Status: draft for review.** Every dollar and GPU-hour below is a planning
estimate derived from explicit assumptions, not a quote or a measurement. The
estimator that produces the numbers is
[`cyberlite/compute_budget.py`](cyberlite/compute_budget.py); regenerate with
`make budget` after changing an assumption.

CyberLite is an open research project asking whether a sub-billion-parameter
model can do useful defensive-security work on consumer hardware. The software
pipeline, data-provenance tooling, evaluation harness, and CPU reference runs
already exist. The missing ingredient is a CUDA GPU: no part of the training or
inference path has ever run on one, so every GPU claim in the repository is
currently an untested plan.

The current ask is deliberately small, because the current model is small.

## The ask

| Tier | What it buys | Amount (planning) | What ships |
|---|---|---|---|
| **0 — Unblock** | One used 24 GB CUDA card (plus PSU/storage if needed) | **≈$1,000–2,000** | GPU bring-up report, 4-run training matrix, first real adapter, external benchmark numbers, quantization check |
| **1 — Complete matrix** | 24 GB + 8 GB cards, a 16 GB card for the bf16 boundary, external review | **≈$6,000–7,000** | The full E0–E7 comparison with confidence intervals, GGUF release, reproduction archive |
| **2 — Scale check** | 48 GB card, 8/16 GB confirmation devices, external review (conditional on Tier 1) | **≈$12,000–15,000** | 26B QLoRA feasibility, protocol-at-scale report; requires a collaborator for bf16 |

Only Tier 0 is required to start. Its bill of materials is one used 24 GB CUDA
card (plus an 850 W PSU and 1 TB NVMe if the host needs them); no cloud credits
are requested. Tiers 1–2 are what the results would justify *after* Tier 0 lands.
The full breakdown is in [docs/compute-budget.md](docs/compute-budget.md).

Planning breakdown: Tier 1 ≈ $3,000 hardware (24 GB + 16 GB + 8 GB and host
parts), ≈$2,500 paid external review, ≈$1,000 contingency. Tier 2 ≈ $8,000
hardware (48 GB + confirmation devices), ≈$4,000 external review, ≈$2,000
contingency.

This is a **single-maintainer project**. The budget prices hardware and
per-piece external review only. It does not assume cloud credits, employees,
contractors, or parallel workstreams. If a funder wants to pay maintainer time,
that is a separate agreement, not something folded into these tiers.

### Beyond Tier 2 — the 26B rung

The [README](README.md#scaling-path) names a 26B follow-on model. Tier 2's 48 GB
card is enough to test 26B at 4-bit QLoRA. The bf16 version needs an 80 GB card
or shared cluster access and is realistically a collaboration, not a solo
deliverable: one person cannot run an 80 GB matrix and the 0.85B program in the
same period. Neither is folded into the current ask.

| Constraint | 0.85B (now) | 26B (conditional) |
|---|---|---|
| bf16 weights | ~1.6 GB | ~52 GB |
| 4-bit weights | ~0.4 GB | ~13 GB |
| Practical training hardware | 8–24 GB | 24–48 GB for 4-bit QLoRA; 80 GB for bf16 LoRA |
| bf16 LoRA, 3 epochs, 30M tokens/epoch | ~4 GPU-hours/run | ~26–43 GPU-hours/run at 100–150 TFLOP/s |
| 10M-token distillation corpus | ~93 GPU-hours at 30 tok/s | ~140–280 GPU-hours at 10–20 tok/s |
| Rough purchase for fixed hardware | ~$1,000–2,000 | ~$10,000–30,000 (80 GB class, verify) |

A 26B model also changes the deployment story: it does not fit the 8 GB laptop
target this project is built around. Treat it as a server-class control that
tests whether the protocol scales, not as the consumer-hardware deliverable or a
solo deliverable.

These are estimates from the same `6 × N × D` model, not measurements. A 26B
config does not exist yet; when it does, run
`python scripts/compute_budget.py --config configs/<26b>.yaml` and replace this
table.

### Why hardware rather than cloud?

This is a consumer-hardware research project, so the hardware is part of the
method, not just a cost line. Cloud is cheaper in cash terms for a few hundred
hours, so the case has to be about the experiment:

- **Fixed hardware** across a multi-month comparison: same card, driver, CUDA
  version, power limit, and thermal behavior for every condition.
- **The 4, 6, and 8 GB classes are not generally rentable.** Allocator ceilings
  are a proxy, not a measurement, and the deployment claim is about those cards.
- **Offline operation is a design goal.** No session expiry, no egress, no
  recurring billing, and the same machine can run air-gapped.
- **The card is a reusable asset** for later releases, reproductions, and
  follow-up work rather than a consumed credit balance.

The tradeoffs are real: higher upfront cost than ~$100 of rental hours, no
elasticity, one card is a single point of failure, and upgrades are capex. The
ask is sized accordingly: one used 24 GB card to start, and only the extra cards
needed to make boundary claims credible.

## What already exists

These are verifiable in the repository today:

- An installable package, CLI entry points, unit tests, and CI.
- Architecture-aware loading of `Qwen/Qwen3.5-0.8B`, verified by a local load and
  a LoRA backward pass (CPU).
- A two-step CPU smoke run that exercises the full training path.
- An evaluation harness with bootstrap intervals, per-item predictions, and run
  hashes.
- A frozen CPU baseline: **23/24** on a project-authored MCQ probe, **0.50**
  classification accuracy with a **false-positive rate of 1.00** (the model
  labels everything `vulnerable`), and **6.16 tokens/s** at 5.4 GB RSS on an
  i5-9500T. See [`results/baseline/`](results/baseline/).
- A full **2,182-item SecEval baseline** for the untrained base model: 34.65%
  overall, 59.11% on single-answer items and 1.41% on multi-answer items, with
  bootstrap intervals and per-topic breakdowns.
- Dataset provenance, license gating, secret redaction, deduplication, and
  contamination screening, exercised on a committed pilot manifest: ATT&CK +
  CWE, 2,006 records, 96 near-duplicates removed, 241,515 evaluation n-grams
  screened with zero verbatim 13-gram overlap.
- A local OpenAI-compatible API and BM25 retrieval.

## What does not exist yet

- Any GPU measurement: no CUDA throughput, no VRAM figure, no bitsandbytes run.
- A trained CyberLite checkpoint. The untrained base model's full SecEval
  baseline exists (34.65% overall), but that is the starting point, not a
  CyberLite result.
- A pilot corpus at the full G1 scope: NVD, OWASP, and Linux/networking
  documentation are not ingested yet; ATT&CK + CWE is published.
- A published paper: [`paper/`](paper/) is a scaffold with placeholders.

Funders should read the generated progress block in the
[README](README.md#goals-and-live-progress): 14 of 39 milestones are complete.
The honest framing is *"the CPU path is built and measured; the GPU path is
specified but untested."*

## Why a GPU is the bottleneck

The CPU baseline is enough to prove the wiring, not to train:

| Constraint | Measured / planned | Consequence |
|---|---|---|
| CPU inference | 6.16 tokens/s | A 10M-token teacher corpus is ≈19 days |
| CPU training | full forward/backward works, but minutes per step at 1024 tokens | A 30M-token epoch is ≥56 days at inference speed; not practical |
| Teacher distillation | a 4B teacher generating 10M tokens | ≈93 GPU-hours at 30 tokens/s versus ≈451 CPU-hours |
| Memory-class study | 4–16 GB targets | Requires cards in those classes, or careful memory-fraction emulation |
| CPU evaluation | 2,182 items in 59 minutes | Affordable; seven conditions ≈7 hours, so scoring is not the bottleneck |

The GPU does not change the research question. It makes training and teacher
generation possible within a funding period. Evaluation is already affordable on
CPU, which is why the budget does not ask for evaluation hardware.

## What the GPU unlocks

| Deliverable | Depends on | Evidence produced |
|---|---|---|
| GPU bring-up report | 1 GPU, ~4 hours | CUDA/bnb versions, tokens/s, VRAM, OOM boundaries |
| bf16 LoRA reference adapter | 1× 24 GB | First trained CyberLite checkpoint, config hash, VRAM/time |
| 4-bit QLoRA adapter | 1× 8–24 GB | Matched-data comparison against bf16 |
| Memory-class matrix | 1 card + allocator ceilings; confirm 8 GB if available | Measured and emulated peak VRAM/throughput per class |
| Distillation corpus | Teacher hours | Reviewed teacher outputs with license record |
| Full evaluation | GPU inference | Base/LoRA/QLoRA/distilled/RAG results with CIs |
| Quantized release | 8 GB card | GGUF/4-bit latency and quality-regression report |

Each deliverable lands in `results/` with raw predictions, configuration, and
hardware metadata, per [docs/reproducibility.md](docs/reproducibility.md).

## Capacity: one person, serial work

The project has **one maintainer** and no employees, contractors, or rotating
contributors. That shapes the plan more than the hardware does.

- Experiments run **one at a time**. The 12-run matrix is serialized; there is no
  parallel ablation queue and no second person to review runs as they finish.
- A realistic serial schedule after Tier 0: bring-up and corpus freeze 4–6
  weeks, full matrix 10–14 weeks, evaluation and paper 4–6 weeks. Milestones are
  ordered so a partial matrix is still publishable.
- If time runs short, cut in this order: the 26B rung, multi-seed repeats, larger
  control models. Do **not** cut: seed fixing, raw predictions, the safety
  gate, or negative results.
- The bus factor is one. Mitigations are committed configs and manifests, DOI
  artifacts where licenses allow, and paid external review at the end of a
  milestone — not a second employee.

A funder should size the award to what one person can finish, not to what the
experiment matrix would ideally contain.

## Budget summary

From `make budget` with the repository configs, 30M tokens per epoch, three
epochs, a 4B teacher generating 10M tokens, and eight evaluation conditions.
The dollar column uses a **notional $0.60/GPU-hour** to compare experiment cost;
it is not a rental rate. It approximates a $1,500 card amortised over ~3,000
hours plus electricity.

| Item | GPU-hours | Notional cost at $0.60/h |
|---|---:|---:|
| Four training runs | 17.0 | $10.22 |
| Distillation generation | 92.6 | $55.56 |
| Evaluation (8 conditions × 4,000 items) | 14.8 | $8.89 |
| Contingency (30%) | 37.3 | $22.40 |
| **Total** | **161.8** | **$97.06** |

Training compute is not the expensive part; the card is. The real constraints
are distillation wall-clock, access to the 4–8 GB classes, and external review.
That is why the ask is one used card plus a small confirmation card, not a
cluster. Full assumptions, the bill of materials, and electricity estimates are
in [docs/compute-budget.md](docs/compute-budget.md).

## Success criteria

The project is falsifiable and the thresholds are written down before training
in [docs/preregistration.md](docs/preregistration.md). In brief:

- at least **+10 points** held-out security MCQ accuracy over the base model,
  with the 95% CI excluding zero;
- vulnerability false-positive rate **below 20%** (baseline: 100%);
- 4-bit deployment retains **≥95%** of the bf16 adapter's primary accuracy and
  loses **≤2 points** of general retention;
- **≥15 tokens/s** and **≤2 s** time-to-first-token at 4-bit on an 8 GB device;
- no increase in execution-claim or unsafe-compliance rate.

If the thresholds are missed, the negative result is published with the same
artifacts. A well-measured "a 0.85B model is not good enough at this" is a
useful outcome and will be reported as one.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Qwen3.5 hybrid attention does not work with the CUDA stack | Bring-up checklist runs before any long job; fall back to SDPA/eager and document |
| Distillation corpus is low quality or license-risky | Review sample, license record per source, quarantine unknowns |
| The model is too small to beat the threshold | Pre-registered negative result; report retention and failure modes |
| Benchmark licensing blocks release | Use evaluation-only adapters; publish predictions only where allowed |
| Hardware is idle between experiments | One card is shared serially; idle time has no recurring cost. A second small card exists only for boundary validation |
| Key-person risk | All runs reproducible from committed configs; governance in [GOVERNANCE.md](GOVERNANCE.md) |

## Use of funds and governance

- Compute and hardware only, unless a tier explicitly includes paid external
  review.
- Every purchase over $500 is listed in the public changelog with its purpose.
- Donated hardware remains with the project and is named on the website unless
  the donor asks otherwise.
- Results are released under Apache-2.0 (code) and the licenses of the
  underlying data; no benchmark text is redistributed.
- Decision-making and conflict-of-interest rules are in
  [GOVERNANCE.md](GOVERNANCE.md).

## What this project will not do

No autonomous exploitation, no command execution, no unlicensed benchmark
redistribution, no production-readiness claims from smoke tests, and no
leaderboard score without raw predictions. See
[docs/roadmap.md](docs/roadmap.md#non-goals) and
[docs/safety.md](docs/safety.md).

## Where this can go

These are categories to investigate, not endorsements or claims of eligibility;
terms change and several require an institutional applicant.

- **Open-source infrastructure funds** (for example NLnet/NGI Zero, OpenSSF,
  Sovereign Tech Fund) for the tooling, data provenance, and offline deployment
  work.
- **Security and public-interest research funds** for the evaluation, safety
  study, and negative-result reporting.
- **Hardware programs and vendor discounts** (NVIDIA, AMD, workstation/refurb
  resellers, university surplus) for Tier 0. A used 24 GB card is the fastest
  path to a measured GPU result.
- **University or lab collaboration** where a faculty partner provides shared
  hardware for the 26B rung; this also addresses the bus-factor risk.

A funder that wants a single fixed asset is a better fit for Tier 0 than one that
wants a multi-year program, and vice versa. The tiers exist so the ask can be
matched to the funder instead of inflated for it.

## Contact

**Brayden Habets** — braydenhabets19(at)gmail.com —
[cyberlite.braydos.com](https://cyberlite.braydos.com) —
[github.com/braydos-h/CyberLite](https://github.com/braydos-h/CyberLite)

For a one-page brief, use this file with the reference and limitations sections
removed; the first three sections are the pitch.

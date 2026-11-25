# Goals

**North-star question.** Can a sub-billion-parameter language model be
post-trained into a useful cybersecurity assistant using parameter-efficient
fine-tuning, distillation, retrieval, and quantization, while remaining
practical on consumer hardware?

This file is the executive view: what the project is trying to achieve and the
milestones that show real progress. The dependency-ordered work plan stays in
[docs/roadmap.md](docs/roadmap.md), and every change is recorded in
[CHANGELOG.md](CHANGELOG.md).

## How progress is tracked

- Each goal has milestone checkboxes. `[x]` means the milestone is **verified in
  this repository** — code exists, tests pass, or measured artifacts exist — not
  that it is merely planned.
- `python scripts/update_progress.py` (or `make progress`) regenerates the live
  progress block and badge in the [README](README.md#goals-and-live-progress).
  Never edit that generated block by hand.
- `make progress-check` (also run by CI and by the test suite) fails when the
  README is stale.
- Check a box only in the change that supplies the evidence, and record the
  change in `CHANGELOG.md` under `[Unreleased]`.
- Numbers belong in results and the changelog, not here. This file tracks
  capability, not claims.

## G1 — Licensed, reproducible data foundation

Advances [roadmap Phase 1](docs/roadmap.md#phase-1--dataset-pilot).

**Success:** a versioned pilot corpus that a third party can rebuild or audit
without redistributing restricted text.

- [x] Source and license registry with quarantine for unknown licenses is implemented.
- [x] Cleaning, secret redaction, exact/SimHash dedup, and 13-gram contamination screening are implemented and smoke-tested.
- [x] Deterministic content-hash splits and manifest hashing are implemented.
- [ ] A licensed, versioned pilot corpus (ATT&CK, CWE, NVD, OWASP, Linux/networking docs) is published as a manifest.

  Current slice: ATT&CK + CWE, 2,006 records, manifest committed under
  [`data/manifests/pilot-attack-cwe-v1/`](data/manifests/pilot-attack-cwe-v1/).
  NVD, OWASP, and the system/networking docs remain open.
- [ ] The source-license report is published without redistributing restricted text.
- [ ] A stratified manual quality and safety review of the pilot corpus is complete.
- [ ] Contamination is measured against each selected benchmark subset.

## G2 — Post-training on consumer hardware

Advances [roadmap Phase 2](docs/roadmap.md#phase-2--core-post-training-comparison).

**Success:** trained adapters with honest memory, time, and quality trade-offs
at 4–16 GB VRAM.

- [x] Architecture-aware Qwen3.5 loading is verified by a local load and a LoRA backward pass.
- [x] LoRA and 4-bit QLoRA SFT pipelines support config hashing, resumption, and memory logging.
- [x] A CPU smoke run exercises the full training path end to end.
- [ ] A bf16 LoRA reference checkpoint is trained at matched data and steps.
- [ ] A 4-bit QLoRA checkpoint is trained at matched data and steps.
- [ ] Peak VRAM, wall-clock time, and throughput are measured for the 4, 6, 8, 12, and 16 GB targets.
- [ ] Catastrophic forgetting and general retention are measured against the base model.

## G3 — Honest, reproducible evaluation

Advances [roadmap Phase 2](docs/roadmap.md#phase-2--core-post-training-comparison)
and [roadmap Phase 6](docs/roadmap.md#phase-6--publication).

**Success:** every published number traces back to raw predictions, configs,
and hardware metadata.

The numeric thresholds and the analysis plan are fixed in
[docs/preregistration.md](docs/preregistration.md) before training; the project
probe is a regression signal, not a benchmark.

- [x] Evaluation harness, metrics, bootstrap intervals, and report schema are implemented.
- [x] CyberSecEval, SecEval (evaluation-only), and held-out MCQ adapters exist behind license gates.
- [ ] Base/instruct reference numbers replace the placeholders in the benchmark table.
- [ ] LoRA, QLoRA, distilled, and +RAG comparisons are reported with confidence intervals.
- [ ] Grounded-QA token F1 and the grounding proxy are reported.
- [ ] Every published result is promoted to results/ with raw predictions, configuration, and hardware metadata.

## G4 — Practical local deployment

Advances [roadmap Phase 3](docs/roadmap.md#phase-3--autocomplete) and
[roadmap Phase 5](docs/roadmap.md#phase-5--quantization-and-cpu-deployment).

**Success:** fast, offline, non-executing assistance on ordinary laptops.

- [x] Local CPU/GPU inference engine with streaming is implemented.
- [x] OpenAI-compatible API with optional bearer-token auth is implemented.
- [x] FIM/prefix autocomplete engine and local API are implemented.
- [x] Dependency-free BM25 retrieval and citation-bearing RAG are implemented.
- [ ] GGUF export and llama.cpp inference are validated for Qwen3.5.
- [ ] A CPU-only latency and memory profile is published for representative laptops.
- [ ] Quality-regression thresholds for quantized deployment are defined and enforced.
- [ ] An editor integration reference client ships with acceptance-rate measurement.

## G5 — Distillation and retrieval

Advances [roadmap Phase 4](docs/roadmap.md#phase-4--distillation-and-retrieval).

**Success:** evidence that distillation and retrieval beat plain supervised
fine-tuning at matched compute, or a documented negative result.

- [x] Offline distillation pipeline is implemented.
- [ ] A teacher-generated corpus is produced at pilot scale with license review.
- [ ] The distilled student is compared with the supervised student at matched compute.
- [ ] RAG ablations cover top-k, citation requirement, and evidence ordering.
- [ ] The grounding proxy and human review of factual claims are reported.

## G6 — Publication and release

Advances [roadmap Phase 6](docs/roadmap.md#phase-6--publication).

**Success:** a reviewable research release where every placeholder is replaced
by a measurement or an explicit limitation.

The compute request that unblocks the training matrix is in
[FUNDING.md](FUNDING.md); the GPU validation protocol is in
[docs/gpu-bringup.md](docs/gpu-bringup.md).

- [x] Paper scaffold, model card, dataset card, and reproducibility docs exist with explicit placeholders.
- [ ] Hypotheses and the analysis plan are pre-registered.
- [ ] Dataset and evaluation versions are frozen for the paper.
- [ ] Every paper placeholder is replaced with a reviewed measurement.
- [ ] A reproducibility archive (manifests, configs, hardware metadata) is released.
- [ ] Independent review and responsible-disclosure checks are complete.

## Non-goals

Autonomous exploitation or command execution, unlicensed benchmark
redistribution, production-readiness claims from smoke tests, and leaderboard
scores without raw predictions. See
[docs/roadmap.md](docs/roadmap.md#non-goals).

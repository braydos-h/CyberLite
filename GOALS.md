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
- [x] Config-driven multi-source ingestion supports per-source paths and limits, explicit include/exclude, archive and NVD API acquisition, a local cache, and offline rebuilding.
- [x] A CPU-only audit utility produces JSON and Markdown reports, token-length percentiles, file hashes, and a deterministic stratified review sample with a human-review template.
- [x] A licensed, versioned pilot corpus (ATT&CK, CWE, NVD, OWASP, Linux/networking docs, and project-authored examples) is published as a manifest.

  Expanded pilot `pilot-v2` (dataset version
  `cyberlite-data-2.0.0-04b01b437805`): 7,724 normalized inputs, 7,188 accepted
  records, 536 rejected (417 near-duplicates, 119 quality), split 6,351 / 416 /
  421 across train / validation / test. The frozen manifest, quality,
  contamination, license, and audit reports are committed under
  [`data/manifests/pilot-v2/`](data/manifests/pilot-v2/). The original
  ATT&CK + CWE slice remains frozen under
  [`data/manifests/pilot-attack-cwe-v1/`](data/manifests/pilot-attack-cwe-v1/).
- [x] A deterministic synthesis pipeline expands the corpus from committed knowledge packs and the frozen pilot training split, with per-record provenance, grouping, exact/SimHash/MinHash deduplication, contamination screening, token gating, and staged manifests.

  `scripts/synthesize_dataset.py` builds calibration and production corpora
  from `data/synthesis/knowledge/` (439 curated facts), a source-grounded
  derivation layer, and a detection-rule teaching library. The pipeline
  never uses validation, test, or evaluation material as generation seeds.
  The expansion build screened 277,950 per-file n-grams across six local
  evaluation files; the pilot-v2 figure above (241,515) covers its earlier
  three-file screen and remains accurate for that frozen build.
- [x] Held-out evaluation sets are authored independently of the training packs and frozen with SHA-256 metadata.

  Three 55-item sets cover factual/knowledge, vulnerability/secure code, and
  logs/incident response/false positives/uncertainty/retention. They live in
  `data/evaluation/cyberlite_eval_*_v1.jsonl` and are screened against every
  training build.
- [ ] Every synthetic record has an independent technical and quality review.

  The review ledger and rubric are implemented, and calibration samples have
  been reviewed by independent AI agents. Coverage is sampled, not complete;
  most accepted records remain `automated-screened`. No human review has been
  recorded.
- [x] The source-license report is published without redistributing restricted text.

  `license_report.json` and `license_report.md` record permitted uses,
  attribution, redistribution obligations, and unresolved questions for every
  observed license.
- [x] Training-time dataset integrity and license gates fail closed before model
  or GPU allocation.

  Production configs point at `data/processed/pilot-v2/` and verify the frozen
  manifest version `cyberlite-data-2.0.0-04b01b437805`, split counts
  6,351 / 416 / 421, SHA-256 hashes, schema, provenance, duplicate IDs,
  cross-split leakage, evaluation-only records, and local benchmark overlap.
  Missing, unknown, prohibited, evaluation-only, and unacknowledged unresolved
  licenses are rejected for both training and validation splits; smoke data uses
  an explicitly separate relaxed path. Verified by the integrity, licensing, and
  preflight tests; unresolved licensing and pending manual review still block
  research readiness.
- [x] Contamination is measured against each available held-out benchmark subset.

  The 13-gram screen indexed 241,515 n-grams from SecEval, the project baseline
  probe, and the smoke evaluation set, with zero removals. CyberSecEval is
  registered but not locally available; that remains an open benchmark-access
  blocker, not a measured zero.
- [ ] A stratified manual quality and safety review of the pilot corpus is complete.

  The auditor generated 200 deterministic stratified samples and a review
  template. **No human review has been recorded**, so this milestone stays open.

## G2 — Post-training on consumer hardware

Advances [roadmap Phase 2](docs/roadmap.md#phase-2--core-post-training-comparison).

**Success:** trained adapters with honest memory, time, and quality trade-offs
at 4–16 GB VRAM.

- [x] Architecture-aware Qwen3.5 loading is verified by a local load and a LoRA backward pass.
- [x] LoRA and 4-bit QLoRA SFT pipelines support config hashing, resumption, and memory logging.

  Resumption now also verifies the recorded experiment fingerprint and refuses a
  changed configuration.
- [x] A CPU-only training preflight validates data integrity, licenses, and the
  pinned base revision without downloading model weights.

  `python scripts/train.py --config configs/qlora.yaml --preflight` reports
  software and research readiness separately, supports JSON, and exits nonzero
  when mandatory checks fail or research blockers remain. Verified by the
  preflight test suite.
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

- [x] Frozen held-out evaluation sets exist for factual, vulnerability, secure-code, log, grounded-QA, incident-response, false-positive, configuration, uncertainty, and retention suites.

  The sets are evaluation-only and were authored by agents isolated from the
  training knowledge packs. They are not a validated public benchmark and no
  trained-model performance is claimed.
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

# Changelog

All notable changes to CyberLite are documented in this file. Entries are
required for every change, including documentation-only changes.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the package follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Research artifacts are versioned separately by dataset manifest and effective
configuration hashes, not by the package version.

Add new entries under `[Unreleased]`, newest first, using the categories
`Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`, and `Docs`.
Move entries into a versioned section only when a release is tagged.

## [Unreleased]

### Added

- E0 SecEval baseline of the untrained base model: `Qwen/Qwen3.5-0.8B` on the full 2,182-item set (CC BY-NC-SA 4.0, evaluation only), CPU fp32, official chat protocol, seed 42. Overall exact-set accuracy is **0.346** (95% CI 0.327–0.365), split into **0.591** on single-answer items (n=1,257) and **0.014** on multi-answer items (n=925). The snapshot records the pinned revision, conversion and prediction hashes, a per-topic breakdown, and the reproduce command; predictions stay git-ignored under the evaluation-only license.
- First licensed pilot dataset slice: ATT&CK + CWE, 2,102 records in, 2,006 out, 96 near-duplicates removed (0 exact), zero 13-gram contamination findings against 241,515 indexed evaluation n-grams, published as a committed manifest under `data/manifests/pilot-attack-cwe-v1/` with split hashes and license counts.
- `FUNDING.md` with a hardware-only three-tier request, bill of materials, deliverables, risks, single-maintainer capacity limits, and use-of-funds rules, so the GPU ask is reviewable instead of implied.
- `GOVERNANCE.md` covering decision-making, money handling, conflicts of interest, key-person risk, and the open legal-entity decision required before accepting funds.
- `docs/preregistration.md` fixes hypotheses, numeric success thresholds (including the FPR, quantization-parity, and safety gates), the statistical analysis plan, and stopping rules before any adapter is trained.
- `docs/compute-budget.md` documents the GPU-hour model, two budget scenarios, measured CPU evaluation cost, a hardware-only bill of materials, electricity, and a conditional 26B projection.
- `cyberlite/compute_budget.py`, `scripts/compute_budget.py`, `cyberlite-compute-budget`, and `make budget` estimate GPU-hours and cost from explicit assumptions, including a `--parameters-b` override for control models; 12 unit tests cover the arithmetic, report totals, Markdown rendering, and CLI.
- `docs/gpu-bringup.md` provides a four-hour CUDA checklist, acceptance criteria, stop rules, and a report template so "GPU-ready" becomes a measurement.
- `scripts/cuda_memory_fraction.py` runs any CLI under a CUDA allocator ceiling so one card can approximate the 6/8/12 GB classes; results are labeled emulated.
- Small baseline artifacts (`summary.json`, `predictions.jsonl`, `inference_benchmark.json`) are now committed under `results/baseline/`, so the hashes quoted in each snapshot can be verified from a clean clone. The SecEval snapshot commits only `summary.json`; its predictions stay local under the evaluation-only license.
- `results/bringup/` JSON and JSONL outputs are exempt from the experiment-output ignore rule so the bring-up protocol can be followed literally.
- `scripts/prepare_benchmarks.py` obtains the pinned SecEval revision only on explicit `--download`, converts it to the local evaluation schema, and writes the items to Git-ignored paths with license, revision, and SHA-256 metadata.
- The evaluation harness now supports multi-select MCQ scoring (exact set match), the upstream SecEval chat protocol (`--protocol seceval`, one-shot, five new tokens), and per-metadata grouped metrics (`--group-by topics`).
- `web/` can now be deployed with `npx wrangler pages deploy web --project-name cyberlite --branch main` (also `make deploy-web`), with Cloudflare Pages `_headers`, `robots.txt`, `sitemap.xml`, and documented one-time login, project creation, and headless token setup.
- Static project website under `web/` with the research overview, verified model facts, hypotheses, progress snapshot, safety boundaries, and explicitly pending benchmark results.
- `data/evaluation/baseline_probe_v1.jsonl`, a 36-item project-authored capability probe (24 MCQ, 12 classification) with balanced, interleaved answer positions and labels.
- E0 capability and throughput snapshot for `Qwen/Qwen3.5-0.8B`: 23/24 MCQ, 0.50 classification accuracy with all items labelled `vulnerable` (FPR 1.0), 5.79–6.63 tokens/s and 1.12–2.59 s TTFT on CPU fp32, with the probe, predictions, and benchmark artifacts hash-pinned.
- E0 pre-training baseline snapshot of `Qwen/Qwen3.5-0.8B` on the smoke evaluation set, with run hashes, per-item predictions, and measured CPU latency/memory, so post-training conditions can be compared against a fixed starting point.
- `GOALS.md` with the north-star question and six goal groups (G1–G6) tracked as verifiable milestones.
- Live progress block and progress badge in `README.md`, generated from `GOALS.md` and `docs/roadmap.md`.
- `scripts/update_progress.py` with `--check` mode to detect a stale README block.
- `AGENTS.md` with working rules for contributors and AI agents, including the mandatory changelog and progress workflow.
- `CHANGELOG.md` (this file) as the single record of notable changes.

### Changed

- `FUNDING.md`, `GOVERNANCE.md`, `README.md`, and `docs/compute-budget.md` now state the single-maintainer, hardware-only scope explicitly; the budget does not assume cloud credits, rentals, salaries, contractors, or a second engineer, and Tier 2 is sized as a conditional scale check.
- `README.md` gains a Funding and compute section linking the ask, budget, bring-up protocol, pre-registration, and governance; the repository layout lists the new documents.
- `GOALS.md` links G3 to the pre-registration thresholds and G6 to the funding and bring-up documents.
- `docs/README.md` indexes the new compute, bring-up, and pre-registration pages.
- `scripts/validate_repo.py` now requires the funding, governance, pre-registration, budget, and bring-up documents, plus `GOALS.md`, `AGENTS.md`, `CHANGELOG.md`, and the progress script.
- `docs/reproducibility.md` and `results/README.md` note which small artifacts are committed and which remain ignored.
- `Makefile` gains `progress`, `progress-check`, and `budget` targets.
- CI now fails when the generated README progress block is out of date.
- `CONTRIBUTING.md` documents the changelog and progress requirements.
- `docs/README.md` and `docs/roadmap.md` link to the goals and changelog.

### Fixed

- Benchmark-contamination screening no longer silently skips evaluation files that use a benchmark schema (`question` / `choices` / `answer`); the index now reads every string value and records how many evaluation n-grams it covered, so a zero result is distinguishable from a skipped check.

### Security

- `.gitignore` now excludes `web/.taste-skill/`, which contains a real browser profile (history, cookies, login databases), and `.wrangler/`, preventing accidental publication of local browser state.

### Docs

- `README.md` documents the conditional scaling path from the 0.8B Qwen3.5 target to a 26B Inkling-2-mini follow-on, so the larger-model ambition is stated as a plan rather than left implied.
- Documented the planning estimates as estimates in every new page; no new measurement or benchmark claim is introduced.
- `docs/dataset.md` now lists what is committed (manifests, the project probe, and small baseline artifacts) instead of claiming only synthetic seed data is tracked.
- `docs/evaluation.md`, `benchmarks/seceval/README.md`, and `data/evaluation/README.md` document multi-select scoring, the SecEval protocol, the pinned revision, and the conversion hashes.
- `MODEL_CARD.md` now distinguishes the untrained base-model SecEval baseline from results for a trained CyberLite checkpoint.
- `web/README.md` now distinguishes the recommended Git-connected Cloudflare Pages setup from manual Wrangler uploads, and documents the `SKIP_DEPENDENCY_INSTALL` and `Authentication error [code: 10000]` pitfalls.
- `README.md` adds a Contact section with the maintainer's name, email, and project website.
- `README.md` documents the planned hardware path: CPU-first training and testing, followed by a funding request for a CUDA GPU to continue post-training at research scale.

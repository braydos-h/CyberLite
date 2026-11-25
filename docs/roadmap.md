# Roadmap

The roadmap is ordered by dependency, not by promised dates. A checked item
means the capability exists in the repository, not that a research claim has
been established.

## Phase 0 — Reproducible foundation (implemented)

- [x] Architecture-aware Qwen3.5 loading and compatibility documentation
- [x] Typed configuration, validation, effective-config hashing
- [x] Dataset schema, provenance, secret redaction, dedup, contamination screen
- [x] Deterministic splitting and manifest generation
- [x] LoRA/QLoRA SFT pipeline with checkpoint resumption and memory logging
- [x] Local inference engine, streaming, OpenAI-compatible API
- [x] FIM/prefix autocomplete engine and local API
- [x] BM25 retrieval and citation-aware RAG
- [x] Evaluation harness and metrics with explicit definitions
- [x] Unit tests, CI, paper scaffold with placeholders

## Phase 1 — Dataset pilot

- [ ] Curate a licensed, versioned pilot corpus from ATT&CK, CWE, NVD, OWASP,
      Linux/networking docs, and project-authored defensive workflows
- [ ] Manually review a stratified sample for quality, safety, and duplication
- [ ] Publish a manifest and source-license report without redistributing
      restricted data
- [ ] Measure contamination against the selected benchmark subsets

## Phase 2 — Core post-training comparison

- [ ] Base/instruct reference evaluation
- [ ] LoRA (bf16) and QLoRA (4-bit) at matched data and steps
- [ ] Rank/sequence-length ablations at 4, 8, 12, and 16 GB targets
- [ ] Peak VRAM, duration, throughput, and cost with explicit assumptions
- [ ] Catastrophic-forgetting and general-retention evaluation

## Phase 3 — Autocomplete

- [ ] Held-out completion benchmark across Bash, Python, PowerShell, YARA,
      Sigma, regex, BPF, and configuration files
- [ ] FIM vs prefix comparison; document checkpoint dependence
- [ ] Latency and acceptance study with a small authorized user group
- [ ] Editor integration reference client

## Phase 4 — Distillation and retrieval

- [ ] Offline teacher-generated corpus with review and license analysis
- [ ] Distilled student vs supervised student at matched compute
- [ ] RAG ablations: top-k, citation requirement, evidence ordering
- [ ] Grounding-proxy and human-review study for factual claims

## Phase 5 — Quantization and CPU deployment

- [ ] 4-bit/8-bit GPU parity study
- [ ] GGUF conversion and llama.cpp validation for Qwen3.5
- [ ] CPU-only latency/memory profile on representative laptops
- [ ] Quality regression thresholds for deployment

## Phase 6 — Publication

- [ ] Pre-register hypotheses and analysis plan
- [ ] Freeze dataset and evaluation versions
- [ ] Replace every paper placeholder with reviewed measurements
- [ ] Release model card, dataset card, and reproducibility archive
- [ ] Independent review and responsible-disclosure check

## Non-goals

- Autonomous exploitation or command execution
- Unlicensed benchmark redistribution
- Claims of production readiness from smoke tests
- A leaderboard score without raw predictions, configuration, and hardware

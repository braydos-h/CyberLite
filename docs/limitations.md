# Limitations

CyberLite is a research scaffold. The following limitations are first-class
findings, not footnotes.

## Status

- **No trained research checkpoint is released.** The bundled smoke adapter is
  an artifact of a two-step pipeline test and has no cybersecurity capability.
- **No benchmark result has been produced.** Tables in the README and paper are
  templates with blanks or explicit placeholders.
- No claim of state-of-the-art performance, safety, or production readiness is
  made.

## Model and architecture

- 0.8B parameters impose a hard capacity limit on broad security knowledge,
  multi-step reasoning, and long-context analysis.
- Qwen3.5 is a hybrid linear/full-attention multimodal architecture. CyberLite
  uses text only and depends on a recent Transformers release for correct
  loading. Architecture support can change between library versions.
- Optional accelerated kernels (`causal-conv1d`, `flash-linear-attention`) may
  not be installed; the reference path is slower.
- The base checkpoint's fill-in-the-middle training status is unknown. Token
  presence is not evidence of FIM quality.
- Knowledge is frozen at the checkpoint's training cutoff. Security facts,
  versions, and mitigations change.

## Data

- Licenses differ, and some sources (e.g., SecEval) are evaluation-only or
  non-commercial. Legal review is the user's responsibility.
- Derived data may inherit attribution or share-alike obligations. The manifest
  records licenses but cannot resolve legal questions.
- The lexical contamination screen catches verbatim overlap only. Paraphrased
  leakage and benchmark memorization may remain.
- Secret detection is best-effort and can miss credentials or flag benign code.
- Deduplication can drop legitimate templated examples; thresholds are
  documented and configurable.
- NVD and ATT&CK data contain descriptions of vulnerabilities and adversary
  behaviour. Defensive use does not remove dual-use concerns.
- Synthetic smoke examples are tiny, author-written, and not representative.

## Training

- LoRA and QLoRA results depend on rank, target modules, learning rate, data
  mix, sequence length, and stopping criteria. The provided configs are starting
  points, not tuned recipes.
- QLoRA's 4-bit quantization can change optimization dynamics; a QLoRA run is
  not an exact substitute for bf16 LoRA.
- Distillation is offline sequence-level generation, not logit matching. Teacher
  errors and licenses propagate. Teacher-generated data requires review.
- Catastrophic forgetting is expected under narrow fine-tuning; general
  capability retention must be measured, not assumed.
- Peak-memory estimates are conservative approximations. Measure per run.

## Evaluation

- MCQ accuracy measures test-taking behaviour as much as security knowledge.
- Exact match is harsh; token F1 is lexical. Neither measures correctness.
- `unsupported_token_rate` is a lexical grounding proxy, not a factual
  hallucination rate.
- Refusal and execution-claim rates use regexes and can misclassify.
- Python syntax validity is not functional correctness or security. Generated
  code is never executed by the harness.
- Benchmark subsets, prompt formats, and answer parsing affect scores. Report
  all three.
- Single-machine latency and memory numbers are not portable.

## Deployment

- The local API has a limited OpenAI-compatible surface and no tools, function
  calling, logprobs, or multi-choice sampling.
- `bitsandbytes` 4/8-bit loading in this pipeline requires CUDA. CPU deployment
  depends on GGUF/llama.cpp, whose Qwen3.5 support may lag.
- There is no sandbox for generated commands. The project intentionally refuses
  to execute them.
- Prompt injection through retrieved documents or source code is a live risk.
  The RAG prompt labels evidence as untrusted, but labels are not a guarantee.
- Model outputs can be confidently wrong. Human review is mandatory for any
  security decision.

## Research conduct

- Hypotheses must be pre-registered in the paper before results are inspected.
- Negative and null results must be reported.
- No benchmark number may be copied from a blog, leaderboard, or another model
  without reproduction.
- The paper's placeholders must be replaced only with reviewed measurements.

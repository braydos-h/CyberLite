# Evaluation methodology

## Scope

The harness is designed for local, reproducible evaluation of:

- cybersecurity knowledge (multiple choice),
- vulnerability/security classification,
- grounded or reference-based generation,
- secure code completion.

The harness does not download benchmarks, does not execute generated code, and
does not produce a single composite "cyber score" that hides task-specific
trade-offs. Benchmark data is obtained and converted by the separate, explicit
`scripts/prepare_benchmarks.py` step.

## Evaluation record schema

```json
{"id": "mcq-1", "task": "mcq", "question": "...", "choices": ["...", "..."], "answer": "A"}
{"id": "mcq-2", "task": "mcq", "question": "...", "choices": ["...", "...", "...", "..."], "answer": "AC"}
{"id": "cls-1", "task": "classification", "text": "...", "label": "vulnerable", "labels": ["benign", "vulnerable"]}
{"id": "gen-1", "task": "generation", "prompt": "...", "reference": "...", "evidence": "optional grounding text"}
{"id": "cmp-1", "task": "completion", "prefix": "def f():\n", "suffix": "\n", "reference": "    return 1", "language": "python"}
```

Answers can be an index, a letter, exact choice text, or a multi-select set such
as `"AC"` / `["A", "C"]`. Multi-select items are correct only when the predicted
set exactly equals the key. IDs must be unique. Malformed records fail with a
line number.

## Protocols

- **Chat-style models:** the system prompt identifies CyberLite as a defensive
  assistant; the user prompt asks for a concise answer. MCQ prompts ask for one
  letter, or the exact letter set when several choices are correct.
- **Base models:** use `--prompt-style raw` to avoid relying on instruction
  following. `auto` selects raw for model IDs ending in `-base`.
- **Decoding:** temperature 0 by default, fixed per-example seeds, no
  benchmark-specific prompt tuning. Record `max_new_tokens`.
- **Completion:** fill-in-the-middle when the tokenizer exposes the FIM control
  tokens; otherwise prefix completion. Python syntax is checked with `ast.parse`;
  code is never executed.
- **Retrieval:** the RAG condition retrieves from a versioned local BM25 index.
  Report `top_k`, index contents/hash, and whether citations are required.
- **SecEval:** `--protocol seceval` follows the upstream chat evaluation script:
  the official instruction, its single worked example, choices rendered as
  `A: ... B: ...`, `max_new_tokens=5`, temperature 0, and exact set match over the
  letters A–D. Use `--group-by topics` for the nine topic breakdown. This protocol
  is chat-only; multi-select items are never scored as correct by subset.

## Metrics

| Metric | Definition | Notes |
|---|---|---|
| MCQ accuracy | predicted set exactly equals the key set | bootstrap 95% CI (10,000 resamples, matching pre-registration) reported; single- and multi-answer subsets reported separately |
| Invalid rate | answer not parseable | reveals format-following failures |
| Classification accuracy | exact label match | task-specific |
| Macro F1 | unweighted mean per-label F1 | handles class imbalance |
| False-positive rate | predicted positive among true negatives | positive label configurable; only for binary labels |
| Exact match | normalized string equality | strict; report with token F1 |
| Token F1 | SQuAD-style token overlap | partial credit |
| Mean edit similarity | character-level similarity | code completion |
| Syntax-valid rate | Python `ast.parse` succeeds | no execution; non-Python returns null |
| Refusal rate | regex-detected refusal | a behaviour metric, not an error |
| Execution-claim rate | output claims a command was run | safety-relevant hallucination proxy |
| Unsupported token rate | answer tokens absent from evidence | **lexical grounding proxy, not truth** |
| Latency / throughput | wall-clock seconds; tokens/s | hardware-specific |
| Peak memory | CUDA counters and process RSS | measured, not estimated |
| Cost | explicit rate × measured duration | no default price |

The harness intentionally does **not** report a "hallucination rate" as if it
were measured factuality. `unsupported_token_rate` can over-penalize paraphrase
and under-detect confidently wrong statements. Use human review or a validated
judge for factual claims, and report the protocol.

## Benchmark licenses and access

| Benchmark | License / access | CyberLite behaviour |
|---|---|---|
| CyberSecEval / CyberSecEval 2 | Upstream Llama community terms; license-gated | No data bundled; local adapters only |
| SecEval | CC-BY-NC-SA; evaluation-only | No training use; no redistribution |
| Project held-out tasks | Synthetic/project-curated | Only the tiny smoke set is committed |

`python scripts/evaluate.py --list-benchmarks` prints the registry. Record the
upstream version/commit and access date for every published result.

## Reproducible run

```bash
python scripts/evaluate.py \
  --model Qwen/Qwen3.5-0.8B \
  --revision 2fc06364715b967f1860aea9cf38778875588b17 \
  --adapter runs/qlora \
  --dataset /path/to/heldout.jsonl \
  --out results/evaluation/qlora-heldout \
  --seed 42 \
  --temperature 0 \
  --prompt-style chat
```

Outputs:

- `summary.json` — metrics, model info (including requested, resolved, and
  tokenizer revision), dataset hash, environment, hardware, latency, memory,
  cost assumptions, limitations, and a run hash;
- `predictions.jsonl` — outputs, hashes, per-example scores, tokens, latency.

Predictions can contain benchmark-derived outputs; store them according to the
upstream license and your organization's policy.

## Baseline snapshots

Frozen reference runs live in [`results/baseline/`](../results/baseline/README.md).
They pair task metrics from `scripts/evaluate.py` with a separate throughput
protocol from `scripts/benchmark.py` (time to first token, tokens per second,
and peak memory at fixed prompt lengths).

Two kinds of snapshot exist:

- **Regression probes** use project-authored data (`baseline_probe_v1.jsonl`,
  `smoke_eval.jsonl`). They are small, synthetic, and not scientific benchmarks.
- **Real-benchmark baselines** use a locally obtained benchmark with its upstream
  protocol. `e0-instruct-seceval/` is the first: full SecEval (2,182 usable
  items), official chat prompt, exact set match. The items are not redistributed;
  the snapshot records the upstream revision, source and converted hashes, and
  the exact command.

The committed E0 SecEval snapshot was produced before the bootstrap default was
aligned with the pre-registration and therefore used 1,000 resamples. Its stored
point estimate and interval are left unchanged; new runs default to 10,000 and
record `bootstrap_resamples` in `summary.json`. Do not describe the old interval
as having used the new default.

Keep task quality and throughput separate. A single composite score would hide
the trade-off between knowledge accuracy, selective classification, generation
quality, and speed.

## Reporting checklist

- [ ] Model/checkpoint revision and adapter hash
- [ ] Base vs instruct distinction
- [ ] Dataset name, version, license, subset selection, access date
- [ ] Split and contamination method
- [ ] Prompt template and prompt style
- [ ] Decoding parameters and seeds
- [ ] Number of examples and per-task counts
- [ ] Accuracy with confidence interval
- [ ] For SecEval: single- vs multi-answer subsets and per-topic breakdown
- [ ] False-positive rate for classification tasks
- [ ] Grounding proxy with explicit interpretation limits
- [ ] Peak training and inference memory, measured
- [ ] Latency and throughput with hardware/software versions
- [ ] Cost only with explicit rates
- [ ] Limitations and negative results

No result should be copied into the paper or README until it satisfies this
checklist.

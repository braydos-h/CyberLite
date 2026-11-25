# Evaluation methodology

## Scope

The harness is designed for local, reproducible evaluation of:

- cybersecurity knowledge (multiple choice),
- vulnerability/security classification,
- grounded or reference-based generation,
- secure code completion.

It does not download benchmarks, does not execute generated code, and does not
produce a single composite "cyber score" that hides task-specific trade-offs.

## Evaluation record schema

```json
{"id": "mcq-1", "task": "mcq", "question": "...", "choices": ["...", "..."], "answer": "A"}
{"id": "cls-1", "task": "classification", "text": "...", "label": "vulnerable", "labels": ["benign", "vulnerable"]}
{"id": "gen-1", "task": "generation", "prompt": "...", "reference": "...", "evidence": "optional grounding text"}
{"id": "cmp-1", "task": "completion", "prefix": "def f():\n", "suffix": "\n", "reference": "    return 1", "language": "python"}
```

Answers can be an index, a letter, or exact choice text. IDs must be unique.
Malformed records fail with a line number.

## Protocols

- **Chat-style models:** the system prompt identifies CyberLite as a defensive
  assistant; the user prompt asks for a concise answer. MCQ prompts ask for the
  letter only.
- **Base models:** use `--prompt-style raw` to avoid relying on instruction
  following. `auto` selects raw for model IDs ending in `-base`.
- **Decoding:** temperature 0 by default, fixed per-example seeds, no
  benchmark-specific prompt tuning. Record `max_new_tokens`.
- **Completion:** the autocomplete engine uses FIM when available; otherwise
  prefix completion. Python syntax is checked with `ast.parse`; code is never
  executed.
- **Retrieval:** the RAG condition retrieves from a versioned local BM25 index.
  Report `top_k`, index contents/hash, and whether citations are required.

## Metrics

| Metric | Definition | Notes |
|---|---|---|
| MCQ accuracy | parsed letter equals key | bootstrap 95% CI reported |
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
  --adapter runs/qlora \
  --dataset /path/to/heldout.jsonl \
  --out results/evaluation/qlora-heldout \
  --seed 42 \
  --temperature 0 \
  --prompt-style chat
```

Outputs:

- `summary.json` — metrics, model info, dataset hash, environment, hardware,
  latency, memory, cost assumptions, limitations, and a run hash;
- `predictions.jsonl` — outputs, hashes, per-example scores, tokens, latency.

Predictions can contain benchmark-derived outputs; store them according to the
upstream license and your organization's policy.

## Reporting checklist

- [ ] Model/checkpoint revision and adapter hash
- [ ] Base vs instruct distinction
- [ ] Dataset name, version, license, subset selection, access date
- [ ] Split and contamination method
- [ ] Prompt template and prompt style
- [ ] Decoding parameters and seeds
- [ ] Number of examples and per-task counts
- [ ] Accuracy with confidence interval
- [ ] False-positive rate for classification tasks
- [ ] Grounding proxy with explicit interpretation limits
- [ ] Peak training and inference memory, measured
- [ ] Latency and throughput with hardware/software versions
- [ ] Cost only with explicit rates
- [ ] Limitations and negative results

No result should be copied into the paper or README until it satisfies this
checklist.

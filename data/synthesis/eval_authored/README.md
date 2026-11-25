# Held-out evaluation sets authored independently

These JSONL files were written by evaluation authors who were explicitly told
not to read the training knowledge packs or the generated corpus. They use the
schema in `data/synthesis/eval/_schema.json` and are validated by
`scripts/validate_evaluation.py`.

| File | Items | Suites |
|---|---:|---|
| `e1-factual-knowledge.jsonl` | 55 | factual, knowledge (single and multi-answer), uncertainty |
| `e2-vulnerability-secure-code.jsonl` | 55 | vulnerability, secure code/FIM, configuration, false positive |
| `e3-logs-incident-retention.jsonl` | 55 | logs, grounded QA, incident response, false positive, retention |

The canonical frozen copies live in `data/evaluation/cyberlite_eval_*_v1.jsonl`
with SHA-256 metadata. These authoring copies are kept for provenance and must
not be edited after a model comparison; a change requires a new versioned file.

Evaluation-only. Never use these items as training data or generation seeds.

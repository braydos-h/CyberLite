# SecEval (local, evaluation-only)

[SecEval](https://xuanwuai.github.io/SecEval) is a 2,189-item, four-choice
cybersecurity knowledge benchmark. It is **CC BY-NC-SA 4.0**, evaluation-only:

- do **not** use SecEval items for training,
- do **not** redistribute the items,
- report the upstream revision, access date, and license with any result.

CyberLite never bundles the items. This directory holds only this note in Git.

## Obtain and convert

```bash
# Explicit download of the pinned upstream revision, then conversion.
python scripts/prepare_benchmarks.py --download --force
```

| Artifact | Path | Git |
|---|---|---|
| Upstream questions | `benchmarks/seceval/questions.json` | ignored |
| Converted evaluation JSONL | `data/evaluation/seceval_v1.jsonl` | ignored |
| Conversion metadata | `data/evaluation/seceval_v1.meta.json` | ignored |

Pinned upstream revision:
`205dab7b0888a06f4b53ca7d9c7093e1326683e1`
(`XuanwuAI/SecEval`, accessed 2026-11-25).

| Hash | Value |
|---|---|
| Upstream `questions.json` SHA-256 | `194c3a511104be422a678675a71d44315d0c0392b040745155aeebc321e692e0` |
| Converted JSONL SHA-256 | `6ae74b2c9c45d1024f99453be00ae82d00567f0b5f1ffa1cc4109a2fa4ef1c03` |
| Harness dataset hash | `c3bd9a852924da17a05fefc954d60032f4a146a86861ad4cd40ec0350233064b` |

Conversion keeps 2,182 usable items: seven upstream items have an empty answer
key and are dropped. 1,257 items have one correct choice and 925 have two to
four. Multi-answer items are scored by exact set match, following the upstream
evaluation script.

## Protocol

`--protocol seceval` reproduces the upstream chat protocol: the official
instruction, the single worked example from `eval/eval.py`, the choices in
`A: ... B: ...` form, `max_new_tokens=5`, temperature 0, and exact set match over
the letters `A`–`D`. See [`docs/evaluation.md`](../../docs/evaluation.md).

```bash
python scripts/evaluate.py \
  --model Qwen/Qwen3.5-0.8B \
  --dataset data/evaluation/seceval_v1.jsonl \
  --out results/baseline/e0-instruct-seceval \
  --device cpu --prompt-style auto \
  --protocol seceval --group-by topics \
  --seed 42 --temperature 0 --max-new-tokens 5
```

The converted file lives under `data/evaluation/`, so the training preparation
pipeline's contamination screen includes it automatically.

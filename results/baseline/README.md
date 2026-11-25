# Baseline snapshots

Frozen measurements of the starting point, kept so later conditions can be
compared against a fixed reference instead of a reconstructed one.

| Snapshot | Condition | Data | Status |
|---|---|---|---|
| [`e0-instruct-smoke/`](e0-instruct-smoke/README.md) | Qwen3.5-0.8B instruct, no adapter, CPU fp32 | `data/evaluation/smoke_eval.jsonl` (8 synthetic items) | Measured 2026-11-25 |

These snapshots are **pipeline baselines**. The smoke set is not a scientific
benchmark, so the numbers are suitable for checking that a later run, dataset,
or adapter is wired correctly and for detecting gross regressions. They are not
suitable for publication or for claims about cybersecurity capability.

Raw `summary.json` and `predictions.jsonl` are retained locally but ignored by
Git under the repository's experiment-output policy. Each snapshot directory
records their hashes so they can be verified.

For publication-grade baselines, use a locally obtained, license-compliant
benchmark subset placed under `benchmarks/` or `data/evaluation/` with a
`SOURCE.md`, and follow the reporting checklist in
[`docs/evaluation.md`](../../docs/evaluation.md).

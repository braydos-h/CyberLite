# Baseline snapshots

Frozen measurements of the starting point, kept so later conditions can be
compared against a fixed reference instead of a reconstructed one.

| Snapshot | Condition | Data | Measures | Status |
|---|---|---|---|---|
| [`e0-instruct-probe/`](e0-instruct-probe/README.md) | Qwen3.5-0.8B instruct, no adapter, CPU fp32 | `data/evaluation/baseline_probe_v1.jsonl` (36 project-authored items) | MCQ accuracy, classification F1/FPR, TPS, TTFT, peak memory | Measured 2026-11-25 |
| [`e0-instruct-smoke/`](e0-instruct-smoke/README.md) | Qwen3.5-0.8B instruct, no adapter, CPU fp32 | `data/evaluation/smoke_eval.jsonl` (8 synthetic items) | End-to-end task coverage and harness validation | Measured 2026-11-25 |
| [`e0-instruct-seceval/`](e0-instruct-seceval/README.md) | Qwen3.5-0.8B instruct, no adapter, CPU fp32 | `data/evaluation/seceval_v1.jsonl` (2,182 items, CC BY-NC-SA, evaluation only) | MCQ exact-set accuracy, single vs multi-answer split, per-topic accuracy, latency | Measured 2026-11-25 |

Two kinds of snapshot are kept here:

- `e0-instruct-probe/` and `e0-instruct-smoke/` use project-authored data. They
  are **pipeline and regression baselines**, suitable for checking that a later
  run, dataset, or adapter is wired correctly, not for publication or capability
  claims.
- `e0-instruct-seceval/` uses the real, evaluation-only SecEval benchmark with
  its upstream protocol. It is the defensible "before" measurement: later
  adapters can be compared against the same items, prompt, and scoring rule.

The probe reports task-specific quality and throughput separately. It does not
compute a composite "smartness" score, because knowledge accuracy, selective
labeling, and generation quality can move in different directions.

The project-authored snapshots commit `summary.json` and `predictions.jsonl` so
their hashes can be verified from a clean clone. The SecEval snapshot commits
only `summary.json`; its `predictions.jsonl` stays local because SecEval is
CC BY-NC-SA and the repository does not redistribute benchmark-derived outputs.
Bulk run output remains git-ignored under the repository's experiment-output
policy.

The SecEval snapshot is the first publication-grade baseline. To add another,
use a locally obtained, license-compliant benchmark subset under `benchmarks/`
or `data/evaluation/` with source metadata, and follow the reporting checklist in
[`docs/evaluation.md`](../../docs/evaluation.md).

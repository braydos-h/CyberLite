# Results

**There are no verified results for a trained CyberLite checkpoint yet.** One
untrained base-model baseline exists in
[`baseline/e0-instruct-seceval/`](baseline/e0-instruct-seceval/README.md): the
full SecEval evaluation set, run before any adapter training. It is the
starting point, not a CyberLite result.

This directory is reserved for reviewed result artifacts produced by
`scripts/evaluate.py` and `scripts/benchmark.py`. Committed summaries must
include:

- the model/checkpoint identifier and adapter hash,
- evaluation set version and license,
- the exact configuration and Git commit,
- hardware, software versions, seeds, and decoding settings,
- raw predictions or a hash-addressed archive,
- a clear statement distinguishing measured values from planning estimates.

Planned tables live in the paper as explicit placeholders. They are not results.

Small baseline artifacts (`summary.json`, `predictions.jsonl`, and the inference
benchmark) are committed under `results/baseline/` so a clean clone can verify
the hashes quoted in each snapshot's README. Everything else under `results/` is
git-ignored until it is reviewed and promoted the same way.

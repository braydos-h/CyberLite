# Benchmark adapters and local data

CyberLite does not bundle CyberSecEval, SecEval, or other third-party benchmark
data. Licenses differ and some are gated or non-commercial.

- `cyberseceval/` — place locally obtained, license-compliant extracts here.
- `seceval/` — place locally obtained SecEval data here (evaluation only).
- `heldout/` — project-authored held-out tasks in the CyberLite JSONL schema.

Convert external data to the CyberLite evaluation schema described in
`docs/evaluation.md`. Record the upstream version/commit and license in a
`SOURCE.md` next to the data. Never use benchmark test items for training.

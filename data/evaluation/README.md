# Held-out evaluation data (not redistributed)

This directory is for locally obtained benchmark subsets and project-authored
held-out tasks in the CyberLite JSONL evaluation schema. Do **not** place
benchmark items here if their license forbids redistribution, and do not commit
them.

The preparation pipeline checks training records against every `*.jsonl` file
in this directory using 13-gram overlap and removes matches above the configured
threshold. This is a lexical screen, not proof that contamination is absent.

Bundled files:

- `smoke_eval.jsonl` — eight original synthetic items for validating the
  evaluation harness. These are not a scientific benchmark and must not be cited
  as one.
- `baseline_probe_v1.jsonl` — 36 original synthetic items (24 MCQ, 12
  vulnerability/benign classifications) for a small baseline capability probe.
  Answer positions and labels are balanced and interleaved. It is a regression
  signal, not a validated or standardized benchmark, and must not be cited as
  one.

Locally generated files (ignored by Git, never redistributed):

- `seceval_v1.jsonl` — 2,182 usable SecEval items converted by
  `scripts/prepare_benchmarks.py --download`. SecEval is CC BY-NC-SA 4.0 and
  evaluation-only. The generated file is in this directory on purpose: the
  preparation pipeline scans this directory, so future training data is screened
  against it. See `benchmarks/seceval/README.md`.

Benchmark metadata and access notes: `cyberlite/evaluation/benchmarks.py`.

# Reproducibility

## What is recorded

Every training run writes:

- `config.effective.yaml` — the exact merged configuration;
- `run_metadata.json` — config hash and resume fingerprint, requested and
  resolved model/tokenizer revision, model class and parameter counts, full
  dataset-integrity report, license-validation report, frozen manifest link,
  hardware, Python/packages, Git commit and dirty state, command;
- `training_metrics.json` — duration, steps, approximate tokens/second, peak
  VRAM/RSS, cost assumptions, and discarded/truncated tokenization counts;
- `trainer_log_history.json` — Trainer logs;
- adapter weights and tokenizer files.

Every evaluation run writes:

- `summary.json` — metrics, model info, dataset hash, environment, hardware,
  latency/memory, cost assumptions, limitations, and a run hash;
- `predictions.jsonl` — outputs, output hashes, scores, tokens, latency.

Small baseline and bring-up artifacts are committed so their quoted hashes can
be verified from a clean clone; bulk run output stays git-ignored.

Dataset preparation writes `manifest.json` with split hashes, dataset version,
source registry hash, license counts, deduplication and contamination stats.

## Determinism

Fixed seeds are set for Python, PyTorch, and Transformers. Matched experiments
also pin `Qwen/Qwen3.5-0.8B` to revision
`2fc06364715b967f1860aea9cf38778875588b17`, the checkpoint used for the E0
SecEval baseline. Model and tokenizer loading use the same revision, and run
metadata records both the requested and resolved commit. A deliberately
different checkpoint requires `model.matched_baseline: false`.

Determinism is still not guaranteed across:

- GPU models/drivers and CUDA/cuDNN versions,
- attention kernels and optional fused kernels,
- batch-size-dependent kernels and allocator behaviour,
- library upgrades.

For strict comparisons, use the same hardware and software image, temperature 0,
fixed prompt templates, and a single sequence per batch. Record deviations. The
repository reports what it can measure; it does not claim bitwise determinism.

## Environment capture

```bash
python -m pip freeze > environment.lock.txt
python scripts/check_hardware.py --json > hardware.json
git rev-parse HEAD
```

Attach these to a result archive. Do not commit environment locks containing
credentials or local paths.

## Training preflight (CPU only)

Run the preflight before any research training. It never downloads or loads model
weights, and it fails before GPU allocation when the dataset is not the frozen
build.

```bash
python scripts/train.py --config configs/qlora.yaml --preflight
python scripts/train.py --config configs/qlora.yaml --preflight --json
```

It checks configuration validity, dataset availability, the frozen manifest,
SHA-256 file hashes, dataset version and split counts, schema, required
provenance, duplicate IDs, cross-split leakage, evaluation-only records, local
13-gram contamination, training licenses, and the pinned model revision. It then
reports `software_ready` and `research_ready` separately.

Exit codes: `0` = research-ready; `1` = software checks pass but research
blockers remain; `2` = invalid configuration; `3` = mandatory software checks
failed. `--software-only` returns 0 when software checks pass, but it is not a
claim that research training is authorized. Pending manual review, external
pre-registration, and unresolved licensing remain blockers; the tool never marks
them complete.

Resuming requires the same config fingerprint as the original run. `config`
changes beyond `training.resume_from_checkpoint` are rejected, so a checkpoint
cannot be silently continued under a different experiment definition.

## Expanded pilot workflow (pilot-v2)

```bash
# First run: fetch pinned public inputs into data/cache and data/raw.
python scripts/prepare_dataset.py --config configs/dataset_pilot.yaml --force

# Offline rebuild from the same cache and pinned local files.
python scripts/prepare_dataset.py --config configs/dataset_pilot.yaml --offline --force

# Audit the produced splits and generate a deterministic review sample.
python scripts/audit_dataset.py \
  --dataset data/processed/pilot-v2 \
  --out data/manifests/pilot-v2/audit \
  --review-out data/processed/pilot-v2/review_samples.jsonl \
  --tokenizer Qwen/Qwen3.5-0.8B --max-seq-len 1024
```

The frozen manifest is `data/manifests/pilot-v2/manifest.json`. It records the
configuration SHA-256, source registry SHA-256, per-source revisions and input
hashes, split hashes, seed, pipeline version, quality/contamination/rejection
statistics, and the reproduction command. Identical pinned inputs and
configurations produce identical dataset content and split hashes. The timestamp
and report-generation time are not part of the dataset version.

NVD pages are cached one file per request under `data/cache/nvd/`; a rerun with
`--offline` reads only those cached pages and fails loudly if a required page is
missing. The cache and raw downloads are Git-ignored.

## Exact smoke workflow

```bash
python scripts/prepare_dataset.py --smoke
python scripts/train.py --config configs/smoke.yaml --smoke --force
python scripts/evaluate.py --dataset data/evaluation/smoke_eval.jsonl --dry-run
```

This validates the plumbing only. It does not measure model quality.

## Validation log (engineering only)

These checks were run during repository construction. They are **not**
benchmark results and should not be cited as model capabilities.

| Date | Check | Observation |
|---|---|---|
| 2026-11-25 | Qwen3.5-0.8B load on CPU | `Qwen3_5ForConditionalGeneration`, 852,985,920 parameters, 100,592,896 vision parameters |
| 2026-11-25 | LoRA backward pass, CPU | r=4, 2.71M trainable parameters, finite loss, gradients present |
| 2026-11-25 | Two-step smoke training | 26--29 s training after load, ~6.3 GiB peak RSS, adapter and metadata saved |
| 2026-11-25 | Adapter reload + generation | Adapter loaded; chat and FIM code paths executed on CPU |
| 2026-11-25 | Evaluation harness | Eight synthetic smoke items processed end to end; outputs kept outside the repository |
| 2026-11-25 | Pilot v1 build | ATT&CK + CWE: 2,102 records in, 2,006 out, 96 near-duplicates removed, 241,515 evaluation n-grams screened, zero 13-gram findings |
| 2026-11-25 | Pilot v2 build | Nine sources: 7,724 records in, 7,188 accepted, 536 rejected; 241,515 evaluation n-grams screened, zero 13-gram findings; Qwen3.5-0.8B tokenizer p50 373 / p95 798 / p99 1,539, max 3,474; 216 records over 1,024 tokens |
| 2026-11-25 | Pilot v2 audit | 200 deterministic stratified samples generated; no human review recorded; cross-split leakage and group violations zero |
| 2026-11-25 | SecEval baseline | Full 2,182 items, 59 min, 1.63 s/item, 34.65% accuracy (59.11% single-answer, 1.41% multi-answer), 5.45 GB peak RSS |
| 2026-11-25 | Test suite | Unit tests pass without downloading model weights |

Machine: 6-thread Intel i5-9500T, 15.4 GiB RAM, no GPU; PyTorch 2.15.0 CPU,
Transformers 5.24.1, PEFT 0.22.0, Python 3.12. These numbers are not portable.

## Promoting results

A result may be promoted from `runs/` or `results/` into the paper only when it
has:

1. a clean Git commit and config hash;
2. a dataset manifest and license record;
3. raw predictions;
4. complete hardware/software metadata;
5. a review note distinguishing measured values from estimates;
6. confirmation that no benchmark test item entered training.

Use a pull request with the summary, not a screenshot of a terminal.

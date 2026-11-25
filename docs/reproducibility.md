# Reproducibility

## What is recorded

Every training run writes:

- `config.effective.yaml` — the exact merged configuration;
- `run_metadata.json` — config hash, model class and parameter counts, dataset
  manifest link, hardware, Python/packages, Git commit and dirty state, command;
- `training_metrics.json` — duration, steps, approximate tokens/second, peak
  VRAM/RSS, cost assumptions;
- `trainer_log_history.json` — Trainer logs;
- adapter weights and tokenizer files.

Every evaluation run writes:

- `summary.json` — metrics, model info, dataset hash, environment, hardware,
  latency/memory, cost assumptions, limitations, and a run hash;
- `predictions.jsonl` — outputs, output hashes, scores, tokens, latency.

Dataset preparation writes `manifest.json` with split hashes, dataset version,
source registry hash, license counts, deduplication and contamination stats.

## Determinism

Fixed seeds are set for Python, PyTorch, and Transformers. Determinism is still
not guaranteed across:

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

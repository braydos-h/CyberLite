# GPU bring-up checklist

The purpose of this page is to turn "we are ready for a GPU" into a measured
fact in one short session. Run it the day the card arrives, before any long
training job. Budget **four hours**. If it cannot be completed in a day, that is
a finding: document where it stopped.

Do not start a long training job until every step below passes or has a written
exception.

> This is an engineering validation, not a research result. Its numbers go in
> `results/bringup/<date>/`, never in the benchmark table.

## 0. Record the environment first

```bash
nvidia-smi
python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())"
python -m pip freeze > environment.lock.txt
git rev-parse HEAD
python scripts/check_hardware.py --json > hardware.json
```

Record the GPU name, total VRAM, driver version, CUDA version, PyTorch build,
Transformers, PEFT, bitsandbytes, and whether the host is shared.

## 1. Install the CUDA stack

```bash
python -m pip install -e ".[dev]"
# Install the CUDA wheel that matches the driver; cu12x is the common case.
python -m pip install torch --index-url https://download.pytorch.org/whl/cu126
python -m pip install -r requirements-optional.txt
```

Optional accelerators for Qwen3.5's hybrid attention:

```bash
python -m pip install causal-conv1d flash-linear-attention
```

If either fails to build, skip it, keep the SDPA fallback, and record the
failure. Do not let a kernel build block the rest of the checklist.

**Pass:** `torch.cuda.is_available()` is `True`, `check_hardware.py` reports the
GPU, and the reported tier matches the card.

## 2. Planning estimate against the real device

```bash
python scripts/train.py --config configs/qlora.yaml --estimate-only --force
python scripts/train.py --config configs/lora.yaml --estimate-only --force
```

**Pass:** both write an estimate, and the 4-bit estimate is smaller than the
bf16 estimate. Note the gap between the estimate and what step 3 measures; that
gap is the planning error the repository keeps talking about.

## 3. Twenty-step QLoRA run

Prepare the tiny local split first (the training configs point at the full
corpus, which does not exist until the pilot is prepared):

```bash
python scripts/prepare_dataset.py --smoke
```

Then run 20 steps. Point the data paths at the smoke split:

```bash
python scripts/train.py \
  --config configs/qlora.yaml \
  --set data.train_file=data/processed/smoke/train.jsonl \
  --set data.validation_file=data/processed/smoke/validation.jsonl \
  --set training.max_steps=20 \
  --set run.output_dir=runs/bringup-qlora \
  --force
```

**Pass:** 20 optimizer steps complete; `training_metrics.json` contains
`peak_cuda_allocated_gb`, duration, and tokens/second; loss is finite.

Then repeat for bf16 LoRA:

```bash
python scripts/train.py \
  --config configs/lora.yaml \
  --set data.train_file=data/processed/smoke/train.jsonl \
  --set data.validation_file=data/processed/smoke/validation.jsonl \
  --set training.max_steps=20 \
  --set run.output_dir=runs/bringup-lora \
  --force
```

**If it OOMs,** reduce in this order and record each attempt: sequence length to
512, rank to 8, batch size to 1, gradient checkpointing on. Do not silently
lower the target; the point is to find the real boundary.

## 4. Inference throughput

```bash
mkdir -p results/bringup/$(date +%F)
python scripts/benchmark.py \
  --model Qwen/Qwen3.5-0.8B \
  --device cuda \
  --prompt-lengths 128,512,2048 \
  --max-new-tokens 64 \
  --runs 3 \
  --temperature 0 \
  --out results/bringup/$(date +%F)/inference_benchmark.json
```

**Pass:** a JSON file with TTFT, tokens/s, and peak memory for all three prompt
lengths. Compare only against the same host and software stack.

## 5. Adapter reload and generation

```bash
mkdir -p results/bringup/$(date +%F)
python scripts/evaluate.py \
  --model Qwen/Qwen3.5-0.8B \
  --adapter runs/bringup-qlora \
  --dataset data/evaluation/baseline_probe_v1.jsonl \
  --out results/bringup/$(date +%F)/e0-qlora-probe \
  --seed 42 --temperature 0 --device cuda --prompt-style auto
```

**Pass:** the adapter loads on CUDA, the run completes, and `summary.json`
records the adapter hash. The score is not a result; it is a regression check.

## 6. Memory-class boundaries

Use one card to approximate the smaller classes:

```bash
python scripts/cuda_memory_fraction.py --fraction 0.25 \
  scripts/train.py --config configs/qlora.yaml \
  --set data.train_file=data/processed/smoke/train.jsonl \
  --set data.validation_file=data/processed/smoke/validation.jsonl \
  --set training.max_steps=20 \
  --set run.output_dir=runs/bringup-6gb --force

python scripts/cuda_memory_fraction.py --fraction 0.33 \
  scripts/train.py --config configs/qlora.yaml \
  --set data.train_file=data/processed/smoke/train.jsonl \
  --set data.validation_file=data/processed/smoke/validation.jsonl \
  --set training.max_steps=20 \
  --set run.output_dir=runs/bringup-8gb --force
```

The fraction is relative to total device memory: 0.25 of 24 GB is ~6 GB, 0.33
is ~8 GB, 0.50 is ~12 GB. Record the first failure for each ceiling and label
the result **emulated**. Driver overhead, allocator fragmentation, and desktop
VRAM use are not reproduced; a deployment claim for an 8 GB laptop still needs a
real 8 GB card.

## 7. Write the report

Create `results/bringup/<date>/README.md`:

```markdown
# GPU bring-up — YYYY-MM-DD

| Field | Value |
|---|---|
| GPU / VRAM | |
| Driver / CUDA | |
| PyTorch / Transformers / PEFT / bitsandbytes | |
| Host / ownership | |
| Optional kernels | installed / skipped (reason) |

## Measured

| Measurement | bf16 LoRA | 4-bit QLoRA |
|---|---:|---:|
| Peak VRAM, 1,024 tokens (GB) | | |
| Seconds per optimizer step | | |
| Tokens/second (training) | | |
| TTFT, 512 prompt tokens (s) | | |
| Tokens/second (inference) | | |

## Emulated memory classes

| Ceiling | Result | First failure |
|---:|---|---|
| 6 GB (0.25) | | |
| 8 GB (0.33) | | |
| 12 GB (0.50) | | |

## What broke

## What the estimate got wrong

## Decision

Ready for the training matrix / blocked on …
```

Commit the report, the JSON artifacts, and the hashes. Update
[docs/compute-budget.md](compute-budget.md) with the measured throughput and
record the change in `CHANGELOG.md`.

## Acceptance criteria for "GPU-ready"

- [ ] CUDA is detected and the driver/CUDA versions are recorded.
- [ ] bf16 LoRA and 4-bit QLoRA both complete 20 steps.
- [ ] Peak VRAM is measured, not estimated, for both.
- [ ] Inference throughput is measured at three prompt lengths.
- [ ] An adapter reloads and generates on CUDA.
- [ ] At least two memory-class ceilings are characterized and labeled emulated.
- [ ] A committed bring-up report exists under `results/bringup/`.
- [ ] The compute budget uses the measured throughput, not the 30 TFLOP/s default.

## Stop rules

- If the CUDA stack cannot be made to work in four hours, stop and write the
  failure report. Do not keep swapping cards to debug the same error.
- If QLoRA OOMs at 4-bit, 512 tokens, rank 8, batch 1, the card is not the
  problem; the model/kernel path is. Report it.
- If the optional kernels fail, proceed with SDPA. Kernel builds are not on the
  critical path.
- Never run a long job on a borrowed or freshly built host without checkpointing
  and a known resume command. See [docs/reproducibility.md](reproducibility.md).

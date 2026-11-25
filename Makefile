.PHONY: install install-dev test lint format typecheck validate progress progress-check budget preflight smoke data audit synthesis-calibration synthesis-production synthesis-audit export paper deploy-web preview-web clean

install:
	python -m pip install -e .

install-dev:
	python -m pip install -e ".[dev]"

test:
	pytest -m "not integration"

lint:
	ruff check cyberlite scripts tests

format:
	ruff format cyberlite scripts tests

typecheck:
	mypy cyberlite

validate:
	python scripts/validate_repo.py

progress:
	python scripts/update_progress.py

progress-check:
	python scripts/update_progress.py --check

budget:
	python scripts/compute_budget.py \
		--config configs/lora.yaml \
		--config configs/qlora.yaml \
		--config configs/low_vram.yaml \
		--config configs/distillation.yaml \
		--train-tokens 30000000 --epochs 3 \
		--distill-tokens 10000000 --eval-conditions 8 \
		--effective-tflops 30 --gpu-hour-usd 0.60 --contingency 0.30 \
		--markdown

data:
	python scripts/prepare_dataset.py --smoke

audit:
	python scripts/audit_dataset.py \
		--dataset data/processed/pilot-v2 \
		--out data/manifests/pilot-v2/audit \
		--review-out data/processed/pilot-v2/review_samples.jsonl \
		--tokenizer Qwen/Qwen3.5-0.8B --max-seq-len 1024

synthesis-calibration:
	python scripts/synthesize_dataset.py --config configs/synthesis/calibration.yaml --force

synthesis-production:
	python scripts/synthesize_dataset.py --config configs/synthesis/production.yaml --force

synthesis-audit:
	python scripts/plan_mixture.py --splits-dir data/processed/synthesis-production --out data/manifests/synthesis-production/mix_plan.json

export:
	python scripts/export_dataset.py --splits-dir data/processed/synthesis-production --out data/processed/exports/production --force

preflight:
	python scripts/train.py --config configs/qlora.yaml --preflight

smoke:
	python scripts/train.py --config configs/smoke.yaml --smoke --force

paper:
	cd paper && latexmk -pdf main.tex

preview-web:
	npx --yes serve web

deploy-web:
	npx --yes wrangler@latest pages deploy web --project-name cyberlite --branch main

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage

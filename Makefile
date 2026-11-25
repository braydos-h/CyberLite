.PHONY: install install-dev test lint format typecheck validate progress progress-check budget smoke data paper deploy-web preview-web clean

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

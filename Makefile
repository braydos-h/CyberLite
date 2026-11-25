.PHONY: install install-dev test lint format typecheck validate progress progress-check smoke data paper clean

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

data:
	python scripts/prepare_dataset.py --smoke

smoke:
	python scripts/train.py --config configs/smoke.yaml --smoke --force

paper:
	cd paper && latexmk -pdf main.tex

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage

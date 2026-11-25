# Testing

## Default suite

```bash
pytest -m "not integration"
```

The default suite is network-free and does not download model weights. It covers:

- configuration validation and hashing,
- hardware detection and planning estimates,
- dataset schema, cleaning, deduplication, secret detection, splitting, and
  contamination,
- multi-source configuration, explicit include/exclude, per-source limits,
  archive caching, offline rebuilds, and deterministic manifests,
- mocked NVD pagination, retries, backoff, API-key headers, cache reuse, and
  malformed-page handling,
- Markdown directory ingestion, code-fence preservation, roff/mdoc and RFC
  parsing, and missing-SPDX quarantine,
- quality gates, PII/secret checks, token-length percentiles, cross-split
  leakage, per-benchmark contamination, and audit review sampling,
- tokenizer-facing SFT encoding with a fake tokenizer, including repeated
  user/assistant text, assistant-only masking, EOS preservation, truncation
  statistics, zero-supervision discards, and the drop policy,
- frozen-manifest integrity: file hashes, version and split counts, schema,
  provenance, duplicate IDs, cross-split leakage, evaluation-only records,
  benchmark contamination, processed-manifest mismatches, and the smoke
  pathway,
- training license enforcement for train and validation splits, including
  missing, unknown, disallowed, prohibited, evaluation-only, and unresolved
  licenses,
- model revision pinning and propagation,
- preflight success and failure, machine-readable JSON, exit
  codes, and resume fingerprint checks,
- metrics and uncertainty estimates,
- BM25 retrieval and RAG formatting,
- autocomplete prompt construction and safety flags,
- FastAPI endpoints with a fake engine,
- dry-run CLIs.

## Training preflight

The preflight tests are part of the default suite and are CPU-only:

```bash
pytest tests/test_dataset_integrity.py tests/test_training_licensing.py \
  tests/test_tokenization_safety.py tests/test_training_preflight.py \
  tests/test_checkpoint_resume.py tests/test_model_revision.py -q
```

Manual preflight against the locally built pilot:

```bash
python scripts/train.py --config configs/qlora.yaml --preflight
python scripts/train.py --config configs/qlora.yaml --preflight --json
```

Research configs are expected to exit nonzero until licensing, manual review, and
external pre-registration are resolved. Use `--software-only` only for
software-readiness checks; it does not create a research approval.

## Integration tests

```bash
CYBERLITE_RUN_INTEGRATION=1 pytest tests/integration -q
```

These download Qwen3.5-0.8B and verify:

- the architecture loads through the selected auto class,
- the tokenizer exposes FIM tokens,
- a LoRA forward/backward pass produces a finite loss,
- the adapter can be reloaded for generation.

They are skipped by default and may require several GB of RAM. A GPU is not
required, but CPU runtime is significant.

## Static checks

```bash
ruff check cyberlite scripts tests
ruff format --check cyberlite scripts tests
mypy cyberlite
python scripts/validate_repo.py
```

`validate_repo.py` checks required repository files, rejects common weight and
secret artifacts, and verifies that training configs and the dataset build
configuration load.

## CI

`.github/workflows/ci.yml` runs linting, type checking, repository validation,
the unit suite, and dataset smoke preparation on Python 3.11 and 3.12 with a
CPU-only PyTorch build. The paper workflow compiles the LaTeX scaffold.

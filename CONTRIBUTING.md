# Contributing to CyberLite

Thank you for helping build a more accessible cybersecurity research stack.
This project values reproducibility, safety, and clear evidence over claims.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -e ".[dev]"
```

## Before opening a pull request

```bash
ruff check cyberlite scripts tests
ruff format --check cyberlite scripts tests
mypy cyberlite
pytest -m "not integration"
python scripts/prepare_dataset.py --smoke
python scripts/validate_repo.py
make progress-check
```

If your change affects model loading, training, inference, or tokenization,
describe the architecture and library versions you tested. Do not claim a model
works because it imported once.

## Changelog and progress

Every change needs an entry under `[Unreleased]` in
[CHANGELOG.md](CHANGELOG.md). Documentation, CI, and dependency-only changes
are included.

Progress is tracked by the milestone checkboxes in [GOALS.md](GOALS.md) and the
phase checkboxes in [docs/roadmap.md](docs/roadmap.md). After editing either
file, regenerate the README block with `make progress`; `make progress-check`
must pass. Never hand-edit the generated region in `README.md`. The full
workflow is in [AGENTS.md](AGENTS.md).

## What we look for

- **Reproducibility:** fixed seeds, config hashes, dataset manifests, environment
  metadata.
- **Honest reporting:** placeholders for missing results; no invented numbers.
- **Safety:** no execution of generated commands; no automatic downloads of
  large datasets; clear warnings around untrusted content.
- **Licensing:** every data source and benchmark needs a verified license and
  provenance.
- **Tests:** network-free unit tests for new logic; integration tests marked
  `integration` and skipped by default.
- **Types and logging:** type hints, structured logging, fail-fast validation.
- **Minimal dependencies:** prefer the standard library and existing stack.

## Data contributions

Do not submit:

- model weights, checkpoints, or large datasets;
- credentials, private keys, tokens, or personal data;
- benchmark test items whose license forbids redistribution;
- content from unauthorized lab environments;
- copied proprietary documentation without permission.

Every new source must be added to `data/sources.yaml` with a license, homepage,
normalizer kind, and redistribution status. Derived text must retain attribution.
When in doubt, open an issue before preparing data.

## Research contributions

A result contribution must include:

- the exact configuration and Git commit;
- dataset version/manifest and license;
- hardware, software versions, seeds, and decoding settings;
- raw predictions or a hash-addressed archive;
- a clear distinction between measured values and planning estimates;
- negative results and limitations.

Results that cannot be reproduced will not be merged into the paper or README.

## Code style

- Python 3.11+, line length 100, Ruff formatting.
- Public functions and modules have docstrings.
- Avoid hidden global state; pass configuration explicitly.
- Raise actionable errors rather than silently falling back when a scientific
  setting is unsupported.
- Keep generated-command paths non-executing.

## Security

Do not report security vulnerabilities in public issues. See
[SECURITY.md](SECURITY.md). If a contribution could introduce an execution or
data-exfiltration path, call it out explicitly in the pull request.

## Licensing

By contributing, you agree that your contribution is licensed under the Apache
License 2.0, and that you have the right to submit it. Third-party code and data
must retain their licenses and be documented in `NOTICE` or the dataset card.

## Review

Maintainers may ask for a smaller reproduction, a license clarification, or a
correction to claims. This is normal: the goal is a repository that researchers
can trust.

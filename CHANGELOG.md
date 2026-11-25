# Changelog

All notable changes to CyberLite are documented in this file. Entries are
required for every change, including documentation-only changes.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the package follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Research artifacts are versioned separately by dataset manifest and effective
configuration hashes, not by the package version.

Add new entries under `[Unreleased]`, newest first, using the categories
`Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`, and `Docs`.
Move entries into a versioned section only when a release is tagged.

## [Unreleased]

### Added

- E0 pre-training baseline snapshot of `Qwen/Qwen3.5-0.8B` on the smoke evaluation set, with run hashes, per-item predictions, and measured CPU latency/memory, so post-training conditions can be compared against a fixed starting point.
- `GOALS.md` with the north-star question and six goal groups (G1–G6) tracked as verifiable milestones.
- Live progress block and progress badge in `README.md`, generated from `GOALS.md` and `docs/roadmap.md`.
- `scripts/update_progress.py` with `--check` mode to detect a stale README block.
- `AGENTS.md` with working rules for contributors and AI agents, including the mandatory changelog and progress workflow.
- `CHANGELOG.md` (this file) as the single record of notable changes.

### Docs

- `README.md` adds a Contact section with the maintainer's name, email, and project website.
- `README.md` documents the planned hardware path: CPU-first training and testing, followed by a funding request for a CUDA GPU to continue post-training at research scale.

### Changed

- `Makefile` gains `progress` and `progress-check` targets.
- CI now fails when the generated README progress block is out of date.
- `scripts/validate_repo.py` requires `GOALS.md`, `AGENTS.md`, `CHANGELOG.md`, and the progress script.
- `CONTRIBUTING.md` documents the changelog and progress requirements.
- `docs/README.md` and `docs/roadmap.md` link to the goals and changelog.

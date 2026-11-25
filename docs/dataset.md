# Dataset methodology

## Principles

1. **Provenance is mandatory.** Every record carries `source`, `license`, and
   usually `url`, `source_version`, and an upstream identifier.
2. **Acquisition is explicit.** The pipeline reads local files by default. It
   downloads only when `--download` is passed or a dataset configuration
   explicitly opts into pinned acquisition. `--offline` forbids network I/O.
3. **Licenses are checked.** Unknown licenses are quarantined. Per-document SPDX
   identifiers override a source-level default where the source is mixed.
4. **Benchmarks are separate.** Evaluation data is never mixed into training.
   A 13-gram lexical screen removes overlaps before splitting and records
   per-benchmark statistics.
5. **Secrets and personal data are screened.** Credential-like strings are
   redacted; high-confidence PII and unredacted secrets are rejected.
6. **Quality is global.** Cleaning, quality gates, deduplication, contamination
   screening, and splitting run once over the combined corpus, never per source.
7. **No bulk data in Git.** Only the tiny synthetic smoke set, project-authored
   examples, manifests, and text-free reports are committed.

## Record schema

JSON Lines, one object per line. Three task shapes are supported.

Chat SFT:

```json
{
  "id": "project-ir-001",
  "source": "project_examples",
  "license": "Synthetic",
  "task": "incident-response",
  "url": "https://github.com/braydos-h/CyberLite",
  "messages": [
    {"role": "user", "content": "What should the first hour of triage cover?"},
    {"role": "assistant", "content": "Preserve evidence before changing the system ..."}
  ],
  "metadata": {
    "group": "project_examples:ir-001",
    "source_version": "v1",
    "upstream_id": "project-ir-001",
    "review_status": "pending-human-review"
  }
}
```

Completion and fill-in-the-middle records use `prompt`/`response` or
`prefix`/`suffix`/`middle`. Chat records must end with an assistant turn.
Assistant tokens are supervised; system and user tokens are masked with `-100`.

`metadata.group` is the leakage-control unit. The pipeline falls back to the
document, CVE/CWE/ATT&CK/RFC identifier, then the content ID when a normalizer
does not set a group explicitly.

## Source registry and build configuration

Two files have different jobs:

- `data/sources.yaml` describes **what a source is**: title, kind, license,
  homepage, pinned URL, revision, redistribution status, attribution, and notes.
- `configs/dataset_pilot.yaml` describes **what a build consumes**: source
  inclusion/exclusion, local paths or pinned archive URLs, per-source limits,
  NVD date ranges, cache/output directories, quality thresholds, and split ratios.

Supported normalizers:

| Kind | Input | Derived records |
|---|---|---|
| `stix_attack` | MITRE ATT&CK STIX 2.1 bundle | technique and defensive-control explanations; revoked/deprecated objects skipped |
| `cwe_xml` | CWE XML or ZIP | weakness, mitigation, detection, consequences, relationships; deprecated/obsolete skipped |
| `nvd_json` | NVD API 2.0 page(s) | factual vulnerability summaries with CVSS, CWE, CPE, dates, references |
| `markdown` | file or recursive directory | heading-aware documentation sections with fenced code preserved |
| `manpage` / `roff` | roff or mdoc manual page | section-level administrative documentation with per-page SPDX license |
| `rfc_text` | plain-text IETF RFC | numbered section-level networking standards |
| `jsonl` | CyberLite schema | project-authored or external records as provided |

ZIP/TAR archives are cached, safely extracted, and normalized. A directory is
processed recursively in sorted order. Per-file errors are collected and
reported without discarding successful files from the same source.

### Enabled sources in the expanded pilot

| Source | Kind | License | Input |
|---|---|---|---|
| MITRE ATT&CK | `stix_attack` | `MITRE-ATTACK` | STIX bundle, pinned `v20.1` |
| MITRE CWE | `cwe_xml` | `MITRE-CWE` | CWE 5.0 XML/ZIP |
| NIST NVD | `nvd_json` | `Public-Domain` | API 2.0, 2024-01-01 to 2024-03-31 |
| OWASP Cheat Sheets | `markdown` | `CC-BY-SA-4.0` | pinned commit `05861f28…` |
| Linux man-pages | `manpage` | per-page SPDX (`Mixed-SPDX` default) | man-pages 6.9, explicit page allowlist |
| OpenSSH manual | `manpage` | `OpenSSH` | pinned `V_10_6_P2`, only `sshd_config(5)` and `ssh_config(5)` |
| nftables manual | `manpage` | `GPL-2.0-only` | nftables 1.1.1, `nft(8)` |
| IETF RFCs | `rfc_text` | `IETF-Trust` | ten pinned RFCs covering TLS, DNS, SSH, syslog, and addressing |
| Project examples | `jsonl` | `Synthetic` | original AI-assisted drafts, explicitly **not human-reviewed** |

Tool documentation with `See-source` licensing remains disabled and would be
quarantined. Missing or unrecognized licenses are rejected by the license gate.

### NVD collection

`cyberlite/data/nvd.py` implements API 2.0 collection with:

- publication-date ranges and automatic 120-day chunking;
- pagination and a per-range `state.json` for resumable downloads;
- request timeouts, retries, exponential backoff, and `Retry-After`;
- a configurable rate limit (conservative without an API key);
- optional `NVD_API_KEY` from the environment;
- one cache file per page with SHA-256 metadata;
- offline replay from cache;
- rejection of malformed pages and `Rejected` CVE entries.

Normalization uses only facts present in the NVD record. It does not add
remediation steps that the source does not state.

## Pipeline stages

```bash
# Legacy single-source path (unchanged)
python scripts/prepare_dataset.py --smoke
python scripts/prepare_dataset.py --download mitre_attack --out data/processed/attack
python scripts/prepare_dataset.py --source owasp_cheatsheets \
  --input /path/to/Cross_Site_Scripting_Prevention_Cheat_Sheet.md \
  --out data/processed/owasp

# Multi-source, configuration-driven build
python scripts/prepare_dataset.py --config configs/dataset_pilot.yaml --force

# Rebuild without network from the same cache and pinned local files
python scripts/prepare_dataset.py --config configs/dataset_pilot.yaml --offline --force

# Audit and generate a deterministic review sample
python scripts/audit_dataset.py \
  --dataset data/processed/pilot-v2 \
  --out data/manifests/pilot-v2/audit \
  --review-out data/processed/pilot-v2/review_samples.jsonl \
  --tokenizer Qwen/Qwen3.5-0.8B --max-seq-len 1024
```

Stages:

1. **Acquire** pinned inputs from local paths or the cache; download only when
   the config enables it.
2. **Normalize** each source into the common schema with provenance metadata.
3. **Clean** Unicode and line endings without destroying code indentation.
4. **Redact** private keys, cloud keys, tokens, JWTs, connection-string
   passwords, and contextual high-entropy blobs.
5. **Quality gate** for empty/short/long responses, repeated lines, boilerplate,
   link-heavy text, low information, PII, unredacted secrets, broken source
   metadata, and missing provenance. Absolute-claim wording is reported as a
   warning unless configured as a rejection.
6. **License gate** against the configured allowlist.
7. **Deduplicate globally** with exact normalized hashes plus banded 64-bit
   SimHash (default Hamming distance 3). Cross-source duplicates are counted.
8. **Screen contamination** with 13-gram hashes against every evaluation JSONL,
   with per-benchmark version, license, SHA-256, item, and n-gram counts.
9. **Split globally** with group-aware deterministic buckets (90/5/5 by default).
   All sections of a document or all views of a security identifier stay in one
   split. Exact and SimHash-near cross-split leakage is checked; colliding
   records are quarantined.
10. **Report** token-length percentiles with the Qwen tokenizer when available,
    truncation risk at 512/1024/2048/4096/8192 tokens, rejection reasons,
    license obligations, and file hashes.
11. **Write** splits, `quarantine.jsonl`, `manifest.json`, and text-free reports.

## Contamination limits

The 13-gram screen catches verbatim and near-verbatim leakage. It does **not**
catch paraphrase, translation, or conceptual overlap. Before publishing:

- exclude all benchmark test items from training;
- record benchmark versions and hashes;
- manually inspect high-overlap candidates;
- re-run the screen after any data change;
- state the limitation in the paper.

The expanded pilot screened 241,515 n-grams from SecEval (2,182 items), the
project baseline probe (36 items), and the smoke evaluation set (8 items) with
zero removals. CyberSecEval is registered but is not locally available; this is
an access blocker, not evidence of absence. Restricted benchmark content is not
committed.

## Auditing and manual review

`scripts/audit_dataset.py` is CPU-only and writes:

- `audit.json` and `audit.md`;
- `quality_report.json`, `contamination_report.json`, and `license_report.json`
  derived from the produced splits;
- `review_plan.json` with deterministic sample IDs and stratum counts;
- `review_template.md` with accuracy, relevance, completeness, provenance,
  safety, and overall-quality fields;
- `review_samples.jsonl` at the caller-specified local path, containing source
  text and therefore never committed.

The auditor never marks review complete. The expanded pilot's 200 samples have
**not** been reviewed; `manual_review.completed` remains `false`.

## Versioning and reproducibility

The expanded pilot is frozen under
[`data/manifests/pilot-v2/`](../data/manifests/pilot-v2/README.md). The manifest
records the dataset version, configuration hash, source registry hash, seed,
pipeline version, source revisions and file hashes, split hashes, quality and
contamination statistics, rejection reasons, and the exact reproduction command.
Identical pinned inputs and configurations produce identical dataset content and
split hashes; report timestamps are not part of the dataset version.

## Training-time integrity and license gate

Training does not trust the directory name or the processed manifest alone. The
preflight and `scripts/train.py` load `data/manifests/pilot-v2/manifest.json`,
require dataset version `cyberlite-data-2.0.0-04b01b437805` and split counts
6,351 / 416 / 421, and verify:

- SHA-256 and byte size for every split file;
- schema validity and required provenance (`source`, `license`, `task`, URL,
  source version, upstream identifier);
- duplicate record identifiers (within and across splits);
- exact/SimHash cross-split leakage;
- evaluation-only metadata, sources, licenses, and local benchmark overlap;
- the processed `manifest.json` beside the splits, when present, against the
  frozen manifest.

A mismatch is a hard failure. The pipeline never edits or regenerates a frozen
manifest to make a check pass; rebuild the dataset from pinned inputs instead.
Smoke data uses an explicitly separate, relaxed profile (no required upstream
provenance, no frozen dataset version, no contamination screen) and is never
treated as research-ready.

The training license policy is narrower than ingestion. Every record must carry a
license that is both explicitly allow-listed and reviewed for training.
Missing, unknown, prohibited, and evaluation-only licenses are rejected for both
train and validation splits. Licenses whose guidance still contains unresolved
questions are rejected unless a human names that exact license in
`data.allow_unresolved_licenses`; there is no blanket approval switch. The
pilot-v2 license report currently lists unresolved questions for several
licenses, so production configs intentionally do not acknowledge them and
research training remains blocked until a documented decision exists.

## Limits of this pilot

- 7,188 accepted records is a pilot, not a research-scale corpus.
- Manual review is pending; project-authored examples are AI-assisted drafts.
- NVD coverage is a three-month publication window, not the full database.
- OWASP and man-page coverage is limited by explicit allowlists and per-page
  licenses.
- The lexical contamination screen cannot detect paraphrase or conceptual
  overlap.
- Upstream documentation can be outdated or incorrect. Records preserve upstream
  claims; they are not independently verified.

## Distillation data

`scripts/generate_distillation_data.py` runs a local teacher and writes records
with `source: teacher-distillation` and `license: Synthetic`. The teacher model's
license may still constrain redistribution. Review the generated corpus, then:

```bash
python scripts/prepare_dataset.py \
  --source teacher-distillation \
  --input data/processed/distill_raw.jsonl \
  --out data/processed/distill
```

`configs/distillation.yaml` requires `data/processed/distill/manifest.json` and
the train/validation/test splits. It has no fallback to pilot-v2: missing teacher
data is an actionable failure, not a reason to train on a different corpus.

## What is committed

Only small, license-safe artifacts are committed:

- tiny, original synthetic examples under `data/seed/` and
  `data/evaluation/smoke_eval.jsonl`;
- the project-authored `data/evaluation/baseline_probe_v1.jsonl`;
- corpus manifests and reports under `data/manifests/`, which carry counts,
  hashes, licenses, and statistics but no source text;
- small baseline result artifacts under `results/baseline/`.

Bulk corpora, raw downloads, the acquisition cache, review samples, model
weights, credentials, and third-party benchmark items are ignored by Git.

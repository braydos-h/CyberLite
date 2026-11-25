# Dataset methodology

## Principles

1. **Provenance is mandatory.** Every record carries `source`, `license`, and
   optionally `url`.
2. **Nothing downloads by default.** The pipeline reads local files. Downloading
   requires an explicit `--download`.
3. **Licenses are checked.** Unknown licenses are quarantined; allowed licenses
   are recorded in the manifest.
4. **Benchmarks are separate.** Evaluation data is never mixed into training.
   A lexical contamination screen removes overlaps before splitting.
5. **Secrets are removed.** Credential-like strings are detected and redacted.
6. **No bulk data in Git.** Only the tiny synthetic smoke set is committed.

## Record schema

JSON Lines, one object per line. Three task shapes are supported.

Chat SFT:

```json
{
  "id": "optional-stable-id",
  "source": "mitre_attack",
  "license": "MITRE-ATTACK",
  "task": "attack-technique",
  "url": "https://attack.mitre.org/techniques/T1059/",
  "messages": [
    {"role": "user", "content": "How should a defender detect interpreter abuse?"},
    {"role": "assistant", "content": "Correlate process creation with ..."}
  ],
  "metadata": {"attack_id": "T1059"}
}
```

Completion:

```json
{
  "source": "cyberlite_smoke",
  "license": "Synthetic",
  "task": "secure-coding",
  "prompt": "Explain parameterized queries.",
  "response": "Parameterized queries separate SQL structure from data."
}
```

Fill-in-the-middle:

```json
{
  "source": "cyberlite_smoke",
  "license": "Synthetic",
  "task": "autocomplete-bash",
  "prefix": "grep -R \"failed password\" ",
  "suffix": " /var/log",
  "middle": "| awk '{print $1}'"
}
```

Chat records must end with an assistant turn. Assistant tokens are supervised;
system and user tokens are masked with `-100`.

## Source registry

`data/sources.yaml` defines source names, kinds, licenses, URLs, filenames, and
redistribution status. Supported normalizers:

| Kind | Input | Derived task |
|---|---|---|
| `stix_attack` | MITRE ATT&CK STIX 2.1 bundle | technique/control explanation |
| `cwe_xml` | CWE XML or ZIP | weakness, mitigation, detection |
| `nvd_json` | NVD API 2.0 page(s) | vulnerability summary with severity/CWE |
| `markdown` | file or directory | documentation explanations |
| `jsonl` | CyberLite schema | as provided |

ZIP archives are extracted to a temporary directory and normalized; Markdown
directories are processed file by file. Add new sources only with a verified
license and a documented normalizer.

### Licenses in the starter registry

| Source | Identifier | Notes |
|---|---|---|
| MITRE ATT&CK | `MITRE-ATTACK` | Royalty-free use with terms/attribution; not redistributed by CyberLite |
| MITRE CWE | `MITRE-CWE` | Free for research/development/commercial use with CWE terms |
| NIST NVD | `Public-Domain` | U.S. Government work; NVD requests attribution |
| OWASP Cheat Sheets | `CC-BY-SA-4.0` | Share-alike; review redistribution obligations |
| Linux documentation | `GPL-2.0-or-later` | Copyleft; training use and redistribution are distinct questions |
| IETF RFCs | `IETF-Trust` | IETF Trust legal provisions |
| Project-authored | `Synthetic` | Apache-2.0-compatible repository content |
| Tool docs | `See-source` | Quarantined until an explicit license is supplied |

This table is a research aid, not legal advice. Verify upstream terms and the
licenses of any model trained on derived data.

## Pipeline stages

```bash
# Tiny offline validation set
python scripts/prepare_dataset.py --smoke

# Explicit download of one source
python scripts/prepare_dataset.py --download mitre_attack --out data/processed/attack

# Normalize a local Markdown file under a registered source
python scripts/prepare_dataset.py \
  --source owasp_cheatsheets \
  --input /path/to/Cross_Site_Scripting_Prevention_Cheat_Sheet.md \
  --out data/processed/owasp
```

Stages:

1. **Normalize** source-specific formats into records.
2. **Clean** Unicode, line endings, trailing whitespace; preserve code
   indentation.
3. **Redact** private keys, cloud keys, tokens, JWTs, connection-string
   passwords, and contextually high-entropy blobs.
4. **Filter** by license, minimum length, and structural validity.
5. **Deduplicate** exact normalized hashes plus banded 64-bit SimHash with a
   conservative Hamming threshold (default 3 bits). Set threshold 0 for exact
   matching only.
6. **Screen contamination** using 13-gram hashes against every `*.jsonl` file in
   `data/evaluation/`. Records with ≥20% candidate n-gram overlap are removed.
7. **Split** deterministically by content ID: 90/5/5 by default, 75/12.5/12.5 for
   the smoke set. IDs are the leakage-control unit.
8. **Write** splits, `quarantine.jsonl`, and `manifest.json`.

The manifest includes input/output counts, source/task/license counts, dataset
version, SHA-256 of every split, cleaning and contamination statistics, and the
source registry hash. Identical inputs and options produce identical split
hashes and dataset versions.

## Contamination limits

The 13-gram screen catches verbatim and near-verbatim leakage. It does **not**
catch paraphrases, translations, or conceptual overlap. Before publishing:

- exclude all benchmark test items from training;
- record benchmark versions and access dates;
- manually inspect high-overlap candidates;
- run the screen again after any data change;
- state the limitation in the paper.

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

## What is committed

Only tiny, original synthetic examples under `data/seed/` and
`data/evaluation/smoke_eval.jsonl`. Bulk corpora, model weights, credentials, and
third-party benchmark items are ignored by Git.

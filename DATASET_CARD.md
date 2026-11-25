# CyberLite dataset card

## Dataset summary

CyberLite provides a **reproducible preparation pipeline**, not a redistributed
security corpus. The only committed examples are a tiny, original synthetic
smoke set used to validate the pipeline.

| Field | Value |
|---|---|
| Committed smoke set | 34 training corpus examples + 8 harness-validation evaluations + 36 baseline-probe evaluations |
| Language | English |
| Tasks | knowledge QA, attack techniques, weaknesses, vulnerabilities, hardening, secure coding, autocomplete |
| Licenses | `Synthetic` for committed examples; source-dependent for local corpora |
| Redistribution | Smoke set only; external sources are not redistributed |
| Dataset version | Content-addressed; see `data/processed/*/manifest.json` |
| Maintainer | CyberLite contributors |

## Motivation

The pipeline exists to make cybersecurity post-training data auditable:

- every record carries source and license metadata;
- cleaning and secret redaction are explicit;
- exact and near-duplicate removal is deterministic;
- benchmark contamination is screened before splitting;
- splits are content-addressed and reproducible;
- bulk data and restricted benchmarks stay out of Git.

## Composition

### Committed smoke set

`data/seed/smoke.jsonl` contains original, author-written examples covering:

- MITRE ATT&CK-style detection and triage;
- CWE-style weakness explanation and remediation;
- NVD-style vulnerability summaries;
- OWASP-style web security guidance;
- Linux, networking, and tool-operation defensive workflows;
- secure coding and secret handling;
- Bash, Python, PowerShell, YARA, Sigma, regex, BPF, and nginx FIM examples.

These examples are deliberately small and are **not** representative of the
domain. `data/evaluation/smoke_eval.jsonl` contains eight disjoint synthetic
items for harness validation. `data/evaluation/baseline_probe_v1.jsonl` contains
36 additional project-authored items (24 MCQ, 12 classification) for a small
capability probe with balanced answer positions and labels; it is a regression
baseline, not a validated benchmark.

### Planned external sources

| Source | Kind | License | Redistribution |
|---|---|---|---|
| MITRE ATT&CK | STIX 2.1 | MITRE terms with attribution | No |
| MITRE CWE | XML | MITRE CWE terms | No |
| NIST NVD | JSON API | Public domain / attribution requested | Generally yes; verify |
| OWASP Cheat Sheets | Markdown | CC-BY-SA-4.0 (project-specific) | Review share-alike |
| Linux man-pages / kernel docs | Markdown/text | GPL-2.0-or-later | Review copyleft |
| IETF RFCs | Text | IETF Trust | Review |
| Security tool documentation | Markdown | Varies (`See-source`) | Only with explicit license |
| Project-authored workflows | JSONL | Synthetic / Apache-2.0-compatible | Yes |
| Teacher distillation | JSONL | Synthetic, teacher-license dependent | Review |
| Authorized labs | JSONL | Synthetic | Yes, if no real target data |

The source registry is `data/sources.yaml`. Licenses must be verified at the time
of use; this table is not legal advice.

## Collection and processing

1. **Explicit acquisition.** The pipeline never downloads by default.
2. **Normalization.** STIX, CWE XML/ZIP, NVD JSON, Markdown, and JSONL adapters
   convert sources into a common schema with provenance.
3. **Cleaning.** Unicode normalization, line-ending normalization, whitespace
   cleanup that preserves code indentation.
4. **Secret handling.** Detection and redaction of private keys, cloud keys,
   tokens, JWTs, connection-string passwords, and contextual high-entropy blobs.
5. **License gate.** Unknown or disallowed licenses are quarantined.
6. **Deduplication.** Exact normalized hash plus banded 64-bit SimHash; default
   Hamming threshold 3. Threshold 0 means exact-only.
7. **Contamination screen.** 13-gram overlap against local evaluation JSONL;
   records at or above 20% overlap are removed.
8. **Splitting.** Deterministic content-ID hashing; 90/5/5 default, 75/12.5/12.5
   for the smoke set.
9. **Manifest.** Counts, hashes, dataset version, source registry hash, license
   counts, and rejection reasons.

## Personal and sensitive information

The pipeline targets public technical documentation. It does not intentionally
collect personal data. Secret detection is best-effort, and logs, code, and
security reports can still contain sensitive material. Do not ingest production
credentials, customer data, or unauthorized target data. Review samples and
quarantine output before training.

## Biases and gaps

- English-language and Linux/networking-centric.
- Overrepresents vulnerabilities and frameworks with public documentation.
- Underrepresents proprietary environments, legacy systems, and non-English
  operational practice.
- ATT&CK/CWE/NVD descriptions are not ground truth and may be outdated.
- LLM-generated or teacher-generated text can contain errors and stylistic bias.
- The smoke set is synthetic and tiny; it validates code paths, not coverage.
- MCQ benchmarks reward test-taking behaviour and may not reflect operational
  skill.

## Evaluation and contamination

Evaluation data is kept in `data/evaluation/` and is never mixed into training.
The lexical screen is necessary but insufficient: paraphrased leakage and
memorization may remain. Benchmark licenses differ; SecEval is evaluation-only
and non-commercial, and CyberSecEval is obtained under upstream terms. CyberLite
does not redistribute either.

## Distribution

- Code: Apache-2.0.
- Committed synthetic examples: intended for use with this repository; see
  `NOTICE`.
- External corpora: not distributed. Reproduce them from the source registry and
  manifest.
- Model weights: not distributed.

## Maintenance

- Dataset versions are content-addressed in manifests.
- Source URLs and licenses can change; re-verify before a new run.
- Report data-quality or safety issues through repository issues (not with
  sensitive data attached).
- Security issues follow `SECURITY.md`.

## Citation

Cite the repository using `CITATION.cff`. When publishing a derived dataset,
cite the upstream sources and record their versions, access dates, and licenses.

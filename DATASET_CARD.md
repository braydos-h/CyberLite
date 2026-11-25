# CyberLite dataset card

## Dataset summary

CyberLite provides a **reproducible preparation pipeline and frozen manifests**,
not a redistributed security corpus. Bulk source text and derived splits stay
outside Git; only small synthetic examples, manifests, and text-free reports are
committed.

| Field | Value |
|---|---|
| Frozen pilot | `pilot-v2`, dataset version `cyberlite-data-2.0.0-04b01b437805` |
| Pipeline version | `2.0.0` |
| Normalized inputs | 7,724 |
| Accepted records | 7,188 |
| Rejected / quarantined | 536 (417 near-duplicates, 119 quality) |
| Splits | train 6,351; validation 416; test 421 |
| Sources | ATT&CK, CWE, NVD, OWASP, Linux man-pages, OpenSSH, nftables, IETF RFCs, project-authored examples |
| Language | English |
| Licenses | Source-dependent; see the committed license report |
| Distribution | Manifests and reports only; external source text is not redistributed |
| Manual review | **Not completed** (200 samples generated, zero reviewed) |
| Maintainer | CyberLite contributors |

The original ATT&CK + CWE slice remains frozen under
[`data/manifests/pilot-attack-cwe-v1/`](../data/manifests/pilot-attack-cwe-v1/README.md):
2,102 records in, 2,006 out, with its own manifest and hashes.

## Motivation

The pipeline exists to make cybersecurity post-training data auditable:

- every record carries source, license, URL, version, and upstream identifiers;
- cleaning, secret redaction, and PII checks are explicit;
- exact and near-duplicate removal is deterministic and global;
- benchmark contamination is screened per benchmark before splitting;
- related sections are grouped so one document cannot straddle splits;
- splits and manifests are content-addressed and reproducible offline;
- bulk data and restricted benchmarks stay out of Git;
- manual review is never implied by an automated check.

## Composition

### Frozen `pilot-v2`

| Source | Accepted records | Task categories |
|---|---:|---|
| MITRE ATT&CK | 959 | attack-technique, defensive-control |
| MITRE CWE | 906 | weakness |
| NIST NVD | 2,615 | vulnerability |
| OWASP Cheat Sheet Series | 1,965 | documentation, secure-coding |
| Linux man-pages | 246 | permissions, networking, logging-monitoring, cryptography, system-administration |
| OpenSSH manual | 28 | system-hardening, ssh |
| nftables manual | 40 | system-hardening |
| IETF RFCs | 393 | tls, dns, ssh, logging-monitoring, networking |
| Project-authored examples | 36 | incident-response, vulnerability-remediation, secure-coding, detection-engineering, log-analysis, system-administration |
| **Total** | **7,188** | 19 task categories |

| License | Records |
|---|---:|
| `CC-BY-SA-4.0` | 1,967 |
| `Public-Domain` | 2,961 |
| `MITRE-ATTACK` | 977 |
| `MITRE-CWE` | 954 |
| `IETF-Trust` | 395 |
| `Linux-man-pages-copyleft` | 156 |
| `Linux-man-pages-1-para` | 67 |
| `OpenSSH` | 28 |
| `GPL-2.0-only` | 40 |
| `GPL-2.0-or-later` | 10 |
| `GPL-3.0-or-later` | 8 |
| `GPL-1.0-or-later` | 6 |
| `Synthetic` | 36 |

License counts are measured after cleaning and before global deduplication; the
accepted-record table is authoritative for final composition.

### Committed smoke set and project examples

`data/seed/smoke.jsonl` contains 34 original examples for pipeline validation.
`data/seed/project_examples_v1.jsonl` adds 36 original defensive examples across
six categories. They are **AI-assisted drafts**, labeled
`review_status: pending-human-review`, and must not be described as manually
verified.

`data/evaluation/smoke_eval.jsonl` contains eight disjoint synthetic items for
harness validation. `data/evaluation/baseline_probe_v1.jsonl` contains 36
project-authored capability-probe items. Neither is a validated benchmark.

## Collection and processing

1. **Explicit acquisition.** A build downloads only when `--download` is passed
   or the dataset configuration enables pinned acquisition. `--offline` forbids
   network I/O.
2. **Normalization.** STIX, CWE XML/ZIP, NVD JSON, Markdown, roff/mdoc, RFC text,
   and JSONL adapters preserve provenance and upstream identifiers.
3. **Cleaning.** Unicode and line-ending normalization; code indentation is
   preserved; fenced code blocks are never split at arbitrary character offsets.
4. **Secret and PII handling.** Redaction of private keys, cloud keys, tokens,
   JWTs, connection-string passwords, and contextual high-entropy blobs.
   High-confidence PII and unredacted secrets are rejected; organizational NVD
   contacts are excluded from the PII warning count.
5. **License gate.** Per-record licenses are checked against the configured
   allowlist. Man-pages without an explicit SPDX identifier are quarantined.
6. **Quality gate.** Empty/short/long responses, repeated lines, boilerplate,
   link-heavy text, low-information records, broken metadata, and missing
   provenance are rejected or reported.
7. **Deduplication.** Exact normalized hash plus banded 64-bit SimHash, default
   Hamming threshold 3. Duplicates are removed globally; cross-source duplicates
   are counted.
8. **Contamination screen.** 13-gram overlap against every local evaluation
   JSONL. Records at or above 20% overlap are removed. Per-benchmark versions,
   licenses, hashes, item counts, and n-gram counts are recorded.
9. **Splitting.** Deterministic group-aware hashing; 90/5/5 by default. Exact and
   near-duplicate cross-split leakage is checked and quarantined.
10. **Token reporting.** Qwen3.5-0.8B tokenizer percentiles and truncation risk at
    512/1024/2048/4096/8192 tokens. If the tokenizer is unavailable, a
    character-based estimate is labeled as estimated.
11. **Manifest and audit.** Split hashes, config/source hashes, quality,
    contamination, license, and audit reports are written without source text.

## Measured quality and leakage statistics

| Check | Result |
|---|---|
| Secret redactions applied | 8 |
| Exact duplicates removed | 0 |
| Near duplicates removed | 417 |
| Quality rejections | 119 (77 repeated lines, 28 PII, 14 link-heavy) |
| Cross-source duplicates removed | 0 |
| Evaluation n-grams indexed | 241,515 |
| Benchmarks screened | SecEval 2,182 items; baseline probe 36; smoke 8 |
| Contamination removals | 0 |
| Group split violations | 0 |
| Cross-split leakage findings | 0 |
| Missing provenance (accepted records) | 0 for URL, version, license, task, and upstream ID |

Token lengths with the real Qwen tokenizer (completion/chat text, no packing):

| Percentile | Tokens |
|---|---:|
| p50 | 373 |
| p90 | 616 |
| p95 | 798 |
| p99 | 1,539 |
| max | 3,474 |
| over 1,024 tokens | 216 records (3.01%) |

The 1,024-token threshold matches `configs/lora.yaml` and `configs/qlora.yaml`.
A high-overlap tail remains because some documentation sections contain large
code blocks that are intentionally preserved rather than cut mid-block. Training
must document truncation or packing behavior.

## Personal and sensitive information

The pipeline targets public technical documentation and project-authored
examples. It does not intentionally collect personal data. Secret and PII checks
are best-effort; logs, code, and security reports can still contain sensitive
material. NVD records include organizational CVSS source identifiers such as
`nvd@nist.gov`; these are not treated as personal contact data unless they appear
as ordinary email addresses. Do not ingest production credentials, customer
data, or unauthorized target data.

## Biases and gaps

- English-language and Linux/networking-centric.
- Overrepresents vulnerabilities and frameworks with public documentation.
- Underrepresents proprietary environments, legacy systems, and non-English
  operational practice.
- ATT&CK/CWE/NVD descriptions are not ground truth and may be outdated.
- OWASP and manual-page coverage is limited by explicit allowlists and licenses.
- NVD coverage is a three-month publication window, not the full database.
- Project-authored examples are AI-assisted and not human-reviewed.
- The smoke set is synthetic and tiny; it validates code paths, not coverage.
- MCQ benchmarks reward test-taking behaviour and may not reflect operational
  skill.

## Evaluation and contamination

Evaluation data is kept in `data/evaluation/` and is never mixed into training.
The lexical screen is necessary but insufficient: paraphrased leakage,
translation, and memorization may remain. Benchmark licenses differ; SecEval is
CC BY-NC-SA 4.0 and evaluation-only, and CyberSecEval is obtained under upstream
terms. CyberLite does not redistribute either. CyberSecEval is registered but not
locally available, so it is an open contamination-coverage blocker.

## Distribution

- Code: Apache-2.0.
- Committed synthetic examples: intended for use with this repository; see
  `NOTICE`.
- External corpora: not distributed. Reproduce them from the source registry,
  dataset configuration, and manifest hashes.
- Model weights: not distributed.

## Maintenance

- Dataset versions are content-addressed in manifests.
- Source URLs, revisions, and licenses can change; re-verify before a new run.
- Report data-quality or safety issues through repository issues (not with
  sensitive data attached).
- Security issues follow `SECURITY.md`.
- A new build must regenerate the manifest, quality, contamination, license, and
  audit reports; never edit a frozen manifest by hand.

## Citation

Cite the repository using `CITATION.cff`. When publishing a derived dataset,
cite the upstream sources and record their versions, access dates, and licenses.

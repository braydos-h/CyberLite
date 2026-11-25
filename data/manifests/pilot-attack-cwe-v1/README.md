# Pilot corpus v1 — ATT&CK + CWE

Frozen manifest for the first licensed CyberLite pilot slice. Generated
2026-11-25 with `cyberlite 0.1.0`, seed 42, and the repository source registry.

## Corpus

| Field | Value |
|---|---|
| Dataset version | `cyberlite-data-0.1.0-26c6d44ae6bc` |
| Source registry SHA-256 | `28c37b6f8c2478358673b5e9cb74c917326b2bf0b8f50757356861231a528c32` |
| Input records | 2,102 |
| Output records | 2,006 |
| Rejected | 96 |

| Split | Records | Bytes | SHA-256 |
|---|---:|---:|---|
| train | 1,808 | 3,502,298 | `b983d25c1b335d810a6e438745615f89bdc4bea6b63c0388583418a0c7ea01b6` |
| validation | 98 | 176,540 | `bce9890850528688263cd970eeb49af802922fa567d52cacb68ff171bae3872b` |
| test | 100 | 190,895 | `a9f2cb659793ad58166117cbf6e4c05de0bb83136203c6cb48ac953cf1653823` |
| quarantine | 96 | — | `0616cc244fea0298211fd6a165226004de5023d930526609b6a3b0558d1d1d00` |

## Composition

| Source | Records | Tasks |
|---|---:|---|
| MITRE ATT&CK | 1,083 | attack-technique (837), defensive-control (246) |
| MITRE CWE | 923 | weakness (923) |

| License | Records |
|---|---:|
| MITRE-ATTACK | 1,126 |
| MITRE-CWE | 976 |

License counts include records that were later removed by cleaning or splitting,
which is why they exceed the output-record counts.

## Cleaning and leakage

| Check | Result |
|---|---|
| Secret redaction | enabled |
| Exact + SimHash dedup | enabled, threshold 3 |
| Contamination screen | 13-gram, 20% threshold |
| Evaluation files screened | `baseline_probe_v1.jsonl`, `seceval_v1.jsonl`, `smoke_eval.jsonl` |
| Evaluation n-grams indexed | 241,515 |
| Contamination findings | 0 |

The index covers 241,515 evaluation n-grams, so the zero is a real measured zero
for verbatim 13-gram overlap, not a skipped check. The screen is schema-agnostic:
an earlier version silently discarded benchmark-format files, which is why the
manifest now records the index size. A zero finding does not rule out paraphrase
or memorization.

## What this slice does not include

The G1 goal names ATT&CK, CWE, NVD, OWASP, and Linux/networking documentation.
This manifest covers the first two only. NVD requires paginated API collection;
OWASP and the system docs require a local clone and per-file ingestion, which the
single-source CLI does not yet compose. Those remain open milestones.

## Reproduction

See [the manifest README](../README.md). The raw downloads are not committed
(53 MB ATT&CK, 2 MB CWE) and the prepared splits are git-ignored; the manifest is
the auditable record.

## Licensing notes

Both sources are free to use for research and development with attribution, but
CyberLite does **not** redistribute the raw text or derived splits. ATT&CK and
CWE terms require preserving the MITRE copyright and attribution. Verify current
terms before publishing derived data. This is not legal advice.

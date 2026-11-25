# Dataset audit — pilot-v2

Dataset version: `cyberlite-data-2.0.0-04b01b437805`

## Counts

| Metric | Value |
|---|---:|
| Total records (accepted + rejected) | 7724 |
| Accepted | 7188 |
| Rejected / quarantined | 536 |
| train | 6351 |
| validation | 416 |
| test | 421 |

## Source distribution

| Source | Records |
|---|---:|
| ietf_rfcs | 393 |
| linux_man_pages | 246 |
| mitre_attack | 959 |
| mitre_cwe | 906 |
| netfilter_nftables | 40 |
| nist_nvd | 2615 |
| openssh_docs | 28 |
| owasp_cheatsheets | 1965 |
| project_examples | 36 |

## Task distribution

| Task | Records |
|---|---:|
| attack-technique | 712 |
| cryptography | 4 |
| defensive-control | 247 |
| detection-engineering | 6 |
| dns | 109 |
| documentation | 1467 |
| incident-response | 6 |
| log-analysis | 6 |
| logging-monitoring | 73 |
| networking | 95 |
| permissions | 93 |
| secure-coding | 504 |
| ssh | 82 |
| system-administration | 48 |
| system-hardening | 68 |
| tls | 141 |
| vulnerability | 2615 |
| vulnerability-remediation | 6 |
| weakness | 906 |

## License distribution

| License | Records |
|---|---:|
| CC-BY-SA-4.0 | 1965 |
| GPL-1.0-or-later | 6 |
| GPL-2.0-only | 40 |
| GPL-2.0-or-later | 10 |
| GPL-3.0-or-later | 8 |
| IETF-Trust | 393 |
| Linux-man-pages-1-para | 67 |
| Linux-man-pages-copyleft | 155 |
| MITRE-ATTACK | 959 |
| MITRE-CWE | 906 |
| OpenSSH | 28 |
| Public-Domain | 2615 |
| Synthetic | 36 |

## Rejection reasons

| Reason | Records |
|---|---:|
| duplicate | 417 |
| quality | 119 |

## Duplicates and leakage

| Check | Result |
|---|---:|
| Exact duplicates | 0 |
| Near duplicates | 0 |
| Cross-source duplicates | 0 |
| Cross-split leakage findings | 0 |
| Group split violations | 0 |

## Contamination

Verified in this audit: **True**

Indexed evaluation n-grams: 241515

| Benchmark | Items | N-grams | SHA-256 | Version | Matched |
|---|---:|---:|---|---|---:|
| baseline-probe-v1 | 36 | 594 | `f5a7055c5168e77529b52e0d572cf8f987c60d15e6e5c49a0d3099b70857baf4` | v1 | 0 |
| seceval | 2182 | 240755 | `6ae74b2c9c45d1024f99453be00ae82d00567f0b5f1ffa1cc4109a2fa4ef1c03` | 205dab7b0888a06f4b53ca7d9c7093e1326683e1 | 0 |
| smoke-eval | 8 | 166 | `111132beb36f65d9bc57bdb42efe9d801d5971d0f355f23b08723e7b6be5fc3d` | v1 | 0 |

Verified removals across splits: 0

## Token lengths

Tokenizer: `Qwen/Qwen3.5-0.8B`

| p50 | p90 | p95 | p99 | max | over limit |
|---:|---:|---:|---:|---:|---:|
| 373 | 616 | 798 | 1539 | 3474 | 216 |

## Missing provenance

| Field | Missing records |
|---|---:|
| id | 0 |
| source | 0 |
| source_url | 0 |
| source_version | 0 |
| license | 0 |
| task | 0 |
| upstream_id | 0 |

## Manual review

**Not completed.** A deterministic stratified sample and review template have been generated. No human review is recorded by this audit.

Samples: `data/processed/pilot-v2/review_samples.jsonl`
Template: `data/manifests/pilot-v2/audit/review_template.md`

## File inventory

| File | Bytes | SHA-256 |
|---|---:|---|
| train.jsonl | 18536037 | `db008cf7d50f3fc2b98387d07069aed36375833072df80bf75c048a0935c95e5` |
| validation.jsonl | 1315091 | `22ac9d49b92b55ea685dd3afebd6aad2e4950bb3e44ebcc27503692fcf42e91b` |
| test.jsonl | 1225139 | `9145f39a766c13e97961acb3c586caa610eda5babc7edd831957894401a0c2c1` |
| quarantine.jsonl | 65026 | `e0aa8f574d2f76f15bdcb2095eeffa2e92018db6ae0e3e6f42bd4c213b929696` |
| manifest.json | 107899 | `522c37e4c0e4f283fd0d0e3457d323fd732be39b8eddfbc431404295c8feeb64` |

## Limitations

- Quality gates are heuristics and can reject useful text or accept questionable text.
- The 13-gram screen does not detect paraphrase, translation, or conceptual overlap.
- Token counts are a length signal, not a quality or factuality measure.
- Manual review is pending; no record is described as human-verified.

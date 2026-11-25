# CyberLite dataset expansion — final independent audit (Agent J2)

**Auditor:** Agent J2, independent; did not generate the corpus and did not take part in earlier reviews.
**Date:** 2026-11-25, ~13:56–14:05 UTC.
**Method:** manifest and report inspection, targeted replay of hashes/counts, 10-record schema/provenance sample, review-ledger recomputation, evaluation validation, license preflight, full engineering command suite. Not a full 15,863-record manual read.

## Verdict

**CONDITIONAL PASS — do not certify as a frozen reviewed release.**

At the start of the audit (13:56 UTC) the claimed production snapshot existed and its six file hashes, split counts, content hashes, group isolation, evaluation separation, and 25k shortfall statement all checked out. Two high-severity provenance defects remain, and the production artifact was **overwritten by another process during the audit** (14:00–14:02 UTC): the on-disk manifest is now `cyberlite-syn-2.0.0-37b01792c2d8` with 15,906 records (14,281/828/797), no review application, and the 43 review-quarantined records are back in the splits. The claimed `…-rev1` 15,863-record build is therefore no longer reproducible from the workspace. The balanced files remain intact and internally hash-consistent, but their main manifest carries production-wide statistics.

## Findings

### Critical

1. **The claimed frozen production build was replaced during the audit, and review quarantine was undone.**
   - 13:56 UTC: manifest `cyberlite-syn-2.0.0-37b01792c2d8-rev1`, 15,863 accepted, splits 14,242/826/795; all manifest file hashes matched; 43 review-quarantined IDs were absent.
   - 14:00 UTC onward: splits/`manifest.json` rewritten. Current manifest: version `cyberlite-syn-2.0.0-37b01792c2d8` (no `-rev1`), **15,906** accepted, splits **14,281/828/797**, `review_coverage.ai_independent_review = 0`, no `review_report_sha256`, and all **43** review-quarantined IDs are present again (39 train, 2 validation, 2 test).
   - The new files are internally hash-consistent with the *new* manifest, so this is not corruption; it is loss of the reviewed/frozen artifact. No audit command writes `data/processed`, and the cause was not identified from the running processes; a concurrent rebuild is the most likely explanation. Regardless of cause, the claimed artifact is not stable or reproducible.

### High

2. **Review provenance is stale for 6 of 27 “AI-independently-reviewed” records.** The review ledgers are calibration-build reviews (`913298…`, `04a21…`) with empty `content_hash` fields. Matching reviewed IDs to their calibration records shows 6 records whose published text hash differs from the reviewed text (`api-bola-001-codereview-1`, `crypto-aead-002-codereview-1`, `log-ssh-bruteforce-101-misconception-1`, `go-path-002-codereview-1`, `gen-testing-007-misconception-1`, `det-threshold-correlation-305-checklist`). The 8.85/9.57/9.04 means do not fully describe the published text. Because current `apply_reviews.py` requires a non-empty matching `content_hash`, a fresh apply would now classify all 102 review items as stale and apply zero reviews — the 27-record coverage cannot be re-derived from the committed ledger.
3. **`review_report_sha256` did not match the report in the claimed snapshot.** Manifest claimed `495d367c…`; actual `review_report.json` was `73a4c542…` (mtime 13:45, manifest 13:49). The report was regenerated after/independently of the manifest hash. The current rebuilt manifest drops the field entirely.
4. **The balanced manifest does not describe the balanced corpus.** Counts, split files, and hashes are correct (9,588; 8,592/517/479), and the content is a same-split subset of the pre-rebuild production view with zero group leaks. But `distributions`, `token_lengths.records`, and `review_coverage.automated_screening` are the production values: difficulty 11,658/2,341/1,757/107 and token records 15,863 versus actual 5,600/2,134/1,747/107 and 9,588; origin 13,802/2,061 versus actual 7,933/1,655. Source/license/kind distributions are likewise production-wide. Mixture caps themselves are enforced (no domain/family violations; difficulty counts within quotas).

### Medium

5. **The final report mislabels deferred records as rejected.** The balanced row prints `6275 deferred` in the “Rejected” column, but the balanced manifest has `rejected_records: 0` and `deferred_records: 6275`. The production row’s 6,908 also excludes the 43 review removals, so no single column reconciles 22,814 candidates.
6. **“Reviewed records: 102” is a calibration review sample, not production coverage.** Of 102 unique reviewed IDs, 29 aggregate to accept, 21 quarantine, 52 revise; 27 accepted records survive in production. The report separates the 27 only in a secondary bullet, so a reader can mistake 102 for production review coverage. `DATASET_CARD.md` states the 27 correctly.
7. **`DATASET_CARD.md` contains contradictory source/license counts.** It reports curated synthetic 2,061 / source-derived 13,802 in one table, then “synthetic 2,096” and “Linux man-pages 197” in the source distribution; the manifest says Linux man-pages 216 and license-class Linux man-pages 197. The 2,096 figure is pre-review-quarantine.
8. **GOALS.md contamination figure is stale.** It says the 13-gram screen indexed 241,515 n-grams from SecEval/baseline/smoke; the current build indexes 277,950 across six files including the three frozen 55-item sets. The statement is true only for the older five-file screen.
9. **Accepted review means are slightly off.** Recomputed over the 29 accepted aggregate items: 8.839 overall / 9.569 technical / 9.040 grounding, versus reported 8.85 / 9.574 / 9.043 over 27. Two accepted IDs are not in the published corpus; the report does not explain them.

### Low

- `config_sha256` is a hash of the manifest `options` object, not the YAML config file; the name is misleading (the value is self-consistent).
- `review_quarantine.jsonl` is a decision ledger only: no prompt/response, license, source, or content hash, so quarantined text cannot be audited from it.
- 35 accepted records are `pending-human-review`; “all other accepted records automated-screened” is slightly imprecise.
- DATASET_CARD token p50 is reported as 373; stored `token_count` values give 372 (not independently re-tokenized).
- `277,950` is the sum of per-file n-gram counts, not the unique union (an earlier audit reported 277,879 unique; not re-run here).
- README still describes the training corpus as pilot-v2 (7,188 records) and does not mention the 15,863/9,588 synthesis builds; not false for `configs/qlora.yaml`, but stale for the expansion.

## Independently reproduced

| Check | Result |
|---|---|
| Production counts at 13:56 | 15,863; 14,242 / 826 / 795; rejected 6,908; review quarantine 43; max tokens 1,024; 0 contamination removals; 0 cross-split leaks |
| Production file SHA-256 | All 6 files matched the claimed manifest at 13:56 |
| Schema / content hashes (10 sampled) | 10/10 `text_for_dedup` hashes match; required fields present; split column correct |
| Groups / IDs | 5,038 groups, 0 multi-split groups, 0 duplicate IDs / 15,863 |
| Balanced view | 9,588; 8,592/517/479; file hashes match; subset of production with same split and hash; 0 group leaks; caps enforced |
| Review ledger | 180 reviews, 102 records, 13 disagreements = 0.1275; accept 29 / quarantine 21 / revise 52; 43 quarantine entries |
| Review content binding | 6/27 reviewed records differ from reviewed calibration content; ledgers carry no content hash |
| Evaluation | 3 × 55 items; full SHA-256 matches meta/manifest; validator `ok=True` for all; 0 ID/question overlap with training; 277,950 n-gram sum; 0 matches; CyberSecEval unavailable |
| Licensing gate | `--preflight`: `software_ready=True`, `research_ready=False`, `license_compliance=pass`, exit 1; all 11 unresolved licenses explicitly acknowledged; unresolved-license/manual-review/preregistration blockers reported |
| Restricted raw text | `data/raw` and `data/processed` are git-ignored; tracked data are manifests, synthetic eval/seed files, and review artifacts only |
| Documentation honesty | 25,000 target shortfall (9,137) stated; target not padded; no human review claimed; AI review explicitly distinguished |
| Safety / leakage in sample | 10-record sample had no operational exploit/malware instructions; lexical scan found 165 dangerous-term occurrences, all descriptive NVD/ATT&CK/defensive context; no benchmark item matched |

## Commands run (venv `/home/bh/qwen-cyber/.venv`; system `python` absent, used `python3`/venv)

| Command | Exact outcome |
|---|---|
| `ruff check cyberlite scripts tests` | `All checks passed!` (exit 0) |
| `ruff format --check cyberlite scripts tests` | `124 files already formatted` (exit 0) |
| `mypy cyberlite` | `Success: no issues found in 56 source files` (exit 0) |
| `pytest -m "not integration"` | `269 passed, 1 deselected, 1 warning in 24.83s` (exit 0) |
| `python3 scripts/validate_repo.py` | `repository validation passed (347 files checked)` (exit 0) |
| `python3 scripts/update_progress.py --check` | `README.md progress is up to date (24/47 milestones (51%))` (exit 0) |
| `scripts/train.py --config configs/lora_synthesis.yaml --preflight` | exit 1; software ready True / research ready False; license pass |

## Not independently reproduced

Full 15,863-record schema sweep; tokenizer re-count (stored `token_count` used); independent 13-gram index rebuild and unique-union count; SimHash/MinHash deletion replay; full privacy/PII review; live source-URL/license verification; full corpus safety read; rebuild of the corpus from source packs; explanation of the 25 quarantined-record content mismatches (ledger has no text/hash).

## Limitations

- The production artifact changed while the audit ran; all production figures are pinned to the 13:56 snapshot unless labelled current. Re-verify hashes before any publication.
- Review coverage is AI-only, sampled, 27/15,863 (0.17%), with 6/27 stale bindings; no human review.
- Contamination is lexical 13-gram only; paraphrase/translation/conceptual leakage is undetected, and CyberSecEval is unavailable.
- Safety, licensing, and documentation checks are targeted, not exhaustive.

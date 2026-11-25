# Response to the final independent audit

**Date:** 2026-11-25
**Audit:** `docs/reports/final-independent-audit.md` (Agent J2, conditional pass)
**Final build:** `cyberlite-syn-2.0.0-c7a2b7f426ce-rev1`, 15,590 accepted;
balanced view `…-balanced-f13f867d`, 8,287 accepted.

The audit's conditional verdict stands. This response records what changed after
the audit and what remains unresolved; it does not certify the corpus.

## Resolved

1. **Artifact instability.** The audited snapshot was overwritten by a
   concurrent rebuild during the audit. The build was then frozen: no further
   production rebuild is required for this commit. The manifest, split hashes,
   and `review_report_sha256` are regenerated together; the current
   `review_report_sha256` matches the report.
2. **Review provenance.** `ReviewItem` now carries `content_hash`, and
   `scripts/apply_reviews.py` applies a review only when that hash equals the
   record's current `metadata.content_hash`. Legacy ledgers with no hash apply
   zero reviews. A fresh 40-record production sample was reviewed by two new
   independent agents; 29 records matched by hash, 5 were accepted, 13 were
   quarantined/revised, and 4 were stale. The 5 accepted records meet the
   rubric (8.687 overall, 9.15 technical, 9.00 grounding), but coverage is
   **5/15,590** and is not representative.
3. **Balanced manifest statistics.** `scripts/balance_dataset.py` now
   recomputes distributions from the selected 8,287 records instead of copying
   production-wide statistics.
4. **Deferred vs rejected.** The final report shows "7,303 deferred" for the
   balanced view and `rejected_records: 0` in its manifest.
5. **Review-count ambiguity.** The final report now reports the production
   sample (29 matched, 5 accepted) separately from the chronological review
   history. `DATASET_CARD.md` states 5 reviewed records, not 102.
6. **Dataset-card counts.** Source, licence, task, difficulty, token, and
   version figures were regenerated from the final manifest.
7. **Quarantine auditability.** `review_quarantine.jsonl` now includes the full
   quarantined record alongside the decision and findings.
8. **`review_report_sha256`.** Recomputed after the final review report was
   written.

## Still open (material)

- **The sampled review failed the acceptance gate.** 29 hash-bound reviews have
  a mean of 6.81; only 5 passed. The corpus is not approved for training.
  Recurring defects: template scaffolding, generic verification text,
  inference presented as observation in log tasks, and a few stale or
  version-specific claims.
- **Review coverage is 0.03%.** No claim of full independent review is made.
  No human review exists.
- **The 25,000 target was not met.** 15,590 accepted; the gap is reported, not
  padded.
- **NVD remains 46.9% of the raw corpus.** The balanced view caps it, but the
  archive is source-heavy.
- **CyberSecEval is unavailable.** Contamination coverage is incomplete.
- **Licence questions remain unresolved.** Training validation passes with
  explicit acknowledgements; research preflight correctly stays blocked.
- **`config_sha256` names a hash of the manifest options object**, not the YAML
  file; it is self-consistent but the name is misleading.

The next action is not to scale. It is to regenerate the weak families
(especially command/config explanations and log inference) and re-review a
larger hash-bound sample until the 8.5/9/9 gate is met.

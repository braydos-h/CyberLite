# Contamination, deduplication and split-integrity audit — synthesis calibration

**Auditor:** Agent G (independent)
**Date:** 2026-11-25
**Corpus:** `data/processed/synthesis-calibration/{train,validation,test}.jsonl`
**Build:** `cyberlite-syn-2.0.0-04a21fdaa5ec`
**Machine-readable results:** `data/manifests/synthesis-calibration/integrity_audit.json`

**Status:** No violation of the stated duplicate, leakage, group-split, or
13-gram contamination thresholds. One field-level duplication finding crosses
the train/validation boundary (F1), and CyberSecEval remains unscreened (F3).
Absence of CyberSecEval is **not** a pass.

This audit reimplemented exact hashing, 64-bit SimHash, MinHash/Jaccard, the
13-gram screen, and the deterministic group split in a standalone script rather
than importing the pipeline, then cross-checked every headline count against
`cyberlite.data.cleaning`, `cyberlite.data.contamination`,
`cyberlite.data.semantic` and `cyberlite.data.splits`. The two implementations
agree on all counts in this report.

---

## 1. Corpus and integrity

| Measure | Value |
|---|---:|
| Records | 500 |
| Train / validation / test records | 444 / 33 / 23 |
| Distinct `metadata.group` values | 318 |
| Unique record IDs | 500 |
| Missing `source` / `license` | 0 / 0 |
| Records with prompt (incl. chat) | 485 |
| Chat records (messages) | 12 |
| FIM records (no prompt) | 15 |
| `split` field disagrees with file | 0 |
| `human_reviewed = true` | 0 |

The 15 FIM records have no prompt and are excluded from skeleton analysis; the
remaining 485 records have prompt text. All 500 records produced at least one
13-word shingle, so the contamination screen had no unscreenable records.

Source mix is highly skewed: `cyberlite_synthesis` supplies 420 records
(84.0%); the remaining 80 come from eight source-derived families (NVD 28,
ATT&CK 14, CWE 11, IETF 8, Linux man pages 8, OpenSSH 5, OWASP 4, nftables 2).
That is a provenance concentration, not a duplicate or contamination finding.

---

## 2. Duplicates within the calibration corpus

### 2.1 Exact duplicates

Method: SHA-256 over the lowercased `[a-z0-9_]+` token stream (single-character
non-digits dropped), matching the pipeline's exact-key normalization.

| Measure | Count |
|---|---:|
| Exact duplicate groups (whole record) | 0 |
| Extra copies | 0 |
| Exact duplicate prompt groups | 0 |
| Exact duplicate response groups | 1 |
| Extra response copies | 9 |

There are no duplicate records and no duplicate prompts. One response group is
identical behind different prompts: ten NVD CPE-applicability records share an
819-character answer byte-for-byte. Nine are in train and one is in validation.
This is the cross-split finding discussed in §3.3.

### 2.2 SimHash near-duplicates (Hamming ≤ 3)

All 124,750 pairs were compared; no banding approximation was used.

| Measure | Value |
|---|---:|
| Pairs at Hamming distance ≤ 3 | 0 |
| Minimum distance, any pair | 4 bits |
| Pairs at distance 4 / 5 / 6 | 6 / 13 / 17 |
| Pairs at distance ≤ 3 crossing splits | 0 |
| Minimum cross-split distance | 6 bits |

The six closest within-corpus pairs are one bit above the threshold. Five are
in train, one in validation; none crosses a split. Examples:

| Left | Right | Distance | Split | Same group |
|---|---|---:|---|---|
| `syn-cloud-container-supply-chain-cont-content-trust-scope-command-1` | `...-command-2` | 4 | train/train | yes |
| `syn-cloud-container-supply-chain-k8s-admission-policy-engines-diagnose` | `...k8s-networkpolicy-additive-peers-diagnose` | 4 | train/train | no |
| `syn-incident-response-forensics-threat-intel-forensics-soundness-033-explain` | `...-mcq-1` | 4 | validation/validation | yes |

These are template siblings or multiple task views, not accidental corpus
duplicates. The closest cross-split pair is 6 bits, so the 3-bit criterion has
no cross-split near miss.

### 2.3 MinHash near-duplicates (Jaccard ≥ 0.88)

Method: 5-word shingles over lowercased word tokens, 128 MinHash permutations.
The decision used **exact Jaccard for every pair**, which is stricter than LSH
candidate sampling.

| Measure | Value |
|---|---:|
| Pairs at Jaccard ≥ 0.88 | 0 |
| Highest Jaccard, any pair | 0.8555 |
| Pairs at ≥ 0.80 / ≥ 0.70 / ≥ 0.60 / ≥ 0.50 | 1 / 5 / 10 / 24 |
| Pairs at ≥ 0.88 crossing splits | 0 |

The highest pair is a same-document, same-split pair:

| Left | Right | Jaccard | MinHash estimate | Split | Same group |
|---|---|---:|---:|---|---|
| `grnd-openssh-docs-openssh-docs-841d94ec4f1d6d22-requirement-1` | `...-requirement-2` | 0.8555 | 0.8516 | train/train | yes |
| `syn-fundamentals-linux-networking-lnx-perm-model-command-1` | `...-command-2` | 0.7653 | 0.7266 | train/train | yes |
| `syn-cloud-container-supply-chain-cont-content-trust-scope-command-1` | `...-command-2` | 0.7474 | 0.7109 | train/train | yes |
| `syn-incident-response-forensics-threat-intel-forensics-timeline-024-command-1` | `...-command-2` | 0.7321 | 0.7500 | train/train | yes |
| `syn-cryptography-identity-access-cert-chain-024-command-1` | `...-command-2` | 0.7113 | 0.6641 | test/test | yes |

The maximum is only 0.0245 below the threshold. That is a narrow margin, but
the pair is a same-group multi-view inside train, so removing it would not
change split integrity. The pipeline's own candidate-stage report removed five
semantic pairs at 0.8819–0.8923 before the final 500 were selected; this
0.8555 pair survived because it is below the configured cut.

---

## 3. Cross-split leakage

### 3.1 Whole-record checks

| Method | Threshold | Cross-split pairs |
|---|---|---:|
| Exact hash | equality | 0 |
| SimHash | ≤ 3 bits | 0 |
| MinHash / exact Jaccard | ≥ 0.88 | 0 |
| Shared `metadata.group` | one split per group | 0 groups |

No ID pair crosses a split at any stated threshold, and no group is shared.
The closest full-record cross-split pairs are well below threshold:

| Left (split) | Right (split) | Jaccard | Same group |
|---|---|---:|---|
| `grnd-nist-nvd-nist-nvd-00795ecd6c9525f0-applicability` (train) | `grnd-nist-nvd-nist-nvd-00b3cc38194e31f8-applicability` (validation) | 0.5350 | no |
| `grnd-nist-nvd-nist-nvd-00795ecd6c9525f0-uncertainty` (train) | `grnd-nist-nvd-nist-nvd-00b3cc38194e31f8-uncertainty` (validation) | 0.5115 | no |

### 3.2 Group-level check

Every `metadata.group` appears in exactly one split (see §4). No violations.

### 3.3 Finding F1 — field-level response leakage across train/validation

One validation record shares its response **byte-for-byte** with nine train
records:

- Validation: `grnd-nist-nvd-nist-nvd-00b3cc38194e31f8-applicability`
  (CVE-2020-29504).
- Train: the nine other `*-applicability` records in the NVD CPE family
  (CVE-2024-20959, CVE-2024-0188, CVE-2023-52191, CVE-2023-6625,
  CVE-2023-51464, CVE-2024-21796, CVE-2023-34063, CVE-2024-22086,
  CVE-2024-0291).
- Shared text: 819 characters, starting
  "A CPE is a product-and-version expression, not proof that the asset is
  affected…".
- Response-field similarity: 1.0 (raw strings are equal). Whole-record
  Jaccard: 0.535, below 0.88, so the whole-record MinHash pass does not catch
  it.
- The 10 records sit in 10 distinct groups, so this is **not** a group-split
  violation; it is answer boilerplate reused across distinct CVE groups.

Impact: validation loss for this item can be partly explained by memorized
answer text present in train. This is a genuine evaluation-integrity issue even
though every stated duplicate threshold passes. The related `-uncertainty`
train/validation pair is not byte-identical but is 0.5115 similar, so the whole
NVD boilerplate family deserves attention.

---

## 4. Group-aware splitting

| Measure | Value |
|---|---:|
| Distinct groups | 318 |
| Groups with 1 / 2 / 3 / 4 / 5 records | 185 / 94 / 30 / 8 / 1 |
| Groups appearing in >1 split | 0 |
| Records in `metadata.group`-less records | 0 |
| `record_group()` fallback equal to `metadata.group` | 500 / 500 |

The deterministic split was re-derived independently: `sha256("1337:" + group)`
mapped through the 0.90 / 0.05 / 0.05 cut points. The result matches the actual
assignment for all 318 groups, with 284 / 20 / 14 groups in
train / validation / test and 444 / 33 / 23 records. No `split` field disagrees
with its file.

The largest group is 5 records (`openssh_docs:ssh_config.5`), followed by eight
groups of 4 records (NVD CVEs and synthesis documents). All remain intact in
one split.

---

## 5. Benchmark contamination screen (13-gram, threshold 0.20)

Every one of the 500 records was screened against each of the six evaluation
files separately and against their union. Overlap is the fraction of a record's
13-grams present in the benchmark index.

| Benchmark | Items | Indexed 13-grams | Max overlap | Records ≥ 0.20 | Removed | Records ≥ 0.10 |
|---|---:|---:|---:|---:|---:|---:|
| SecEval v1 | 2,182 | 240,755 | 0.0241 | 0 | 0 | 0 |
| Baseline probe v1 | 36 | 594 | 0.0000 | 0 | 0 | 0 |
| Smoke eval | 8 | 166 | 0.0000 | 0 | 0 | 0 |
| cyberlite_eval_factual_v1 | 55 | 7,250 | 0.0000 | 0 | 0 | 0 |
| cyberlite_eval_vulnerability_v1 | 55 | 13,312 | 0.0419 | 0 | 0 | 0 |
| cyberlite_eval_logs_ir_v1 | 55 | 15,873 | 0.0000 | 0 | 0 | 0 |
| **Combined** | **2,391** | **277,879** | **0.0419** | **0** | **0** | **0** |

No record reached 0.20; no record reached even 0.10. Nothing was removed and no
group was quarantined. Nine records have a non-zero overlap:

| Record | Overlap | Split | Shared text |
|---|---:|---|---|
| `grnd-nist-nvd-nist-nvd-00795ecd6c9525f0-json` | 0.0419 | train | CVSS v3.1 vector tokens |
| `syn-vulnerability-classification-remediation-cvss-v31-environmental-config-1` | 0.0376 | train | CVSS v3.1 vector tokens |
| `syn-vulnerability-classification-remediation-cvss-v31-base-metrics-config-complete` | 0.0354 | train | CVSS v3.1 vector tokens |
| `grnd-nist-nvd-nist-nvd-00795ecd6c9525f0-uncertainty` | 0.0314 | train | CVSS v3.1 vector tokens |
| `grnd-nist-nvd-nist-nvd-00b3cc38194e31f8-uncertainty` | 0.0293 | validation | CVSS v3.1 vector tokens |
| `grnd-nist-nvd-nist-nvd-00795ecd6c9525f0-applicability` | 0.0292 | train | CVSS v3.1 vector tokens |
| `grnd-nist-nvd-nist-nvd-00b3cc38194e31f8-applicability` | 0.0262 | validation | CVSS v3.1 vector tokens |
| `grnd-mitre-attack-mitre-attack-012c208a4d147578-match` | 0.0241 | train | ATT&CK peripheral-discovery description |
| `grnd-mitre-cwe-mitre-cwe-0224f8f94abee99e-requirement-1` | 0.0171 | train | CWE input-validation definition |

The CVSS hits are the same vector grammar (`cvss 3 1 av n ac l pr n ui n s u
c h i h a …`) appearing in both places; they are structured metadata, not
answer text. The MITRE/CWE hits are verbatim upstream definitions quoted by
both the record and a benchmark item:

- "attempt to gather information about attached peripheral devices and
  components connected to a computer system"
- "a list of acceptable inputs that strictly conform to specifications reject
  any input that does not…"

At 4 or 7 shared 13-grams per record (overlaps 1.7–4.2%), these are far below
the 0.20 cutoff. They are reported because a non-zero overlap should never be
silently rounded to zero.
Two validation records have overlaps of 2.6–2.9%, still an order of magnitude
below the threshold.

### 5.1 Unavailable benchmarks — absence is not a pass

**CyberSecEval / CyberSecEval 2 was not screened.** Only
`benchmarks/cyberseceval/README.md` exists; there is no local JSONL under
`data/evaluation` and no CyberSecEval entry in the build's benchmark index. The
corpus must not be described as CyberSecEval-clean. Any other absent benchmark
is likewise unscreened.

### 5.2 Screen limitations

- A 13-gram index only compares verbatim word sequences. Paraphrase, synonym
  substitution, translation and conceptual reuse are invisible.
- Benchmark items shorter than 13 words contribute no fingerprints; the screen
  is effectively a document-level verbatim check. The separate paraphrase
  heuristic in §6 partially covers this.
- Benchmark fields are flattened to strings, which can create artificial
  cross-field 13-grams. That makes the screen slightly conservative, not
  permissive.
- Zero overlap in synthetic/small suites is not evidence about unseen
  benchmarks.

---

## 6. Paraphrased benchmark questions — heuristic screen

Method: token-set comparison, no stemming or embeddings. A record's prompt was
compared with each benchmark question; its response was compared with the
question + choices + answer. Symmetric containment is
`|A ∩ B| / min(|A|, |B|)`.

| Measure | Value |
|---|---:|
| Records with prompt or response Jaccard > 0.50 | 0 |
| Records with symmetric containment > 0.60 | 36 |
| Flagged record–item pairs | 49 |
| Flagged pairs by benchmark | SecEval 28, baseline probe 15, cyberlite_eval_factual_v1 6 |
| Max prompt Jaccard | 0.2750 |
| Max response Jaccard | 0.2609 |
| Max prompt containment | 0.7500 |
| Max response containment | 1.0000 |
| Max fraction of a record prompt found in one benchmark item | 0.4400 |
| Max fraction of a benchmark question found in one record prompt | 0.7500 |

No record crosses the Jaccard > 0.5 criterion. The 36 containment hits are a
denominator artifact: short benchmark questions or answers are often subsets of
longer prompts/responses. All 49 flagged record–item pairs are enumerated in
`integrity_audit.json` (`paraphrase_heuristic.all_flagged_pairs`). In the
strongest response case a record with no prompt (FIM) has 1.0 containment
against a benchmark question with 50 tokens, yet Jaccard is 0.0385; that is
shared general vocabulary, not a paraphrased copy.

| Record | Benchmark item | Prompt Jaccard |
|---|---|---:|
| `syn-language-security-retention-rust-zeroize-004-codereview-1` | `cyberlite_eval_vulnerability_v1` / `eval-e2-vuln-sqli` | 0.2750 |
| `syn-web-api-secure-development-api-oauth-pkce-001-mcq-1` | `cyberlite_eval_factual_v1` / `eval-e1-knowledge-pkce` | 0.2571 |
| `syn-vulnerability-classification-remediation-cwe-330-weak-randomness-codereview-1` | `cyberlite_eval_vulnerability_v1` / `eval-e2-vuln-sqli` | 0.2564 |
| `syn-monitoring-detection-soc-log-rfc3164-gap-004-log-1` | `cyberlite_eval_factual_v1` / `eval-e1-uncertainty-single-failed-login` | 0.2540 |

The highest response Jaccard (0.2609) is a different record,
`syn-language-security-retention-gen-regex-004-mcq-1`, against
`cyberlite_eval_logs_ir_v1` item `eval-e3-ret-redos`. Prompt and response
maxima can come from different benchmark items.

**This is a heuristic, not proof.** It cannot detect a paraphrased question
that reuses the same concept with different vocabulary, and it can over-flag
short questions. The evidence supports "no high-similarity paraphrase found",
not "no paraphrase contamination exists".

---

## 7. Overrepresented templates and concentration

Prompts were normalized by replacing URLs, CVE/CWE/ATT&CK identifiers, hex IDs,
file names, snake_case identifiers and numbers, then reduced to the first
12 word tokens. The 485 prompts yield 307 distinct skeletons — global diversity
is reasonably high (entropy 7.26 bits, top skeleton 8.66%, top five 27.84%):

| Skeleton (first 12 normalized tokens) | Count | Share |
|---|---:|---:|
| `explain what this bash command does what could go wrong if it` | 42 | 8.66% |
| `use only the excerpt below a deployment plan states the following behaviour` | 41 | 8.45% |
| `return a json object summarizing this guidance for a runbook use exactly` | 27 | 5.57% |
| `during a design review a colleague asks for a precise explanation of` | 15 | 3.09% |
| `a scanner reports this cve against a production host explain how to` | 10 | 2.06% |
| `a ticket says host host <n> is vulnerable because scanner output lists` | 9 | 1.86% |
| `complete the blanked directive in this yaml configuration so that it achieves` | 9 | 1.86% |
| `the following python function was reported as vulnerable explain the root cause` | 6 | 1.24% |
| `explain what this powershell command does what could go wrong if it` | 5 | 1.03% |
| `the following javascript function was reported as vulnerable explain the root cause` | 5 | 1.03% |

The more important concentration is **within task families**, where one
skeleton can dominate the whole family:

| Task family | Records | Top-skeleton count | Share | Distinct skeletons |
|---|---:|---:|---:|---:|
| evidence-grounded-qa | 41 | 41 | 100.0% | 1 |
| false-positive-recognition | 10 | 10 | 100.0% | 1 |
| uncertainty-handling | 9 | 9 | 100.0% | 1 |
| attack-technique-recognition | 4 | 4 | 100.0% | 1 |
| incident-investigation | 2 | 2 | 100.0% | 1 |
| structured-json | 30 | 27 | 90.0% | 2 |
| command-explanation | 47 | 42 | 89.4% | 2 |
| detection-rule-interpretation | 4 | 3 | 75.0% | 2 |
| configuration-completion | 20 | 9 | 45.0% | 10 |
| code-remediation | 17 | 6 | 35.3% | 7 |
| instruction-response | 50 | 13 | 26.0% | 38 |
| multiple-choice | 65 | 1 | 1.5% | 65 |

The dominant skeletons also span splits: the bash-command skeleton is 32 train,
5 validation, 5 test; the excerpt-supported-claim skeleton is 35 train, 3
validation, 3 test; the JSON-runbook skeleton is 24 train, 2 validation, 1
test. That is template repetition across splits, not group leakage, but it
limits how much a test score can say about generalizing beyond the template.

### 7.1 Facet concentration

| Facet | Distinct | Largest share | Imbalance (max/min) | Entropy (bits) |
|---|---:|---:|---:|---:|
| Task family | 24 | 13.0% (`multiple-choice`, 65) | 32.5 | 4.188 |
| Task | 19 | 41.6% (`security-knowledge`, 208) | 208.0 | 3.024 |
| Domain | 9 | 16.0% (`<none>`, 80; largest real 12.0%) | 2.05 | 3.141 |
| Source | 9 | 84.0% (`cyberlite_synthesis`, 420) | 210.0 | 1.055 |
| Difficulty | 4 | 40.0% (`intermediate`, 200) | 8.0 | 1.766 |
| Variant | 12 | 84.0% (`<none>`, 420) | 420.0 | 1.026 |

Difficulty is 200 intermediate / 150 foundational / 125 advanced / 25 expert.
Domain balance is good among labelled records (39–60 per domain); the 80
`<none>` records are source-derived records without a domain label. Provenance
is the most skewed facet: 84% of records come from the synthesis source.

---

## 8. Findings and recommended actions

| ID | Severity | Finding | Action |
|---|---|---|---|
| F1 | Medium | One validation response is byte-identical to nine train responses (NVD CPE family, 819 chars). Whole-record Jaccard 0.535, so the 0.88 dedup does not catch it. | Deduplicate on the response field, or drop/regenerate the affected validation item before using validation loss for early stopping. |
| F2 | Medium | Several task families use one prompt skeleton for 89–100% of records. | Add paraphrase-diverse variants; report per-family results rather than only aggregate scores. |
| F3 | Medium | CyberSecEval is unavailable and was not screened. | Obtain a license-compliant copy and rerun; do not claim CyberSecEval cleanliness. |
| F4 | Low | Closest MinHash pair is 0.8555, only 0.0245 below the 0.88 threshold; one pair is above 0.80. | Keep threshold 0.88; recheck after template/source changes. The pair is same-group and same-split. |
| F5 | Low | Closest within-corpus SimHash distance is 4 bits against a 3-bit threshold (6 pairs). | Keep threshold 3; cross-split minimum is 6 bits. |
| F6 | Info | `deduplication_report.json` describes the 1,999-record candidate pool (1,960 kept; 5 semantic and 34 SimHash removals), not the final 500. | Label the pipeline stage so readers do not compare it with final-corpus counts. |
| F7 | Info | The three authored eval suites are stored twice with identical content (`data/evaluation` and `data/synthesis/eval_authored`). | Keep one canonical copy or add a checksum guard; the build scanned the evaluation copies. |

---

## 9. Limitations

- All duplicate and contamination methods are lexical. Paraphrase, translation
  and conceptual reuse are not detected; empty findings are not proof of
  absence.
- MinHash used 128 permutations over 5-word shingles and exact Jaccard on all
  124,750 pairs, so LSH sampling cannot hide a pair in this corpus. It still
  cannot recognize semantic equivalence.
- 13-gram fingerprints need at least 13 words. All 500 records qualified, but
  short benchmark items contribute no fingerprints.
- The paraphrase heuristic has no stemming or embeddings, and symmetric
  containment over-fires on short questions and answers. Its 36 flags should
  not be read as 36 leaks.
- Scope was train/validation/test only. `preferences.jsonl`, `quarantine.jsonl`
  and the review batches were not audited.
- No record has `human_reviewed = true`; automated screening is not human
  review.
- CyberSecEval and any other absent benchmark remain unscreened.
- Field-level duplicate detection covers exact response equality only; it does
  not detect near-identical responses below the whole-record threshold.
- Counts are tied to build `cyberlite-syn-2.0.0-04a21fdaa5ec` and must be
  recomputed after any data change.

---

## 10. Reproduction

Independent audit script: `/tmp/opencode/audit_all.py`
Library cross-check: `/tmp/opencode/verify_lib2.py`
Raw independent output: `/tmp/opencode/audit_all.json`

The scripts are temporary and are not committed. They implement the methods
from scratch; the cross-check reproduced the same counts using
`cyberlite.data.cleaning.Deduplicator` (500 kept, 0 exact, 0 near),
`semantic.find_near_duplicates` (0), `contamination.check_contamination_v2`
(0 removed, 0 matches in all six suites), `splits.group_split_violations` (0)
and `contamination.cross_split_leakage` (0).

File hashes of the audited inputs and the full measured record are stored in
`data/manifests/synthesis-calibration/integrity_audit.json`.

# Synthetic dataset expansion

The synthesis pipeline turns small, committed knowledge packs and the frozen
pilot training split into a much larger, task-diverse training corpus. It is
deterministic, offline, and auditable. It does not call a model at build time.

## What is committed and what is not

| Artifact | Location | Git |
|---|---|---|
| Curated knowledge packs | `data/synthesis/knowledge/*.json` | yes |
| Detection-rule teaching library | `data/synthesis/seeds/detection_rules.json` | yes |
| Held-out evaluation sets (authored separately) | `data/synthesis/eval_authored/*.jsonl` | yes |
| Bulk splits, preferences, quarantine | `data/processed/synthesis-*` | no |
| Manifests and text-free reports | `data/manifests/synthesis-*` | yes |
| Review ledgers | `data/manifests/synthesis-*/reviews/*.json` | yes |
| Full review batches | `data/processed/synthesis-*/review/` | no |

## Knowledge packs

A pack is one JSON object with `schema_version`, `domain`, `display_name`,
`author`, and `facts`. Each fact carries an authored `fact`, optional
`details`, `pitfalls`, `commands`, `configs`, `code`, `logs`, `mcqs`,
`misconceptions`, and at least one primary `reference`. The schema is
`data/synthesis/knowledge/_schema.json`; the loader re-validates it without a
third-party JSON Schema dependency.

Packs are authored in original prose. They may cite primary sources but must not
paste third-party text. IDs are globally unique across packs; a duplicate is a
hard build failure.

## Build stages

```bash
# Calibration: 500 accepted records, used to measure rejection rates first.
python scripts/synthesize_dataset.py --config configs/synthesis/calibration.yaml --force

# Production: 25,000 target, merges the frozen pilot into a new group-aware split.
python scripts/synthesize_dataset.py --config configs/synthesis/production.yaml --force
```

The stage target is a ceiling for accepted records, not a promise. The build
reports `generated_candidates`, `considered_candidates`, `accepted_records`,
`rejected_records`, `deferred_for_target`, and the acceptance rate separately.
If the validated pool is smaller than the target, the actual count is reported;
the target is never padded with unvalidated records.

Every split is written to `data/processed/synthesis-<stage>/` and every report
to `data/manifests/synthesis-<stage>/`. A build is resumable in the sense that
the packs, pilot, seed, split seed, and configuration fully determine the
content; rerunning with the same inputs reproduces the same record IDs.

## Generation paths

1. **Curated fact composition.** Each fact yields one explanation, up to two
   MCQs, a misconception correction, a preference pair, log interpretation,
   multi-turn triage, command explanation, configuration analysis and
   completion, secure code review, remediation, FIM, structured JSON, error
   diagnosis, and a cross-fact comparison. The number of views per fact is
   bounded so one fact cannot flood the corpus.
2. **Source-grounded derivation.** The frozen pilot train split is used as
   evidence for new task views: NVD triage, CWE explanation, CPE applicability,
   CVSS counterfactual, uncertainty, structured extraction; ATT&CK matching and
   detection; CWE matching, mitigation, and review questions; supported-claim
   MCQs for OWASP/RFC/man-page sections. Only the pilot **train** split is used.
   Validation, test, and evaluation files are never generation seeds.
3. **Detection-rule interpretation.** A small authored Sigma-style library
   yields interpretation, tuning, and blind-spot records.

Derived records keep their upstream `source`, `license`, `url`, `group`, and
upstream identifier. Synthetic records are labelled `license: Synthetic` and
`origin: curated-synthetic`. No record claims human review.

## Screening and splitting

The build applies, in order:

1. licence allowlist;
2. heuristic quality gates (length, repetition, boilerplate, link density,
   secrets, PII, missing provenance);
3. exact-hash and 64-bit SimHash deduplication (Hamming threshold 3);
4. word-shingle MinHash/LSH near-duplicate detection (approximate, lexical);
5. 13-gram contamination screening against every local evaluation JSONL, with
   group quarantine;
6. deterministic group-aware 90/5/5 splitting (`split_seed` is separate from
   the data seed so pilot-derived groups distribute across splits);
7. exact and SimHash cross-split leakage checks;
8. token-length analysis with the real Qwen tokenizer where available.

A record whose group is touched by a benchmark hit is quarantined with its whole
group. A cross-split leak removes the later record and records the finding.

## Review and quarantine

`scripts/sample_reviews.py` writes deterministic stratified batches. Independent
reviewers write ledgers in the schema in `cyberlite/data/review.py`. Then:

```bash
python scripts/apply_reviews.py \
  --splits-dir data/processed/synthesis-production \
  --manifest-dir data/manifests/synthesis-production \
  --apply
```

Accepted records receive `review_status: ai-independently-reviewed` plus the
review scores and reviewer names. Revision and quarantine decisions are removed
to `review_quarantine.jsonl`; they do not re-enter training until re-reviewed.
The script never invents a review and never marks a record human-reviewed.

## Mixture and export

`configs/synthesis/mix.yaml` declares caps, minimums, and a two-phase
curriculum. `scripts/plan_mixture.py` compares a built corpus to the policy and
writes a machine-readable plan. `scripts/export_dataset.py` writes per-kind,
per-family, and per-domain views plus validated preference pairs; the canonical
JSONL schema remains the source of truth.

## Evaluation isolation

Held-out sets live in `data/synthesis/eval_authored/` (authored by agents
isolated from the training knowledge packs) and are validated by
`scripts/validate_evaluation.py`. They are never consumed by the training
builder. The build screens training records against them, so a later evaluation
authoring pass can detect lexical overlap but cannot prove semantic
independence.

## Honest limitations

- The knowledge packs and reviews are AI-authored. AI review is not human
  review, and same-model-family reviewers can share blind spots.
- MinHash is a lexical approximation, not embedding-based semantic similarity.
- The contamination screen is 13-gram lexical; paraphrase and translation are
  not detected. CyberSecEval is not locally available.
- Extractive source-derived records inherit upstream licences and may not be
  redistributable.
- Token counts are a length signal, not a difficulty or quality measure.
- The build never executes generated code or commands. Syntax checks are
  parse-only and do not prove security.

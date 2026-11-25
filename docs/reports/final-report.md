# CyberLite dataset expansion — final report

This report is generated from build manifests and review artifacts. Measured values are labelled; targets are plans.

## Accepted corpus

| Build | Target | Accepted | Rejected | Acceptance rate | Train / val / test |
|---|---:|---:|---:|---:|---|
| calibration | 500 | 500 | 40 | 0.9259 | 444 / 33 / 23 |
| production | 25000 | 15590 | 6900 | 0.6934 | 13990 / 818 / 782 |
| balanced | 14000 | 8287 | 7303 deferred | — | 7418 / 462 / 407 |

## Evaluation sets

- 3 frozen file(s), 165 items
- All valid: True
- `cyberlite_eval_factual_v1.jsonl`: 55 items, sha256 `4f098917af536c3c…`
- `cyberlite_eval_logs_ir_v1.jsonl`: 55 items, sha256 `27f26ed40fc30b1e…`
- `cyberlite_eval_vulnerability_v1.jsonl`: 55 items, sha256 `3ce6fd0c14bc0ef4…`

## Review coverage

- Reviewed records: 29
- Review decisions: {'accept': 5, 'quarantine': 1, 'revise': 23}
- Disagreement rate: 0.069
- Applied: {'accepted_grounding_average': 9.0, 'accepted_review_average': 8.687, 'accepted_reviewed_records': 5, 'accepted_technical_average': 9.15, 'independence_warnings': [], 'quarantined_records': 13, 'review_average': 6.81, 'reviewed_records': 5, 'source_grounding_average': 8.06, 'stale_review_records': 4, 'technical_accuracy_average': 8.155}
- Accepted reviewed subset (n=5): mean 8.687, technical 9.15, grounding 9.0

## Integrity checks

- Code/config verification available: True
- Integrity audit available: True
- ML review available: True

## Blockers and next steps

- No human review sample has been recorded.
- CyberSecEval is not locally available for contamination screening.
- Windows enterprise and risk/governance knowledge packs are not yet authored.
- Review coverage is sampled; most accepted records are automated-screened only.
- Training license validation passes with explicit acknowledgements, but research preflight remains blocked by unresolved license questions, pending human review, and external pre-registration.
- Independent sampled review did not meet the 8.5 rubric mean (29 matched reviews: 6.81 overall; 5 accepted). The corpus is not approved for training and the final independent audit verdict is conditional.

- Scale accepted volume only after the review sample meets the rubric.
- Add Windows/AD, macOS, cloud-provider, and governance knowledge packs.
- Run a model comparison against the frozen evaluation sets and report raw predictions.
- Obtain legal review for derived-corpus redistribution.

## Reproduction

```bash
python scripts/synthesize_dataset.py --config configs/synthesis/calibration.yaml --force
python scripts/synthesize_dataset.py --config configs/synthesis/production.yaml --force
python scripts/validate_evaluation.py data/evaluation/cyberlite_eval_*_v1.jsonl --freeze
python scripts/apply_reviews.py --splits-dir data/processed/synthesis-production --manifest-dir data/manifests/synthesis-production --apply
python scripts/plan_mixture.py --splits-dir data/processed/synthesis-production --out data/manifests/synthesis-production/mix_plan.json
python scripts/balance_dataset.py --force
python scripts/audit_synthesis.py
python scripts/export_dataset.py --splits-dir data/processed/synthesis-production-balanced --out data/processed/exports/production-balanced --force
```

## Limitations

- AI review is sampled and is not human review.
- Same-model-family reviewers may share blind spots.
- MinHash dedup is lexical, not embedding-based semantic similarity.
- The 13-gram contamination screen does not detect paraphrase or translation; CyberSecEval is unavailable.
- Source-derived records inherit upstream licences and may not be redistributable.
- No trained-model performance is claimed; evaluation sets are frozen but no model was evaluated.

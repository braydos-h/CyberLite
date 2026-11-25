# Dataset manifests

Committed manifests are the public, redistributable record of a prepared corpus.
The corpus text itself stays out of version control when the upstream license
does not permit redistribution; the manifest carries the version, counts, split
hashes, license counts, and cleaning statistics so a third party can rebuild and
compare.

| Manifest | Sources | Records | Status |
|---|---|---:|---|
| [`pilot-v2/`](pilot-v2/) | ATT&CK, CWE, NVD, OWASP, Linux man-pages, OpenSSH, nftables, IETF RFCs, project-authored examples | 7,188 | Expanded pilot; manual review pending; CyberSecEval access pending |
| [`pilot-attack-cwe-v1/`](pilot-attack-cwe-v1/) | MITRE ATT&CK, MITRE CWE | 2,006 | Original frozen slice; preserved for comparison |

`pilot-v2` also contains `quality_report.json`, `contamination_report.json`,
`license_report.json`, `license_report.md`, `README.md`, and an `audit/`
subdirectory with the CPU-only audit, review template, and review plan. None of
these files contains source text.

## Rebuild

```bash
# Expanded pilot from pinned inputs (network on first run; cache thereafter).
python scripts/prepare_dataset.py --config configs/dataset_pilot.yaml --force

# Identical offline rebuild from the same cache and pinned local files.
python scripts/prepare_dataset.py --config configs/dataset_pilot.yaml --offline --force

# Re-audit and regenerate the deterministic review sample.
python scripts/audit_dataset.py \
  --dataset data/processed/pilot-v2 \
  --out data/manifests/pilot-v2/audit \
  --review-out data/processed/pilot-v2/review_samples.jsonl \
  --tokenizer Qwen/Qwen3.5-0.8B --max-seq-len 1024
```

The resulting `data/processed/pilot-v2/manifest.json` should match the committed
version on `dataset_version`, split counts, and split hashes. It will not match on
`created_at` or the environment fields.

The original `pilot-attack-cwe-v1` can still be rebuilt with the legacy
single-source CLI:

```bash
python scripts/prepare_dataset.py --download mitre_attack --out data/processed/_attack --force
python scripts/prepare_dataset.py --download mitre_cwe --out data/processed/_cwe --force
```

## What a manifest does not prove

- That the source text was unchanged upstream. Record the source URL and time.
- That the license analysis is correct. The license report is a starting point,
  not legal advice.
- That contamination screening caught paraphrase. It catches verbatim 13-gram
  overlap only.
- That any record was manually reviewed. The committed review plan is a plan;
  `manual_review.completed` remains false until a human records the review.

See [docs/dataset.md](../docs/dataset.md) for the schema and
[data/sources.yaml](../sources.yaml) for the registry.

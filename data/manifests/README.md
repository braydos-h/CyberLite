# Dataset manifests

Committed manifests are the public, redistributable record of a prepared corpus.
The corpus text itself stays out of version control when the upstream license
does not permit redistribution; the manifest carries the version, counts, split
hashes, license counts, and cleaning statistics so a third party can rebuild and
compare.

| Manifest | Sources | Records | Status |
|---|---|---:|---|
| [`pilot-attack-cwe-v1/`](pilot-attack-cwe-v1/) | MITRE ATT&CK, MITRE CWE | 2,006 | Pilot slice; NVD, OWASP, and system docs pending |

## Rebuild

```bash
# Explicit downloads are required; the default workflow never fetches data.
python scripts/prepare_dataset.py --download mitre_attack --out data/processed/_attack --force
python scripts/prepare_dataset.py --download mitre_cwe --out data/processed/_cwe --force

# Discovery combines the local raw inputs into one corpus.
python scripts/prepare_dataset.py --out data/processed/pilot --force
```

The resulting `data/processed/pilot/manifest.json` should match the committed
version on `dataset_version`, split counts, and split hashes. It will not match on
`created_at` or the environment fields.

## What a manifest does not prove

- That the source text was unchanged upstream. Record the source URL and time.
- That the license analysis is correct. The license report is a starting point,
  not legal advice.
- That contamination screening caught paraphrase. It catches verbatim 13-gram
  overlap only.

See [docs/dataset.md](../docs/dataset.md) for the schema and
[data/sources.yaml](../sources.yaml) for the registry.

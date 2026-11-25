# Raw data (not committed)

Place locally obtained source files here, under a subdirectory named after the
source in `data/sources.yaml`:

```text
data/raw/mitre_attack/enterprise-attack.json
data/raw/mitre_cwe/cwec_latest.xml.zip
data/raw/owasp_cheatsheets/*.md
```

CyberLite does not download sources automatically. Use an explicit command:

```bash
python scripts/prepare_dataset.py --download mitre_attack --out data/processed
```

Review the license in `sources.yaml` before downloading or redistributing. Bulk
data, model weights, and credentials are ignored by `.gitignore`.

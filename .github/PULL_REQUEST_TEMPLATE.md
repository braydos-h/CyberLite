## Summary

<!-- What does this change do, and why? -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Data or evaluation methodology
- [ ] Documentation
- [ ] Reproducibility / CI
- [ ] Safety / security hardening

## Verification

<!-- Commands run and results. Do not paste secrets or restricted data. -->

```bash
ruff check cyberlite scripts tests
pytest -m "not integration"
python scripts/validate_repo.py
```

## Evidence and limitations

<!-- If this changes a claim, config, dataset, or metric, describe the evidence and what remains unknown. -->

## Checklist

- [ ] Tests added or updated
- [ ] No model weights, secrets, or bulk/restricted data added
- [ ] Licenses and provenance documented for new data sources
- [ ] Generated commands remain non-executing
- [ ] Documentation updated
- [ ] No fabricated benchmark numbers

# Seed data

`smoke.jsonl` contains 34 original, synthetic records written for this
repository. They validate the data pipeline, chat masking, FIM encoding, and the
training/inference plumbing. They are not a representative cybersecurity corpus
and must not be presented as a benchmark.

`distill_prompts.jsonl` contains a few prompts for exercising the offline
teacher-generation script. It is not a training corpus.

`data/evaluation/smoke_eval.jsonl` contains eight disjoint synthetic evaluation
items for the harness. They are not scientific benchmark items.

Do not add real credentials, personal data, restricted benchmark items, or
third-party text here. Larger corpora are prepared locally and ignored by Git.

# Manual review template

**Status: not completed.** No human review has been recorded by the auditor.
Fill this template only after a person has read the sampled records and checked
the source evidence. Do not mark a record reviewed because an automated check
passed.

## Instructions

1. Open `review_samples.jsonl` in a local, access-controlled environment. It is
   intentionally outside Git because it contains source text.
2. Review each sample against its `url`, `source_version`, and `upstream_id`.
3. Score each field from 1 (poor) to 5 (excellent), or mark `unsure` with a note.
4. Record concrete errors, unsupported claims, unsafe guidance, or provenance gaps.
5. Do not edit the dataset splits. Report issues for a new build.
6. Aggregate results in `review_summary.json`; set `completed: true` only when
   every sampled record has a reviewer and a timestamp.

## Fields

| Field | What to check |
|---|---|
| `accuracy` | Is the technical content correct and consistent with the cited source? |
| `relevance` | Does the response answer the prompt and stay on the defensive-security task? |
| `completeness` | Are the important conditions, limitations, and verification steps present? |
| `provenance` | Do source, URL, version, license, and upstream identifiers match the evidence? |
| `safety` | Does the record avoid operational harm, credentials, and unsupported instructions? |
| `overall_quality` | Would this record be acceptable for the intended training run? |

## Record-level fields

```json
{
  "id": "...",
  "reviewer": "...",
  "reviewed_at": "YYYY-MM-DD",
  "accuracy": 1,
  "relevance": 1,
  "completeness": 1,
  "provenance": 1,
  "safety": 1,
  "overall_quality": 1,
  "notes": "Evidence and specific issue, if any.",
  "review_status": "reviewed"
}
```

## Aggregate

```json
{
  "completed": false,
  "reviewed_records": 0,
  "sample_size": 0,
  "reviewers": [],
  "accuracy_mean": null,
  "safety_failures": null,
  "provenance_failures": null,
  "notes": "Set completed to true only after the human review is finished."
}
```

# Calibration Quality Review — Agent E

Independent quality review of the CyberLite calibration synthesis split. I did
not generate the corpus and did not modify any corpus record.

- Review ledger: `data/manifests/synthesis-calibration/reviews/agent-E-quality.json`
- Calibration review inputs: `data/processed/synthesis-calibration/review/*.jsonl`
- Manifest: `data/manifests/synthesis-calibration/manifest.json`
- Dataset version: `cyberlite-syn-2.0.0-913298850f3e`
- Rubric and thresholds: `cyberlite/data/review.py`

## Scope and method

The calibration review split contains 200 records across 15 batches. I selected
50 records purposively so each required family quota was met, then read the full
prompt, response, metadata, and cited source URL for every item. Selection was
not random; it was stratified by family and domain to exercise the formats most
likely to hide quality defects.

| Required category | Quota | Reviewed |
|---|---:|---:|
| Instruction-response / technical explanation | 10 | 10 |
| Multiple-choice / multi-answer | 8 | 8 (5 single, 3 multi) |
| Secure code review / code remediation | 6 | 6 (4 review, 2 remediation) |
| Configuration analysis / completion | 6 | 6 (3 analysis, 3 completion) |
| Log interpretation / multi-turn troubleshooting | 6 | 6 (5 log, 1 multi-turn) |
| Structured JSON / comparison | 4 | 4 (2 JSON, 2 comparison) |
| Misconception / uncertainty | 4 | 4 (3 misconception, 1 uncertainty) |
| Source-derived evidence-grounded | 6 | 6 evidence-grounded (8 source-derived total) |

All 15 batches and all eight named metadata domains are represented, plus eight
source-derived records whose `domain` is null. Difficulty is 21 foundational,
20 intermediate, 8 advanced, and 1 expert. Records range from 151 to 723
metadata tokens (mean 326.4); 10 exceed 400 tokens and one exceeds 700.

I scored all eight rubric dimensions on 0–10. Decisions follow the ledger
thresholds: `accept` requires no critical finding, an average of at least 8.5,
technical accuracy of at least 9.0, and source grounding of at least 9.0 when
the record is source-dependent. Technical accuracy was judged only at the level
needed to decide usefulness; deep factual verification is Agent D's task.

## Results

### Decisions

| Decision | Count | Share |
|---|---:|---:|
| accept | 19 | 38.0% |
| revise | 24 | 48.0% |
| quarantine | 7 | 14.0% |

Two records carry `critical: true` and are quarantined regardless of score:

- `syn-language-security-retention-gen-bigo-001-codereview-1` — presented as a
  security code review but the code has no security defect; the answer reframes
  O(n²) performance as a vulnerability.
- `syn-fundamentals-linux-networking-fund-hash-vs-encrypt-compare-fund-least-privilege`
  — the prompt concatenates two unrelated topics and the answer admits they are
  not comparable, so the comparison task is incoherent.

### Mean scores

| Dimension | Mean |
|---|---:|
| technical_accuracy | 8.98 |
| source_grounding | 8.96 |
| completeness | 7.42 |
| relevance | 8.04 |
| clarity | 8.94 |
| practical_usefulness | 7.72 |
| originality_diversity | 6.16 |
| small_model_suitability | 8.22 |
| **Overall average** | **8.06** |

The pattern is consistent: records are usually clear and technically plausible,
but they lose points on completeness, practical usefulness, and originality.
Originality is the weakest dimension by a wide margin, which matches the
template repetition described below. Mean score by decision is 8.96 for
accepted records, 7.88 for revise, and 6.20 for quarantine, so the decision
boundaries are behaving as intended rather than clustering at one score.

## Recurring quality defects

These are the defects that recur across families, not one-off errors. They are
the main reason 31 of 50 records were not accepted as-is.

### 1. Verbatim template closers that sometimes contradict the task

Several families end with the same sentence regardless of content:

- Configuration analysis: "Configuration text alone does not prove the deployed
  state: check the effective configuration, confirm the file is loaded by the
  running service, and test the negative case."
- Configuration completion: "Other values may be syntactically valid but would
  not satisfy the stated purpose. After editing, reload or restart the service
  as appropriate..."
- Log interpretation: "Do not treat a single log line as proof of intent.
  Correlate it with identity, endpoint, and network telemetry..."
- Multi-answer: "The selected statements describe the mechanism or condition
  that matters; the remaining options are common misconceptions..."
- Code remediation/review: "Verify the fix with a test that exercises the
  malicious input... A fix that only blocks one payload string is not a
  root-cause remediation."
- Misconception: "Acting on the incorrect claim would lead to a false sense of
  assurance or the wrong control being applied."

The closers are not merely repetitive; they are sometimes false to the item.
The Big-O code review is told to test "malicious input" and "payload strings".
The patch-verification log is told not to treat "a single log line" as proof
when the excerpt contains four commands. The configuration items are told to
check "the deployed system" even when the task is to read a request or a policy
snippet.

### 2. Multi-answer distractors are bad practices, not false statements

In `...-s3-block-public-access-multi-answer`,
`...-gen-stacktrace-002-multi-answer`, and `...-log-k8s-verb-110-multi-answer`,
the "wrong" options are things an analyst should not do ("Relying on bucket-level
Block Public Access...", "Reading only the last line...", "Ignoring
cross-namespace access..."). They are not statements that are supported or
unsupported by evidence, so "select all that are supported" is the wrong frame.
The answer key also gives no per-option rationale, only a generic paragraph.

### 3. Evidence-grounded items are proofreading, not security reasoning

All six evidence-grounded items are the same construction: quote a source
sentence, present three near-identical options, and change one word.

- `...#69` changes SHOULD to MUST and removes a negation.
- `...#112` changes `fstatat(2)` to `fstatat(3)` and `required` to `RECOMMENDED`.
- `...#115` changes MAY to SHALL and citation year 2010 to 4020.
- `...#118` changes may to SHALL and removes a negation.
- `...#155` changes "ssh 1" to "ssh 2" and SHOULD to MUST.
- `...#157` changes React 19 to 38 and removes a negation.

The answers are verbatim copies of the correct sentence followed by a mechanical
diff. This is high source grounding but low training value: it teaches a 0.8B
model to match strings, not to understand confidentiality, access control,
ATT&CK mitigations, or XSS. `...#155` is worse because the source text contains
"ssh 1" conversion artifacts, so the item is partly typo-spotting.

### 4. Incoherent or malformed prompts from fact concatenation

`...#54` asks to compare "hashing is one-way; encryption is reversible with a
key" with "least privilege applies to services and tokens". The two topics have
no shared axis. The answer effectively says so and then writes two unrelated
summaries. `...#160` is grammatical only in fragments ("Compare cvss v3.1 base
metrics describe ... with environmental metrics are where ..."), though its two
topics are at least related.

### 5. Inference presented as observation in log items

The log family prompt explicitly asks to "distinguish observations from
inferences", but several answers state a cause as fact:

- `...#58` says the file "was copied from a home directory with cp -a preserving
  context" — the AVC line does not show how the label was applied.
- `...#166` says the "previously successful traversal pattern now returns a
  client error" — the excerpt never shows a prior success, and a 400 can come
  from many controls.
- `...#78` says "The account is being used to intercept payment discussions" —
  a reasonable hypothesis, but presented as established fact.

### 6. Off-topic supporting material merged from another subtopic

`...#79` asks why cloud audit logs must be exported, but the supporting point
opens with Chrome/Edge/Firefox SQLite browser forensics before returning to
Entra and CloudTrail retention. `...#60` and `...#59` both contain the same
generic CIA-triad essay, which is longer than the answer they are supporting.
`...#127` explains the Sigma modifier catalogue while the blank is a condition
expression.

### 7. Missing the prompt's requested "what would make this wrong" or verification

Many instruction-response prompts ask for a failure condition or verification
step. `...#5` asks for concrete CEL conditions and verification but gives
neither. `...#130` and `...#175` never state what would make the explanation
wrong. Configuration-analysis items `...#2`, `...#174`, and `...#192` substitute
the generic verification paragraph for an assumption and test specific to the
snippet.

### 8. Structured output copied instead of summarized

`...#10` is valid JSON with the exact keys, but `principle` is the guidance
paragraph copied verbatim, and the `checks` strings are long assertions that
include claims absent from the guidance. `...#148` shows the correct pattern:
short, exact extraction with no extra keys.

## Weak records

| Record | Why it is weak |
|---|---|
| `...gen-bigo-001-codereview-1` | Security review prompt, no security defect; performance reframed as vulnerability; "malicious input" boilerplate. Quarantined. |
| `...fund-hash-vs-encrypt-compare-fund-least-privilege` | Incoherent comparison of cryptography and access policy; two separate essays; template closer. Quarantined. |
| `...linux-man-pages-10426f0e9c0ebc37-claim-1` | 723-token item built around a glibc excerpt; fstatat(2) vs (3) proofreading; no security reasoning; near the 1024-token limit. Quarantined. |
| `...mitre-attack-2f6456316b4b8a60-claim-1` | Options differ by MAY/SHALL and citation year 2010/4020; no ATT&CK mitigation reasoning. Quarantined. |
| `...hunt-evidence-collection-402-triage-dialogue` | Two turns are unrelated; first turn restates the record, second is generic false-positive text; closing bullets do not answer the question. Quarantined. |
| `...forensics-cloudlogs-034-mcq-1` | Off-topic browser forensics in a cloud-retention answer. |
| `...lnx-lsm-modes-log-1` | Unsupported `cp -a` cause presented as observation in an observation-vs-inference task. |
| `...rem-verify-patch-log-1` | "Previously successful" traversal is not in the excerpt; 400 is weak evidence; generic closer mismatched. |
| `...cloud-shared-responsibility-layers-checklist` | Principle copied verbatim; "short strings" instruction violated; outside claims added. |

## Strong records

| Record | Why it is strong |
|---|---|
| `...nist-nvd-...-json` | Exact JSON extraction, correct null policy, 140-character response, no extra keys. The best structured-output exemplar in the sample. |
| `...nist-nvd-...-uncertainty` | Clearly separates what the NVD record establishes from what the ticket claims; lists the exact missing evidence and how to obtain it. |
| `...go-exec-004-codereview-1` | Correct command-injection diagnosis, correct `exec.CommandContext` fix, explains why separate argv is safe and when a shell reintroduces injection. |
| `...go-tls-005-explain` | Specific Go settings (`MinVersion`, `InsecureSkipVerify`, `RootCAs`, config cloning, handshake timeouts) and real failure modes. |
| `...forensics-prefetch-027-explain` | Concrete Windows facts plus the key limitation that absence proves little; lab-verifiable checks. |
| `...crypto-pq-migration-018-explain` | Current, specific migration guidance: Shor/Grover, FIPS 203/204/205, hybrid X25519MLKEM768, NIST IR 8547, CNSA 2.0. |
| `...forensics-memory-022-explain` | Acquisition tools, Volatility profile risk, and the "what would make this wrong" failure mode. |
| `...cloud-cloudtrail-data-events-gap-mcq-1` (`...#8`) | Clean single-answer MCQ: data events vs management events, plausible distractors. |
| `...cvss-v31-temporal-mcq-1` | Clean CVSS point: temporal metrics do not change base metrics; useful supporting detail. |

## Suitability for Qwen3.5-0.8B at 1024 tokens

The sample is mostly within budget, but the margin is thinner than the metadata
suggests. Ten records exceed 400 tokens and one reaches 723; long excerpts plus
four options leave little room for reasoning, and a 0.8B model is more likely to
pattern-match the longest option or copy the source sentence than to compare
alternatives. The best items are short, single-purpose, and answer a question
the model can verify from the prompt (`...#148`, `...#149`, `...#178`, `...#8`).
The worst items are long verbatim excerpts with one-word differences
(`...#112`, `...#155`, `...#118`), which consume context without teaching a
reusable security concept.

## Limitations

- **Sampled, not exhaustive.** Fifty of the 200 review-split records (from a
  500-record corpus) were reviewed. Selection was purposive to fill family
  quotas, not random, so the 38% acceptance rate is a signal about this sample,
  not a precise corpus-wide estimate.
- **Same-model-family reviewer.** Agent E is an LLM reviewer in the same model
  family as the generation workers. Correlated blind spots are likely: phrasing
  that looks natural to the family, and factual errors that are internally
  consistent with the same priors, may be under-detected.
- **No deep factual verification.** Accuracy was judged only to the level needed
  for usefulness. Agent D owns primary-source checking. Two items were flagged
  for time-sensitive facts (NIST IR 8547 draft status, OpenSSL 3.5 features)
  but not independently verified.
- **No execution.** Code and commands were read, not run. The code-review scores
  do not certify that the "secure" snippets compile or that the vulnerable
  snippets behave as described.
- **Single reviewer, subjective scores.** No inter-rater calibration was
  performed. A second reviewer could reasonably move borderline records by one
  point, which would change accept/revise status near the 8.5 boundary.
- **Coverage gaps.** Fill-in-the-middle records were not sampled, and only one
  multi-turn dialogue was reviewed. Chat records use a `messages` array rather
  than `prompt`/`response`, so generic tooling that assumes the completion
  schema will miss them.
- **Source text quality.** Some evidence-grounded excerpts contain conversion
  artifacts (notably "ssh 1" in the OpenSSH item). The review judges the record
  as shipped, including those artifacts, not the upstream document.
- **Scope.** This review covers quality and training usefulness only. Safety,
  privacy, licensing, and contamination are out of scope and belong to other
  reviewers.

## Recommended revisions before the next calibration pass

1. Remove or parameterize the family-level closers; make each closing sentence
   answer the specific prompt.
2. Rewrite multi-answer distractors as false statements and add one line of
   rationale per option.
3. Replace verbatim sentence-matching evidence items with paraphrase or
   application questions that require the concept, not the exact wording.
4. Enforce observation-versus-inference labeling in log items, and add a
   concrete next verification step.
5. Split concatenated comparison prompts and give both sides a shared axis.
6. Cap excerpts so the total prompt stays comfortably below 1024 tokens; prefer
   one short excerpt and three short options.
7. Use `...#148` as the structured-output exemplar and reject verbatim copies of
   the guidance.

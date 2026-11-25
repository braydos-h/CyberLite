# Calibration Quality Review v2 — Agent E

Independent quality review of the revised CyberLite calibration synthesis split
(`cyberlite-syn-2.0.0-04a21fdaa5ec`). I did not generate the corpus and did not
modify any corpus record. This review does not overwrite the v1 review.

- Review ledger: `data/manifests/synthesis-calibration/reviews/agent-E-quality-v2.json`
- v1 ledger (preserved): `data/manifests/synthesis-calibration/reviews/agent-E-quality.json`
- v1 report: `docs/reports/quality-review-calibration.md`
- Inputs: `data/processed/synthesis-calibration/review-v2/*.jsonl`
- Manifest: `data/manifests/synthesis-calibration/manifest.json`
- Dataset version: `cyberlite-syn-2.0.0-04a21fdaa5ec`

## Scope and method

The v2 review split contains 200 records across 16 batches. I selected 40
records purposively to cover the same families as v1 and to retest each of the
seven defects from the v1 report. I read the full prompt, response, metadata,
and cited URL for every item. Selection was stratified, not random.

| Category | Reviewed |
|---|---:|
| Instruction-response / technical explanation | 7 |
| Multiple-choice / multi-answer | 6 (2 single, 4 multi) |
| Secure code review / code remediation | 5 (4 review, 1 remediation) |
| Configuration analysis / completion | 5 (2 analysis, 3 completion) |
| Log interpretation / multi-turn troubleshooting | 5 (4 log, 1 multi-turn) |
| Structured JSON / comparison | 4 (2 JSON, 2 comparison) |
| Misconception / uncertainty | 3 (2 misconception, 1 uncertainty) |
| Source-derived evidence-grounded | 5 |

Coverage is 14 of 16 batches and all eight named metadata domains, plus seven
source-derived records with null `domain`. The unsampled batches are
`linux_man_pages` and `openssh_docs`; both contain only source-derived
`requirement` items, and the evidence-grounded regression described below is
already established by four other sources. Difficulty is 15 foundational, 15
intermediate, 9 advanced, and 1 expert. Records range from 188 to 481 metadata
tokens (mean 308.6, sample p95 423); none exceed 1,024.

Scores use the eight-dimension rubric and the ledger thresholds from
`cyberlite/data/review.py`: `accept` requires no critical finding, an average of
at least 8.5, technical accuracy of at least 9.0, and source grounding of at
least 9.0 when the record is source-dependent. Technical accuracy was judged
only to the level needed to decide usefulness; Agent D owns deep verification.

## Results

### Decisions

| Decision | Count | Share |
|---|---:|---:|
| accept | 17 | 42.5% |
| revise | 17 | 42.5% |
| quarantine | 6 | 15.0% |

Five records carry `critical: true`:

- `grnd-mitre-attack-mitre-attack-041884b6dc3d3cf6-requirement-1`
- `grnd-mitre-cwe-mitre-cwe-0224f8f94abee99e-requirement-1`
- `grnd-netfilter-nftables-netfilter-nftables-b4529fd9fc104be1-requirement-1`
- `grnd-owasp-cheatsheets-owasp-cheatsheets-00df144ac4ae4742-requirement-1`
- `syn-language-security-retention-js-eval-003-compare-js-npm-005`

The first four are the new evidence-grounded format applied to descriptive
sources, where the answer fabricates a MUST or SHOULD that the excerpt does not
contain. The fifth is a comparison of two unrelated controls.

### Mean scores

| Dimension | v2 mean | v1 mean | Change |
|---|---:|---:|---:|
| technical_accuracy | 8.73 | 8.98 | −0.25 |
| source_grounding | 8.70 | 8.96 | −0.26 |
| completeness | 7.45 | 7.42 | +0.03 |
| relevance | 8.20 | 8.04 | +0.16 |
| clarity | 8.88 | 8.94 | −0.06 |
| practical_usefulness | 7.90 | 7.72 | +0.18 |
| originality_diversity | 6.33 | 6.16 | +0.17 |
| small_model_suitability | 8.35 | 8.22 | +0.13 |
| **Overall** | **8.07** | **8.06** | **+0.01** |

The overall score is flat, but the composition changed. Relevance, usefulness,
originality, and small-model suitability improved slightly; technical accuracy
and source grounding fell because four evidence-grounded items now assert
normative strength that the source does not support. Mean score by decision is
8.96 for accepted records, 7.98 for revise, and 5.79 for quarantine, so the
decision boundaries separate the groups cleanly.

## Prior-defect scorecard

| # | v1 defect | Status | Evidence in v2 |
|---|---|---|---|
| 1 | Verbatim template closers that sometimes contradict the task | **Partially fixed** | Config and code closers were replaced (`...#19`, `...#20`, `...#22`, `...#23`, `...#14`, `...#16`), and the code closer is now artifact-appropriate. But the log closer ("Do not treat a single log line...") is unchanged in all four log items, the misconception closer ("Acting on the incorrect claim...") is unchanged in both misconception items, and multi-answer traded one boilerplate sentence for another. Two new closers are artifact-mismatched: Sigma verified with `kubectl` (`...#22`) and an HTTP request verified by reloading a service (`...#23`). |
| 2 | Multi-answer distractors were bad practices, not false statements | **Fixed in framing; partial in rationale** | All four sampled multi-answer items now ask "Which practices should be avoided?" and put the pitfalls in the correct set (`...#8`, `...#9`, `...#10`, `...#11`). The remaining problem is that the answer claims "Each selected practice is wrong for the reason given in the supporting point" but the paragraph does not give a per-option reason. |
| 3 | Evidence-grounded items were verbatim option proofreading | **Not fixed — regressed** | The new format works for the one IETF item with real RFC 2119 language (`...#36`: MUST-level ALPN vs proposed MAY). It fails for descriptive sources: ATT&CK (`...#37`) is said to be "recommended (SHOULD)", CWE (`...#38`) and OWASP (`...#40`) are said to be "required (MUST)", and the nftables prose (`...#39`) uses lowercase "must" as a technical precondition. In all four, the proposed behaviour is the excerpt sentence verbatim, so the answer's "No, it weakens or reverses that requirement" is self-contradictory. Four of five sampled evidence items are quarantined. |
| 4 | Incoherent comparison prompts from fact concatenation | **Partially fixed** | `...#31` (CVSS base vs environmental) is now grammatical and shares an axis. `...#32` (eval/new Function vs npm lifecycle scripts) is still not a comparison: they are different problems, not alternatives, and the answer admits "They are not interchangeable" before writing two separate essays. The shared-domain restriction did not produce a shared decision axis. |
| 5 | Inference presented as observation in log items | **Still present** | `...#25` still states the file "was copied from a home directory with cp -a" although the AVC line does not show that. `...#27` still asserts a "previously successful traversal pattern" that is not in the excerpt. `...#26` still says "The account is being used to intercept payment discussions", and `...#24` calls the finding a "signature of stolen credentials". The prompt still asks to distinguish observations from inferences. |
| 6 | Off-topic supporting material merged from another subtopic | **Partially fixed** | The sampled log answers stay on topic; the v1 browser-forensics item was not re-sampled, so that specific merge is unconfirmed. A new artifact-mismatch variant appeared: `...#22` verifies a Sigma rule with `kubectl`, `...#23` verifies an HTTP request by reloading a service, and `...#19` still treats a plain IAM policy as a permissions boundary. |
| 7 | Missing the prompt's requested "what would make this wrong" or verification | **Partially fixed** | The prompt wording changed to "assumptions and failure modes that the verification should test" or "specific settings, defaults, or failure modes". `...#3` and `...#4` answer it; `...#1` and `...#5` still do not. Config items now include a verification paragraph, but `...#19` is generic and `...#22`/`...#23` verify the wrong artifact. |

### What the generator fixed cleanly

- **Big-O/security mismatch:** the v1 Big-O code-review item is gone. The
  sampled code reviews are security-relevant (`...#14`, `...#15`, `...#16`,
  `...#17`) and the code remediation is a real CWE-1321 defect (`...#18`).
- **Comparison prompt grammar:** `...#31` is now a readable comparison question
  rather than the v1 concatenated phrase.
- **Config-completion alignment:** `...#20` and `...#21` now blank a directive
  that is actually related to the stated purpose, and the explanation names the
  line.
- **Token cap:** the corpus has zero records over 1,024 (manifest max 819, p95
  438); the sample max is 481 tokens. No sampled item approaches the limit, and
  the v1 700+ token item is not in the sample.
- **Instruction prompt wording:** the specific "what would make the explanation
  wrong" phrase is gone; the replacement asks for assumptions and failure modes.

## Remaining and new defects

### 1. Normative-strength template applied to non-normative sources (critical)

This is the top remaining defect and it is a regression, not a partial fix. The
new evidence template asks whether a proposed behaviour is supported, then
answers with a MUST/SHOULD analysis. That works only when the excerpt contains
RFC 2119 language about a deployment requirement.

- `...#37` ATT&CK excerpt: "The HISTCONTROL environment variable keeps track..."
  There is no SHOULD. The answer says "the excerpt makes this recommended
  (SHOULD)" and rejects a proposed behaviour that is the same sentence.
- `...#38` CWE-1288 excerpt: a definition of improper consistency validation.
  There is no MUST. The answer says "required (MUST)".
- `...#39` nftables excerpt: "The set setname must already exist..." is a
  technical precondition, not a normative requirement. The answer maps it to
  MUST and claims the plan weakens it.
- `...#40` OWASP excerpt: descriptive guidance. There is no MUST. The answer
  says "required (MUST)".

In each case, the proposed behaviour is verbatim from the excerpt, so the
correct answer to "is that behaviour supported?" is yes, not "No, it weakens or
reverses that requirement". A 0.8B model would learn a fabricated rule:
descriptive prose can be converted into a normative requirement by assertion.

### 2. Artifact-specific verification is not actually artifact-aware

The closers were rewritten, but the verifier is selected by template rather than
by artifact:

- `...#22` (Sigma YAML) says: "Verify with inspect the admitted object with
  `kubectl get -o yaml` and confirm `condition` survived defaulting and
  admission." A Sigma rule is not a Kubernetes object; there is no admission
  controller or defaulting step.
- `...#23` (HTTP request) says: "reload the service and read the effective value
  from the running process." There is no service configuration to reload.
- `...#20` (Dockerfile) says: "Verify with run the built image as a non-root
  user..." The grammar is broken, and the check does not test the `groupadd`
  line that was just added.
- `...#19` (IAM policy) says: "attempt the action the control is meant to
  block" without naming the action or checking that the boundary is attached.

This is the same class of defect as v1's off-topic material, but it is more
dangerous because it appears authoritative and is attached to an otherwise
correct answer.

### 3. Comparison pairs still share a domain, not a decision

`...#31` is fixed. `...#32` is not: `eval`/`new Function` and npm lifecycle
scripts both live under language security, but an engineer does not choose one
"instead of" the other. The answer admits they are not interchangeable, then
uses the same generic closer: "Choose the control that matches the asset, threat
model, and evidence you actually have, and state the assumption that would
change the decision." The pair-selection rule needs a shared decision axis, not
just a shared tag.

### 4. Multi-answer rationale still overclaimed

The framing is fixed, which is a real improvement. But the answer key says
"Each selected practice is wrong for the reason given in the supporting point",
and the supporting point is still a general paragraph. In `...#8`, the paragraph
explains the four Block Public Access switches but never says why A or C is
wrong. In `...#9` and `...#10`, the paragraph explains how to read tracebacks
and audit records but not why the selected practices fail. Only `...#11` comes
close, because its paragraph mentions DNS rebinding and alternate IP encodings.

### 5. Log and misconception templates are unchanged

The log family still ends with the generic "Do not treat a single log line as
proof of intent" sentence, even when the excerpt is four commands (`...#27`) or
a structured finding (`...#24`). The misconception family still ends with
"Acting on the incorrect claim would lead to a false sense of assurance or the
wrong control being applied" (`...#33`, `...#34`). The middle paragraphs are
still generic essays (shared-responsibility and CIA triad) rather than
item-specific reasoning.

### 6. Structured JSON still copies instead of summarizing

`...#29` still puts the full guidance paragraph in `principle`, and `checks`
contains long assertions plus outside claims (managed Kubernetes, liability
shield) that are not in the guidance. The instruction says "short strings".
`...#30` remains the correct exemplar: exact keys, 140-character response.

### 7. Multi-turn dialogue is still two unrelated turns

`...#28` is unchanged from v1. The first assistant turn describes the parse
failure but gives no concrete triage steps; the second user turn is unrelated to
the first artifact; the closing bullets do not answer the question. It remains a
quarantine.

## Weak records

| Record | Why it is weak |
|---|---|
| `...mitre-attack-041884b6dc3d3cf6-requirement-1` | Fabricates a SHOULD for descriptive ATT&CK prose; proposed behaviour is verbatim; answer says "No". Critical. |
| `...mitre-cwe-0224f8f94abee99e-requirement-1` | Fabricates a MUST for a CWE definition; proposed behaviour is verbatim. Critical. |
| `...netfilter-nftables-b4529fd9fc104be1-requirement-1` | Treats lowercase "must" in a technical precondition as RFC 2119 MUST. Critical. |
| `...owasp-cheatsheets-00df144ac4ae4742-requirement-1` | Fabricates a MUST for descriptive OWASP guidance. Critical. |
| `...js-eval-003-compare-js-npm-005` | Compares unrelated controls; answer admits "not interchangeable"; generic closer. Critical. |
| `...det-data-quality-310-triage-dialogue` | Two unrelated turns; no multi-turn reasoning; generic false-positive script. |
| `...det-sigma-modifiers-302-config-complete` | Correct condition, but verification uses `kubectl` on a Sigma rule. |
| `...cwe-306-missing-authentication-config-1` | HTTP request treated as configuration; verification says reload the service. |
| `...iam-permission-boundary-intersection-config-1` | Plain IAM policy called a boundary; generic verification. |
| `...lnx-lsm-modes-log-1` | Unsupported `cp -a` cause presented as observation. |
| `...rem-verify-patch-log-1` | "Previously successful" traversal is not in the excerpt; 400 is weak evidence. |
| `...cloud-shared-responsibility-layers-checklist` | Verbatim principle; long checks; outside claims. |

## Strong records

| Record | Why it is strong |
|---|---|
| `...go-path-002-codereview-1` | New item; correctly explains that `filepath.Join`/`Clean` does not confine, and uses `IsLocal` + `Rel` or `os.Root` for symlink-safe opens. |
| `...cwe-1321-prototype-pollution-codefix-1` | Correct CWE-1321 diagnosis and secure merge; states impact range and root cause. |
| `...nist-nvd-...-json` | Exact structured extraction; 140-character response; no extra keys. |
| `...nist-nvd-...-uncertainty` | Separates record from claim; lists the exact missing evidence and next steps. |
| `...ietf-rfcs-...-requirement-2` | The one evidence item where the normative-strength format works: proposed MAY vs excerpt MUST-level ALPN, with a real operational consequence. |
| `...forensics-memory-022-explain` | Specific acquisition detail and a real failure mode (Volatility profile mismatch). |
| `...api-jwt-claims-001-explain` | Clear signature-vs-claims distinction; concrete validation list. |
| `...go-exec-004-codereview-1` | Correct command-injection diagnosis and `exec.CommandContext` fix. |
| `...crypto-pq-migration-018-explain` | Current, specific migration guidance with checkable dates and algorithms. |
| `...lnx-sshd-config-config-complete` | Correct `AllowGroups` line; artifact-appropriate `sshd -T` verification. |

## Suitability for Qwen3.5-0.8B at 1024 tokens

The token cap is fixed: the corpus has zero records over 1,024 (manifest max
819, p95 438), and the sample max is 481 with a mean of 308.6. That is a genuine
improvement over v1's 723-token item, which is not in this sample. The remaining
small-model risk is not length but signal quality: four evidence items teach a
fabricated normative rule, and two config items teach a verifier for the wrong
artifact. A 0.8B model is likely to reproduce the template rather than notice
the mismatch. The best items are short, single-purpose, and answer a question
the model can verify from the prompt (`...#17`, `...#18`, `...#30`, `...#35`,
`...#36`).

## Limitations

- **Sampled, not exhaustive.** Forty of 200 review-v2 records (from a 500-record
  corpus) were reviewed. Selection was purposive to retest the seven v1 defects,
  not random, so the 42.5% acceptance rate is a signal about this sample, not a
  precise corpus-wide estimate.
- **Same-model-family reviewer.** Agent E is an LLM reviewer in the same model
  family as the generation workers. Correlated blind spots are likely, especially
  for template phrasing that looks natural to the family.
- **No deep factual verification.** Accuracy was judged to the usefulness level.
  Agent D owns primary-source checking. For the normative-strength items I
  checked only whether the excerpt contains a MUST/SHOULD; I did not re-fetch the
  upstream documents.
- **No execution.** Code and commands were read, not run. The code-review scores
  do not certify that the secure snippets compile or that the vulnerable
  snippets behave as described.
- **Single reviewer, subjective scores.** No inter-rater calibration. A second
  reviewer could move borderline records by one point and change accept/revise
  status near 8.5.
- **Coverage gaps.** `linux_man_pages` and `openssh_docs` were not sampled; both
  are source-derived-only batches. Fill-in-the-middle records were not sampled,
  and only one multi-turn dialogue was reviewed.
- **Evidence regression may be under- or over-represented.** Four of five sampled
  evidence items are from descriptive sources; the IETF item shows the format can
  work. The defect is systematic in the template, but the exact corpus-wide rate
  is not measured here.
- **Scope.** This review covers quality and training usefulness only. Safety,
  privacy, licensing, and contamination are out of scope.

## Recommended fixes before the next calibration pass

1. **Gate the normative-strength template on source type.** Only use it when the
   excerpt contains RFC 2119 keywords in a requirement sentence. For descriptive
   sources, use a different evidence task (paraphrase, applicability, claim
   support) and never propose a verbatim sentence as a "weakened behaviour".
2. **Make verification artifact-aware.** Define an allowed verifier per artifact
   type; reject `kubectl` for Sigma, service reload for HTTP requests, and
   process inspection for a Dockerfile line that only adds a group.
3. **Finish the config-analysis rewrite.** Require the boundary attachment check
   and an action-specific negative test, not a generic "attempt the action".
4. **Add per-option rationale to multi-answer items** or remove the claim that
   the supporting point explains each selected practice.
5. **Require a shared decision axis for comparisons.** Domain or subtopic tags
   are not enough; both controls must be alternatives for the same decision.
6. **Remove or specialize the log and misconception closers.** The current
   sentences are unchanged from v1 and sometimes contradict the artifact.
7. **Re-review every `requirement` item before acceptance.** The four critical
   quarantines show the format can produce confidently wrong answers.
8. **Keep `...#30` and `...#35` as the structured/uncertainty exemplars**, and
   reject verbatim copies of guidance in structured JSON.

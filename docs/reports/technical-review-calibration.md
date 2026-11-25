# Technical review — synthesis calibration (Agent D)

Artifact: `synthesis-calibration` · Dataset version: `cyberlite-syn-2.0.0-913298850f3e`
Ledger: `data/manifests/synthesis-calibration/reviews/agent-D-technical.json`
Sample: 50 records deliberately selected from 200 (25%), weighted toward the highest-risk families. This is **not** a random sample and does **not** cover the corpus.

## Coverage

| Primary family | Records |
|---|---|
| NVD triage / CVSS / CWE / CPE applicability (incl. 2 uncertainty and 2 JSON-extraction items) | 8 |
| CWE matching, mitigation, review questions | 7 |
| ATT&CK matching | 3 |
| RFC / OWASP / OpenSSH / man-page grounded claims | 4 |
| Secure code review / remediation | 12 |
| Configuration analysis / completion / diagnosis | 6 |
| Detection-rule interpretation (Sigma, DNS regex, K8s audit, threshold/correlation) | 4 |
| Log interpretation (GuardDuty, KQL, GPO, BEC, patch verification) | 5 |
| Misconception correction | 1 |
| **Total** | **50** |

Origin split: **22 source-derived** (NVD, CWE, ATT&CK, OWASP, OpenSSH, RFC 4251, man-pages) and **28 curated-synthetic**. All items were read in full; key claims were checked against primary sources (MITRE CWE 5.0 entries for 1253/282/681/319/611, ATT&CK v20.1 T1120 and T1218.003, the CVSS v3.1 base formula, NVD records, the Sigma 2.1.0 specification, Microsoft's Group Policy scope documentation, the AWS GuardDuty severity documentation, and the cited RFC/OWASP excerpts). Code was reviewed statically; no generated code was executed.

## Results

- **Accept: 17/50 (34%)**
- **Revise: 31/50 (62%)**
- **Quarantine: 2/50 (4%)**
- Mean overall score: **7.76/10**
- Mean by dimension: technical accuracy 8.66 · source grounding 8.58 · completeness 7.28 · relevance 7.98 · clarity 8.84 · practical usefulness 6.96 · originality/diversity 5.50 · small-model suitability 8.28
- Accepted rate by origin: source-derived **4/22 (18%)**, curated-synthetic **13/28 (46%)**.

The low originality score and the high revise rate are driven mainly by template reuse and by items whose format does not test the concept named in the prompt, not by a large number of false statements. Where records are factually sound but generic, they were marked revise rather than quarantine.

## Recurring defects

1. **Boilerplate detached from the scenario.** The same closing paragraph ("confirm the file is loaded by the running service… overridden by a more specific scope") appears on an HTTP request, an IAM policy, a STIX bundle, and a DOM-XSS diagnosis. "Parameterization or a safer API" is attached to CWE-282 ownership management and CWE-319 cleartext transmission. "A fix that only blocks one payload string" is attached to a duplicate-finding function with no input at all.
2. **Verbatim duplicate responses.** The two NVD applicability records and the two NVD uncertainty records are byte-identical, including CVE-specific claims that should differ.
3. **Degenerate "grounded claim" items.** Most source-derived claim questions are copy-selection with number/negation distractors (`2017`→`4034`, `19`→`38`, `2`→`3`). They are technically correct but train transcription, not reasoning. Several also call lowercase prose "normative keywords" and claim an RFC 2119 violation where the source has ordinary "may"/"should".
4. **Completion blanks unrelated to the stated purpose.** `cont-linux-capabilities-drop-config-complete` fills `read_only: true` for a purpose already satisfied by `cap_drop: ALL` + `cap_add: NET_BIND_SERVICE`; `api-versioning-001-config-complete` fills a request line for a deprecation-header purpose. The answer is syntactically valid but does not exercise the named control.
5. **Fabricated inferences in verification/log tasks.** `rem-verify-patch-log-1` asserts that 4.2.3-0ubuntu1 "matches the fixed build" (no fixed version is supplied) and that a traversal "previously succeeded" (no prior success is shown), then treats a 400 as proof. `auth-gpo-052-log-1` reads a `gPLink` change on the GPO container as a link addition, but `gPLink` lives on the domain/OU/site object, not the GPO object.
6. **Insecure "secure" fixes.** `api-excessive-data-001-codereview-1` fixes field exposure but leaves the endpoint without any authorization check (still an IDOR/BOLA for the returned fields), and the `User.__dict__` example is likely to raise on `_sa_instance_state` rather than leak.
7. **Source-extraction artifacts.** `Pattern: : the weakness.`, `ssh 1`/`ssh 2` instead of `ssh(1)`, duplicated metric sentences in NVD descriptions, and a non-existent "first version/second version" reference in the Go `exec` review.
8. **Detection-rule specifics not checked.** The K8s rule uses `requestObject.spec.containers.securityContext.privileged` without addressing that `containers` is an array, and the response misses the Deployment/ReplicaSet evasion and the admission-controller/Falco data source. The DNS rule response invents an aggregation window that the per-event regex does not have.

## Quarantines

- `syn-vulnerability-classification-remediation-rem-verify-patch-log-1` — fabricated verification evidence; directly contradicts the prompt's observation/inference instruction.
- `syn-language-security-retention-gen-bigo-001-codereview-1` — no security defect exists; an O(n²)→O(n) performance rewrite is presented as a "secure fix", with Wikipedia complexity pages as sources.

## Examples of good records

- `syn-vulnerability-classification-remediation-cwe-22-path-traversal-codereview-1` — correct root cause, `realpath` + `commonpath` containment, 404 handling.
- `syn-web-api-secure-development-api-jwt-kid-001-codefix-1` — correct PyJWT `get_unverified_header` use and fixed trusted-key map.
- `syn-monitoring-detection-soc-det-sigma-modifiers-302-config-complete` — correct `contains|all` semantics and condition expression.
- `syn-monitoring-detection-soc-det-threshold-correlation-305-checklist` — accurate tumbling/sliding, late-event, entity-key and duplicate-ingestion guidance in the requested JSON shape.
- `syn-language-security-retention-c-buffer-001-codefix-1` — correct `snprintf` truncation check and accurate `strncpy`/`snprintf` caveats.
- `grnd-nist-nvd-nist-nvd-00795ecd6c9525f0-json` — exact extraction; CVSS 9.8 and CWE-787 verified.
- `grnd-mitre-attack-mitre-attack-012c208a4d147578-match` and `...01d4a8ba2e991f0d-match` — correct T1120 and T1218.003 mappings, including the v20.1 "Stealth" tactic name.

## Limitations

- **Sampled, not exhaustive:** 50 of 200 records (25%), deliberately over-weighting high-risk families; no claim of full corpus coverage. Rates here should not be treated as corpus-wide estimates.
- **Same-model-family reviewer:** this review was produced by an AI reviewer (Agent D) from the same model family as the corpus generators. Shared blind spots, shared template priors, and correlated errors are possible; human adjudication is still required.
- **Static review only:** no generated code was executed; C/Go/Python/Java fixes were reasoned about, not compiled or fuzzed. Runtime claims (e.g., parser feature support, ImageMagick delegate behavior) are based on documentation and known behavior.
- **Selective verification:** key high-risk claims were checked against primary sources, but not every sentence was independently fetched. Some judgments (e.g., the GPO `gPLink` placement, ImageMagick argument injection) rely on domain knowledge of the relevant schema/tool rather than a fresh fetch in this session.
- **Scores are reviewer judgments:** the rubric has no inter-rater calibration here; `originality_diversity` and `small_model_suitability` are the most subjective dimensions.

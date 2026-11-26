# Technical review — synthesis calibration v2 (Agent D)

Artifact: `synthesis-calibration-v2` · Dataset version: `cyberlite-syn-2.0.0-04a21fdaa5ec`
Ledger: `data/manifests/synthesis-calibration/reviews/agent-D-technical-v2.json`
Sample: 40 records deliberately selected from the 200-record `review-v2` sample (itself a subset of 500 accepted). This is **not** a random or exhaustive sample; rates are not corpus-wide estimates.

## Coverage

| Primary family | Records |
|---|---|
| NVD triage / applicability / uncertainty / CVSS / JSON | 4 |
| CWE review, mitigation, matching | 4 |
| ATT&CK matching | 2 |
| Evidence-grounded normative-strength items | 8 |
| Detection-rule interpretation | 4 |
| Secure code review / remediation | 5 |
| Configuration completion / analysis | 5 |
| Log interpretation | 4 |
| Error diagnosis | 3 |
| IAM boundary analysis | 1 |
| **Total** | **40** |

Origin: **18 source-derived**, **22 curated-synthetic**.

The v2 review sample is a **mix of changed and unchanged v1 records**: of the 170 record IDs common to v1 and v2, only **51 changed**; 119 are byte-identical. My 40 items comprise 10 changed records, 21 unchanged records, and 9 new records. This matters for interpreting the revision note: an old defect appearing here proves it is still in the accepted artifact; a fix absent here may still exist only in newly generated records.

## Results

- **Accept: 10/40 (25%)**
- **Revise: 21/40 (52.5%)**
- **Quarantine: 9/40 (22.5%)**
- Mean overall score: **7.01/10**
- Mean by dimension: technical accuracy 7.25 · source grounding 7.92 · completeness 6.28 · relevance 7.30 · clarity 8.25 · practical usefulness 6.25 · originality/diversity 5.38 · small-model suitability 7.42
- By origin: source-derived **5/18 accept, 7 quarantine, mean 6.44**; curated-synthetic **5/22 accept, 2 quarantine, mean 7.47**.

The quarantine rate is driven by two clusters: the broken evidence-grounded normative items (6) and records that were named as quarantined in the revision note but remain in the accepted train split (2), plus the CWE-1253 hardware review.

## Prior defects: fixed, partial, or still present

| Prior defect | Status | Evidence in this sample |
|---|---|---|
| NVD applicability decodes vendor/product/version/`target_sw` | **Still present** | Both applicability records are byte-identical to v1; the response never decodes `version=*` or `target_sw=aem_cloud_service`/`construction`/`design_&_survey`. |
| NVD uncertainty mentions wildcard CPE limits | **Still present** | Unchanged from v1; no mention of `version=*`/`-`. |
| Exact-duplicate responses removed globally | **Partially fixed** | Only one exact duplicate group remains in 200 records, but it is the flagged NVD applicability pair. |
| CWE review questions only for software root causes | **Partially fixed** | Many `-review` records are in `quarantine.jsonl`; the CWE-1253 hardware review remains in `train.jsonl`. |
| CWE mitigation stops appending "parameterization" | **Still present** | CWE-319 and the new CWE-681 mitigation both still end with "parameterization or a safer API"; unrelated to either weakness. |
| Malformed `Pattern: : the weakness.` prefix stripped | **Still present** | Both CWE match prompts still begin with it. |
| Evidence-grounded items use weakened behaviour + normative strength | **Partially fixed** | The two IETF items correctly handle MUST→MAY. Six of eight selected CWE/man/OpenSSH/OWASP items present the excerpt **verbatim** as the proposed behaviour and answer "No, it weakens or reverses" — a direct contradiction. |
| Detection "gap" records removed; K8s replaced with hostPID scalar | **Still present** | `det-det-k8s-privileged-pod-gap` is unchanged; **no hostPID rule appears anywhere in the v2 sample**. |
| Detection interpretation distinguishes per-event from windowed | **Still present** | The DNS regex item still says "evaluated over the events in the stated window"; the rule has no window. |
| Error diagnosis gives a distinguishing check | **Partially fixed** | Bodies now contain fact-specific detail (GCM 2^32, CWE-770/400, GuardDuty regions), but the "check" is still identical config-load boilerplate; the JS DOM-XSS second cause is still wrong. |
| Config completion restricted to directive-like configs and tied to purpose | **Partially fixed** | API versioning is fixed (`Deprecation` header). Capabilities still fills `read_only`, systemd still fills unrelated `ProtectHome`, and CVSS uses a one-line `text` block. |
| Named quarantined facts removed from the accepted corpus | **Still present (3 of 4)** | `rem-verify-patch-log-1`, `api-excessive-data-001-codereview-1`, and `auth-gpo-052-log-1` are still in `train.jsonl` and in `review-v2` with unchanged text. The `gen-bigo-001` codereview is gone, but its explain/multi-answer siblings remain. |
| Verification boilerplate matched to scenario | **Partially fixed** | IAM now says "policy simulator"; STIX now gets IAM policy-simulator language, Sigma gets `kubectl ... defaulting and admission`, and CVSS gets "reload the service". |
| Token budget: 500 accepted, p95 438, 0 over 1,024 | **Verified** | Manifest: accepted 500; p95 438; max 819; `over_limit: 0` at 1,024. |

## Most important remaining defects

1. **Evidence-grounded regression (6/8 items).** `CWE-1288`, `CWE-291`, both OpenSSH items, the OWASP malformed-XML item, and the man-pages group item all present a "Proposed behaviour" that is **verbatim identical** to the excerpt, then answer "No ... weakens or reverses that requirement". The CWE-291 item calls a sentence about attacker sniffing "required (REQUIRED)". The OpenSSH/man/OWASP answers treat lowercase descriptive prose as RFC 2119 keywords. This is the single largest new defect cluster.
2. **Named quarantines are still in the accepted corpus.** `rem-verify-patch-log-1` still fabricates a "fixed build" match and a "previously successful" traversal; `api-excessive-data-001-codereview-1` still labels an endpoint with no authorization check "SECURE"; `auth-gpo-052-log-1` still reads a `gPLink` change on the GPO container as a link addition even though `gPLink` lives on the domain/OU/site SOM. They are absent from `quarantine.jsonl` and present in `train.jsonl`.
3. **Detection fixes were not applied.** The K8s privileged-pod rule still uses the array-valued `requestObject.spec.containers...privileged` path and still misses Deployment/ReplicaSet creation; the named replacement (hostPID scalar rule) does not exist in the sample. The DNS item still invents a window for a per-event regex.
4. **NVD applicability/uncertainty unchanged.** Neither record decodes the CPE that the prompt supplies; both applicability records remain byte-identical.
5. **CWE mitigation and prompt artifacts unchanged.** "Parameterization" is still appended to CWE-319 and CWE-681; `Pattern: :` is still present.
6. **Config-completion is only partly fixed.** `read_only: true` and `ProtectHome=yes` are valid directives but do not achieve the stated purposes; the CVSS "text configuration" has no directive and any vector would pass; the verifiers are copied from unrelated domains.
7. **Error-diagnosis checks remain generic.** The body may name 2^32 or CWE-400, but "confirm the service loaded the configuration" does not distinguish the two causes. The JS DOM-XSS item still says `innerHTML = ''` is a cause of the security property failing, which it is not.
8. **Code-review artifacts persist.** `go-exec` still says "the first version/the second version" for a single-version prompt and still passes attacker-controlled input to ImageMagick `convert` without `--`; `c-offbyone` still calls the `i <= rows` write an unconditional one-byte overflow.

## Examples of good records

- `grnd-ietf-rfcs-...-04baffe38ea43c4e-requirement-2` and `...-0b055e6e1bb95a59-requirement-2` — genuine MUST→MAY weakening, correctly quoted.
- `grnd-nist-nvd-nist-nvd-00795ecd6c9525f0-json` — exact extraction; CVSS 9.8 and CWE-787 verified.
- `grnd-mitre-attack-mitre-attack-012c208a4d147578-match` / `...01d4a8ba2e991f0d-match` — T1120 and T1218.003 correct, including v20.1 "Stealth".
- `syn-monitoring-detection-soc-det-threshold-correlation-305-checklist` — accurate tumbling/sliding, late-event, entity-key and duplicate guidance.
- `syn-vulnerability-classification-remediation-cwe-22-path-traversal-codereview-1` — correct containment fix and improved regression-test wording.
- `syn-language-security-retention-c-buffer-001-codefix-1` — correct `snprintf` truncation check.
- `syn-web-api-secure-development-api-versioning-001-config-complete` — the completion now targets the Deprecation header and matches the Sunset date.
- `syn-incident-response-forensics-threat-intel-ir-bec-009-log-1` — accurate Exchange audit fields and BEC containment.

## Limitations

- **Sampled, not exhaustive:** 40 of the 200-record v2 review sample, deliberately weighted to prior defect families; no claim of full coverage and no corpus-wide rate estimate.
- **Mixed-vintage sample:** only 51 of 170 common IDs changed between v1 and v2, so this sample cannot prove the new generator never produces a fixed record; it can and does prove that the accepted artifact still contains the old defects.
- **Same-model-family reviewer:** Agent D is an AI reviewer from the same model family as the corpus generators; correlated blind spots are possible and human adjudication is still required.
- **Static review only:** no generated code was executed; runtime claims are reasoned from documentation. Primary checks were against CWE 5.0, ATT&CK v20.1, the CVSS v3.1 formula, NVD records, the Sigma 2.1.0 specification, Microsoft Group Policy scope documentation, and AWS GuardDuty severity documentation.
- **Spot checks outside the ledger:** the `gen-bigo-001` explain/multi-answer siblings were read but not scored; they remain off-domain general-retention items rather than the flagged codereview defect.

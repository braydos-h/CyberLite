# Dataset expansion architecture and gap analysis

Status: proposal for review. No file outside this report was changed and no
training run was made.

Labels: **[measured]** = re-derived from an artifact in this checkout, with its
path; **[computed]** = arithmetic on measured values; **[proposed]** = a design
decision with no evidence yet. Nothing is an estimate unless it says
**estimated**.

## 1. Measured baseline

### 1.1 Volume, splits, rejection

From `data/manifests/pilot-v2/manifest.json` and
`data/manifests/pilot-v2/audit/audit.json`:

| Metric | Value |
|---|---:|
| Normalized inputs / accepted / rejected | 7,724 / 7,188 / 536 |
| Duplicates removed (exact / near / cross-source) | 0 / 417 / 0 |
| Quality rejections (repeated lines / PII / link-heavy) | 119 (77 / 28 / 14) |
| Train / validation / test | 6,351 / 416 / 421 |
| Group split violations / cross-split leakage | 0 / 0 |
| Missing provenance (url, version, license, task, upstream id) | 0 |

Record shapes **[measured]** from the three split files: 7,152 `completion`, 36
`chat`, **0 `fim`**, **0 multi-turn**. The 36 chat records are exactly
`data/seed/project_examples_v1.jsonl`.

### 1.2 Task distribution

Nineteen `task` values; counts from the manifest and confirmed on the splits
**[measured]**:

| Task | n | Task | n |
|---|---:|---|---:|
| vulnerability | 2,615 | permissions | 93 |
| documentation | 1,467 | ssh | 82 |
| weakness | 906 | logging-monitoring | 73 |
| attack-technique | 712 | system-hardening | 68 |
| secure-coding | 504 | system-administration | 48 |
| defensive-control | 247 | incident-response | 6 |
| tls | 141 | vulnerability-remediation | 6 |
| dns | 109 | detection-engineering | 6 |
| networking | 95 | log-analysis | 6 |
| | | cryptography | 4 |

Max/min ratio is **653.75** (`audit.json` `task_imbalance`, marked unbalanced).
Six categories have exactly six records, all from the seed file. Three categories
hold 4,988 records, **69.4% [computed]**.

### 1.3 Domain coverage

There is no `domain` field, so the pilot cannot report domains. As a proxy I
measured concept mentions in accepted responses **[measured]**; these are mention
rates, not coverage:

| Concept | n | Share |
|---|---:|---:|
| Windows / AD / Kerberos / Sysmon | 202 | 2.8% |
| Cloud (AWS/Azure/GCP/S3/K8s) | 209 | 2.9% |
| Identity (MFA/OAuth/SAML) | 236 | 3.3% |
| Cryptographic primitives | 163 | 2.3% |
| Threat modeling / trust boundaries | 117 | 1.6% |
| Forensics / evidence handling | 110 | 1.5% |
| Kubernetes specifically | 68 | 0.9% |
| Sigma or YARA | 3 | 0.04% |

The corpus is Linux- and documentation-centric because its sources are: 30
allowlisted man pages, two OpenSSH pages, one nftables page and ten RFCs in
`configs/dataset_pilot.yaml`.

### 1.4 Difficulty proxy

Applied to all 7,188 records **[measured]**: L1 = answer <300 tokens with no
artifact and no procedure; L2 = artifact present, or 300–700 tokens, without a
procedure; L3 = >700 tokens or a numbered procedure. Result **L1 2,498 (34.8%),
L2 4,160 (57.9%), L3 530 (7.4%)**. Only 482 records (6.7%) contain a fenced code
block, 1,184 (16.5%) inline code, and 134 (1.9%) a numbered procedure. NVD
dominates L2 only because its template emits severity, dates and references.

### 1.5 Token statistics at 1,024

Manifest, Qwen3.5-0.8B tokenizer, no packing: p50 373, p90 616, p95 798, p99
1,539, max 3,474, mean 395.26; 216 records (3.01%) exceed 1,024. My recount with
`apply_chat_template` gives p50 371 / p95 796 / p99 1,537 / max 3,473 — within two
tokens, so the manifest stands.

Per source **[measured]**, rendered prompt+answer:

| Source | n | answer p50 | answer p95 | prompt p50 | >1,024 |
|---|---:|---:|---:|---:|---:|
| openssh_docs | 28 | 1,407 | 1,747 | 35 | 71.4% |
| ietf_rfcs | 393 | 378 | 1,410 | 48 | 16.3% |
| linux_man_pages | 246 | 281 | 1,542 | 34 | 12.2% |
| mitre_cwe | 906 | 268 | 1,082 | 32 | 5.8% |
| owasp_cheatsheets | 1,965 | 153 | 676 | 27 | 2.0% |
| mitre_attack | 959 | 263 | 577 | 29 | 0.3% |
| nist_nvd | 2,615 | 403 | 591 | 56 | 0.2% |
| project_examples | 36 | 244 | 328 | 15 | 0.0% |

Supervised token share is **90.0% [measured]**: prompts are 15–56 tokens at the
median, so almost every token is an answer. That is a recitation objective, not an
instruction objective.

### 1.6 Template concentration

Replacing CVE/CWE/T/RFC ids, quoted section names and parentheticals with
placeholders yields 435 prompt skeletons for 7,188 records **[measured]**. The
top skeleton covers 2,615 records (**36.4%**); top 2 = 57.6%, top 4 = 79.4%,
**top 5 = 84.7%**, top 10 = 89.7%. Targets show extraction: **2,673 responses
(37.2%)** begin with a copied Markdown heading, **2,793 (38.9%)** contain a
"further reading / references" block, and 205 contain raw `<code>` HTML residue.
The corpus trains "emit the next section", not "answer a question".

### 1.7 Sources, licenses, redistribution

| License | n | Share |
|---|---:|---:|
| Public-Domain (NVD) | 2,615 | 36.4% |
| CC-BY-SA-4.0 (OWASP) | 1,965 | 27.3% |
| MITRE-ATTACK / MITRE-CWE | 959 / 906 | 13.3% / 12.6% |
| IETF-Trust | 393 | 5.5% |
| Linux-man-pages-* | 228 | 3.2% |
| GPL-* | 64 | 0.9% |
| Synthetic | 36 | 0.5% |
| OpenSSH | 28 | 0.4% |

`data/sources.yaml` marks only `nist_nvd` and `project_examples`
`redistributable: true`; together **2,651 records (36.9%)**. The other **63.1%
cannot be redistributed**, so a publishable expansion must be authored rather than
re-extracted.

### 1.8 Contamination and review

The 13-gram index holds 241,515 n-grams from SecEval (2,182 items, 240,755
n-grams), the 36-item project probe (594) and the 8-item smoke set (166), with
zero removals. CyberSecEval is registered but absent: unmeasured, not zero. The
36 probe items yield **16.5 n-grams per item [computed]**, so a 13-word window
rarely fits inside a 25-word MCQ stem; short-item screening is weak. Manual review
is at zero of 200 samples, and 505 records (7.0%) carry an unsupported
absolute-claim warning that no gate resolves.

### 1.9 Coverage gaps

1. **No task diversity:** zero MCQ, preference, multi-turn, FIM, JSON extraction,
   grounded-with-evidence, uncertainty, patch or localization records.
2. **No application-level skill:** 6.7% of records contain code; only 6
   project-authored secure-coding records exist.
3. **No operational artifacts:** 1.9% procedures; Sigma/YARA in 3 records; no log
   with a labeled verdict.
4. **Domain holes:** Windows/AD, IAM, cloud/container, forensics and threat
   modeling are each under 4% by mention and under 1% by authored content.
5. **Evaluation cannot support a claim:** 24 MCQ probe items give a 95% CI
   half-width near ±20 points at p=0.5 **[computed]**; a 5-point effect is
   unmeasurable, and no suite covers grounded QA, extraction, uncertainty or FIM.
6. **Licensing blocks publication:** 63.1% non-redistributable, 0.5% synthetic.
7. **Nothing is human-verified.**

### 1.10 In-flight scaffold

An uncommitted scaffold appeared in this checkout during analysis:
`cyberlite/data/synthesis.py`, `cyberlite/data/build_synthesis.py`,
`scripts/synthesize_dataset.py`, and `data/synthesis/` with JSON Schemas for
knowledge packs and 11 evaluation suites. `build_synthesis.py` already declares
stage targets 500 / 5k / 25k / 50k / 100k and a semantic dedup threshold of 0.88.
Its `task_family` values are **format names** (instruction-response,
multiple-choice, misconception-correction, preference-pair, log-interpretation,
multi-turn-troubleshooting, command-explanation, configuration-analysis,
secure-code-review, code-remediation, structured-json, fill-in-the-middle,
comparison). That collides with the capability-family axis below: a single
`fact_id` there feeds many formats under one `synthesis:<domain>:<id>` group, which
is the right leakage behaviour. Reconcile the naming before Stage 0 — either
rename that field to `format` or adopt its 13 labels and add capability as a
second field.

## 2. Proposed taxonomy

No canonical 22-family list exists in the repository, so this is the definition
used here. A family is a capability; format (chat, completion, FIM, MCQ,
preference, multi-turn) is a separate axis.

### 2.1 Domains

| ID | Domain | Subtopics |
|---|---|---|
| D1 | vulnerability-management | advisories, CVSS, CWE mapping, exposure, risk acceptance |
| D2 | secure-coding | injection, authn/session, crypto, files, deserialization, supply chain |
| D3 | detection-engineering | behavior-to-ATT&CK, Sigma/YARA/regex, false positives, coverage |
| D4 | log-and-telemetry | auth, web/proxy, EDR, cloud audit, DNS, field mapping |
| D5 | network-and-protocols | TCP/IP, TLS/PKI, DNS, HTTP, SSH, segmentation |
| D6 | linux-host | permissions, systemd persistence, namespaces, auditd, packages |
| D7 | windows-and-identity | AD/Kerberos, GPO, event IDs, Sysmon, MFA/OAuth/SAML |
| D8 | incident-response | triage, containment, evidence, timeline, retrospective |
| D9 | cloud-container-supply-chain | IAM policy, storage, Kubernetes, SBOM, CI/CD |
| D10 | threat-modeling-architecture | trust boundaries, STRIDE, controls, residual risk |

### 2.2 Families and counts

Counts are **[proposed]** and each column sums exactly to its build size.

| # | Family | Domain | 25k | 50k | Rationale |
|---|---|---:|---:|---:|---|
| 1 | factual_recall | D1–D5 | 1,250 | 1,750 | Factual floor; already over-supplied, so capped |
| 2 | concept_explanation | all | 1,500 | 2,250 | Zero-shot explanation; grows sublinearly |
| 3 | misconception_correction | all | 1,000 | 2,000 | Targets confident-wrong answers; doubles |
| 4 | vulnerability_triage | D1 | 1,750 | 3,000 | Highest-volume operator task |
| 5 | weakness_mapping | D1/D2 | 1,250 | 2,000 | Turns CWE text into decisions |
| 6 | remediation_planning | D1/D2 | 1,750 | 3,500 | Biggest behavioral gap: ordered action |
| 7 | risk_prioritization | D1/D9 | 1,250 | 2,500 | Exposure and residual risk |
| 8 | secure_code_generation | D2 | 1,750 | 3,500 | Sinks with a syntax gate |
| 9 | vulnerability_localization | D2 | 1,500 | 3,000 | Find the defect; high marginal gain |
| 10 | patch_generation | D2 | 1,000 | 2,500 | Hardest to author; grows 2.5× |
| 11 | configuration_hardening | D5–D7 | 1,250 | 2,500 | Parser-verifiable configs |
| 12 | log_analysis | D4 | 1,500 | 3,000 | Synthetic logs with labeled readings |
| 13 | detection_rule_authoring | D3 | 1,250 | 2,500 | Parseable rules over synthetic events |
| 14 | alert_triage | D3/D4 | 1,000 | 2,500 | Benign/malicious with FP pressure |
| 15 | telemetry_mapping | D3/D4 | 1,000 | 2,000 | "Which sensor sees this"; small-model friendly |
| 16 | incident_response | D8 | 1,250 | 2,500 | Ordering, evidence, authority |
| 17 | threat_modeling | D10 | 750 | 1,500 | Thin but necessary |
| 18 | protocol_network_analysis | D5 | 500 | 1,000 | Keep only if probe gains appear |
| 19 | grounded_qa_citation | all | 750 | 2,000 | Evidence in, cited answer out |
| 20 | structured_extraction_json | D1/D4 | 250 | 1,000 | Grows 4× once the parser gate proves out |
| 21 | uncertainty_escalation | all | 250 | 1,000 | Rare by design (≤4% of tokens) |
| 22 | code_completion_fim | D2/D3/D6 | 1,250 | 2,500 | Feeds Phase 3; separate run |
| | **Total** | | **25,000** | **50,000** | |

Knowledge share is 15.0% of records at 25k and 12.0% at 50k; the largest family is
7.0% at both sizes. Growth is deliberately non-uniform: definitional families
1.4–2.0×, procedural and grounded families 2.0–4.0×. Target domain token shares
**[proposed]**: D1 20%, D2 22%, D3+D4 18%, D5+D6 15%, D7 8%, D8 6%, D9 6%, D10 5%.
A domain above 25% is a build failure, not a warning.

## 3. Schema and adaptor design

### 3.1 Compatibility constraints

`cyberlite/data/schema.py` rejects unknown top-level fields (`allowed`, line 112),
and `tests/test_data_schema.py:59` asserts that; `to_dict` emits a fixed key set;
`validate_record` requires chat to end with an assistant turn, FIM to have a
non-empty `middle`, completion to have non-empty `prompt` and `response`;
`metadata` is the only free-form extension point; `splits.record_group` reads
`metadata.group` first; `integrity.py:358` accepts `dataset_schema` 1 or 2 only.
Therefore **add no top-level fields and do not bump `dataset_schema`**; add a
namespaced metadata block and `taxonomy_version` to the manifest options.

Required metadata keys for every new record: `group`, `schema_version`,
`taxonomy_version`, `domain`, `subtopic`, `task_family`, `difficulty`, `format`,
`provenance_class` ∈ {primary_source, derived, authored}, `author_model`,
`review_status`, `source_version`, `upstream_id`. `provenance_class` is what lets
a report separate extracted text from written text.

### 3.2 Format representation

| Format | Shape | Extra metadata | Validation | Group |
|---|---|---|---|---|
| MCQ | chat/completion; choices in prompt, answer+rationale in target | `mcq.choices`, `mcq.answer` (indices), `mcq.letters`, `mcq.rationale`, `mcq.option_seed` | ≥3 unique choices; indices in range; letters match indices; rationale ≥40 chars and ≥30% content-word overlap with the keyed choice; letter balance χ² p>0.01 | `fact:<id>` |
| Preference pair | two records, chosen and rejected | `preference.pair_id`, `.role`, `.criterion`, `.defect`, `uses:["dpo"]` | shared prompt and group; chosen ≠ rejected; both structural | `pref:<pair_id>` |
| Multi-turn | chat ≥3 messages, alternating | `turns`, `final_turn_intent` | alternates, starts user (or system+user), ends assistant, each earlier assistant turn ≤80 tokens | `fact:<id>` |
| FIM | `prefix`/`suffix`/`middle` | `language`, `fim.origin`, `fim.site` | middle ≤256 tokens; prefix+suffix ≤768; middle not a substring of prefix | `code:<snippet_id>` |
| Grounded QA | chat; evidence in prompt | `evidence.doc_id`, `.spans[{start,end,quote}]`, `.license`, `.url` | each quote an exact substring; each citation resolves to a span; answer ≤350 tokens; evidence ≤450 | `evidence:<doc_id>` |
| JSON extraction | completion, exactly one JSON value | `extraction.schema_id`, `.input_kind` | `json.loads` succeeds; validates against the named schema; no prose wrapper; string values are substrings of the input | `record:<source_id>` |
| Uncertainty | chat | `uncertainty.label` ∈ {answerable, insufficient_evidence, out_of_scope, needs_authorization}, `.missing_fact` | non-answerable targets name the gap and ask or escalate; no definitive claim; paired variants share a group | `fact:<id>` |
| Evaluation item | separate JSONL, never a `Record` | `id`, `suite`, `domain`, `task_family`, `difficulty`, `references` | `data/synthesis/eval/_schema.json` (11 suites); unique id; answer resolvable; `evaluation_only: true` | `eval:<id>` |

Two limitations must be written down, not hidden. **No per-turn masking:**
`training/dataset.py::_assistant_char_spans` supervises every assistant turn, so
multi-turn context turns become targets; keep them short and correct. **Global
quality floors mis-fit short formats:** `QualityThresholds.min_response_chars`
defaults to 120 (config uses 120), which can reject a valid one-line JSON
extraction; add `quality_by_family` overrides (MCQ 60, extraction 40, uncertainty
80, FIM already exempt) instead of lowering the global floor.

### 3.3 Grouping and leakage

Groups must be content-derived: `fact:<fact_id>` for every format variant of one
authored fact (so an MCQ cannot be "unseen" while its explanation is in train);
`<source>:<document>:<heading>` for extracted sections; `pref:<pair_id>`;
`evidence:<doc_id>`; `code:<snippet_id>`. Beyond
`group_split_violations`, add: a **fact-overlap check** (content-word Jaccard ≥0.6
between a test and a train record in the same family is a leak — SimHash-3 misses
this on short answers); a **group size cap** (no group >0.5% of its family;
`ietf_rfcs:RFC8446` currently holds 102 records, 26% of the RFC slice); and a
**cross-format check** that no format of a test-group fact appears in train.

## 4. Quality gates and acceptance

### 4.1 Mechanically checkable (blocking)

- **Schema:** JSONL parses; `Record` validates; metadata block validates against a
  JSON Schema in `data/synthesis/`; `task_family`/`domain`/`difficulty` in the
  controlled lists.
- **Answer integrity:** MCQ index/letter agreement, rationale overlap, preference
  pair consistency — misaligned labels are the most damaging synthetic error.
- **Evidence integrity:** quoted span is a substring; citations resolve;
  extraction values are substrings of the input. This turns grounding from a claim
  into a check.
- **Syntax:** Python `ast.parse`; shell `sh -n`; YAML/JSON `safe_load`/`loads`;
  Sigma has `title`/`logsource`/`detection`/`condition`. **Parsed only, never
  executed.**
- **Secrets/PII:** existing `assess_record` findings plus a synthetic-identifier
  allowlist (10.0.0.0/8, 192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24,
  2001:db8::/32, `*.example.internal`, `host-01`); reject real routable addresses.
- **Dedup:** exact + SimHash-3 globally, plus normalized Jaccard ≥0.8 within
  family (SimHash is noisy below ~100 words).
- **Length:** chat/FIM rendered p99 ≤1,024 and hard reject >1,024; FIM ≤768;
  evidence ≤450; JSON output ≤200.
- **Contamination:** 13-gram ≥0.20 for records ≥120 words; **5-gram ≥0.30 for
  records <120 words**, which closes the short-item hole.
- **Split:** zero group violations, zero SimHash leakage, zero fact overlap.
- **License:** allowlist plus the evaluation-only guard in
  `cyberlite/data/licensing.py`.
- **Distribution:** family count within ±5% of plan (25k/50k) or ±10% (5k);
  knowledge ≤20% of tokens; domain ≤25%; MCQ ≤10%; no prompt skeleton >8%.
- **Balance:** MCQ letter χ² p>0.01; no family with >60% of one difficulty label.
- **Determinism:** two runs from the same inputs produce identical split hashes.

### 4.2 Needs independent review

Factual correctness against the cited primary source and version; whether the
"secure" snippet is secure and the "vulnerable" one exploitable in that context;
whether a rule fires on the event and stays quiet on the benign lookalike; whether
a refusal is calibrated rather than evasive; whether a procedure is safe, ordered
and complete; whether evaluation items are fair and genuinely unseen.

### 4.3 Rubric

Score 1–5 on accuracy, groundedness, specificity, safety, calibration and clarity,
extending `REVIEW_FIELDS` in `cyberlite/data/audit.py`. A 5 is version-specific and
traceable to the source; a 3 is mostly right with one vague claim; a 1 is wrong,
invented, or unsafe. Accept a build when accuracy and overall means are ≥4.0, no
accepted record scores accuracy ≤2, groundedness mean is ≥4.0 for families 19–21,
and there are zero safety=1. Double-review 10%; target Cohen's κ ≥0.6 on accuracy.
κ below 0.6 is a rubric defect and blocks the next stage.

### 4.4 Quarantine policy

**reject** = structural, license, secret, leakage or safety failure; never enters a
split. **quarantine** = plausible but unresolved (ambiguous answer, unsupported
absolute claim, unverified citation, unreviewed); frozen in `quarantine.jsonl` and
excluded. **warn** = style or minor provenance gap; reported and kept. Quarantine
is never deleted silently; a build fails if the rate exceeds 15% or any reason code
more than doubles versus the previous build; a record leaves only with a reviewer
id, timestamp and new content hash, never by editing a frozen file.

## 5. Staged plan

**Stage 0 — calibration, 500** (22 families × ~22). Purpose: prove generator,
adaptors, validators and review on a readable corpus. Gates: 100% schema/license
pass; quarantine ≤5%; near-dup <2%; ≥60% unique prompt skeletons and none >5%;
p50 220–420 tokens, p99 ≤1,024, zero over; MCQ χ² and rationale overlap pass;
evidence and extraction checks 100%; **all 500 read by a person**, accuracy mean
≥4.0, zero safety=1, κ ≥0.6 on 50 double-reviewed; base-model accuracy on a
100-item authored probe between 25% and 70% (above is trivial, below is ambiguous
or broken). Any failure: fix the generator, rebuild 500, do not scale.

**Stage 1 — 5k.** Purpose: learnability at 0.8B. Family counts ±10% of 8% of the
25k plan; knowledge ≤25% of tokens; contamination 0 with the 5-gram rule; 500
reviewed, κ ≥0.55, accuracy ≥3.8. Train a short adapter: primary-suite gain ≥8
points over base with a CI excluding 0, retention loss ≤3 points. Below 8 points
is a mixture or format problem, not a volume problem.

**Stage 2 — 25k.** Production build. All gates, plus: eval authors disjoint from
training-pack authors (checked by author ids); probe ≥400 items, CI half-width
≤5 points; per-family review mean ≥4.0; no family >12% of tokens; 100%
redistributable or non-redistributable flagged with a documented distribution
plan; identical hashes across two builds. Ablation: a knowledge-only control at
matched tokens must underperform the mixture on procedural suites.

**Stage 3 — 50k.** Scale test. 25k must beat 5k by ≥3 points or stop and fix the
mixture. Per-family marginal value: <1 point freezes the family at its 25k count.
Review 1,000 with κ ≥0.6; CyberSecEval screened or the blocker restated.

**Feedback loop.** Each build emits a family scorecard (yield, top quarantine
codes, review means, token stats, skeleton diversity, probe delta). Next
allocation: high yield + no gain → cut 30%; quarantine >10% → rewrite the
generator, do not add volume; two builds with no gain → freeze and record a
negative result.

## 6. Mixture and curriculum at 1,024 tokens

Sample by **tokens, not records**: measured family lengths differ 10× (OWASP p50
153, OpenSSH 1,407), so record-proportional sampling misstates the mixture.

Caps per epoch **[proposed]**: knowledge families ≤18% of tokens; any family
≤10%; any domain ≤25%; any upstream source ≤15%; MCQ ≤10%; FIM ≤8% in a separate
run; preference pairs 0 in SFT; uncertainty ≤4%; minimum per family 1.5%, below
which drop the family rather than starve it.

Two phases: **A (70% of steps)** broad mixture at roughly 55/45 L1-L2/L3, every
family at its floor; **B (30%)** procedural ×1.6 (6, 9, 10, 12, 13, 14, 16),
grounded/uncertainty ×1.3 (19, 21), definitional ×0.6 (1–3). Avoid strict
easy→hard annealing: at 0.8B with 1,024 tokens a hard-only final phase produces
brittle format following and measurable forgetting, while a fixed two-phase
mixture is reproducible and ablatable.

Four anti-definition mechanisms: the caps above, enforced in the sampler rather
than the loss; a **pairing rule** (every definitional record pairs 1:1 with an
applied record from the same fact group; >1.2:1 fails); a **prompt-length floor**
(p50 60–120 prompt tokens, supervised share 60–75%; today 15–56 and 90.0%); and
the **skeleton gate** (no skeleton >8%, top-10 ≤40%; today top-5 is 84.7%).

Sequence plan: at 1,024 with mean ~420 tokens, record-per-step wastes ~60% of each
window. Pack to 1,024-token blocks with boundary-respecting masks, about 10,300
steps per epoch for 25k records (~10.5M tokens) **[estimated from the measured
mean]**. Never pack across multi-turn or grounded boundaries. Use `drop` for chat
and grounded, `truncate` for FIM, and report discards; target >0.5% truncation.

## 7. Risks and limitations

**Template repetition** is structural: top-5 skeletons are 84.7% of the pilot. A
generator with one shape teaches skeleton→recital and fails on unseen phrasing.
Use ≥8 templates per family with different intents, keep the skeleton gate, and
hold out an unseen-phrasing suite.

**Same-model authoring and review** correlates errors, so review measures
self-consistency. Use different model, prompt and seed for review; show the
reviewer only the item and the primary reference; adjudicate disagreements with a
human; record `author_model` and whether review was human or model. Never write
"verified" for model review.

**Licensing** is the hardest constraint: 63.1% of accepted records are
non-redistributable and 0.5% synthetic. Original prose over cited facts is the
only publishable path, and authoring is not a license bypass — a fact restated
from copyleft text still needs a terms review. Open questions stay open: whether a
derived corpus or model is a derivative work (already recorded for ATT&CK, CWE,
OWASP), CC-BY-SA share-alike, GPL man pages, and teacher-model terms.

**Contamination coverage** is three local files and no CyberSecEval. The largest
new risk is evaluation items authored from the same fact packs as training: the
leak is semantic and no n-gram screen sees it. Separate fact namespaces, isolate
`eval_authored/`, run the 5-gram screen, and assert that no `fact_id` appears in
both train and eval.

**Evaluation independence and power:** a 24-item probe has a CI half-width near
±20 points; 400 items get to ~±5. MCQ still rewards test-taking, so add
grounded-QA token F1, false-positive rate on benign alerts, and refusal rate. Do
not publish a composite score.

**Capacity and sprawl:** 22 families may exceed a 0.8B model. The 5k and 50k gates
are designed to find this; expect 12–16 to survive. A documented negative result
beats a balanced-looking corpus that teaches nothing.

**Inherited blind spots:** the generator's misconceptions become the model's;
version drift is invisible unless the version is in the record; English-only,
Linux-heavy coverage persists unless D7 and D9 are authored deliberately. Track
domain share per build.

**A gap this plan does not close:** there is no general-domain retention set, so
catastrophic forgetting (G2) cannot be measured. Add a small permissive retention
set (~1,000 items, ~2% of tokens) or drop the claim until measurable.

## 8. Open decisions

1. Is this 22-family list the intended one? A different canonical list changes the
   counts before Stage 0.
2. Redistributable corpus (authoring only) or research-only (extraction allowed)?
   This sets the license budget and review burden.
3. Who reviews? Without a human reviewer the corpus ships only as "AI-assisted,
   unreviewed", and the 25k gate cannot pass.
4. Is CyberSecEval obtainable before Stage 2? If not, carry a named blocker rather
   than a zero.

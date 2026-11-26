# ML Training Review — Agent I

Independent training review of the CyberLite synthesis calibration corpus for a
Qwen3.5-0.8B, 1,024-token SFT run. I did not train a model, did not modify the
corpus, and did not modify training code or configs.

**Measured snapshot:** `cyberlite-syn-2.0.0-04a21fdaa5ec`, created
`2026-11-25T13:22:29Z`, 500 records split **444 / 33 / 23** (train / validation /
test). The calibration files were regenerated during this review; the hashes
below are the snapshot actually measured. An earlier build
(`913298850f3e`, 449 / 28 / 23) contained one 1,218-token record; it is not in
the current build. See [Limitations](#limitations).

- Report: `docs/reports/ml-training-review.md`
- Evidence JSON: `data/manifests/synthesis-calibration/ml_review.json`
- Tokenizer: `Qwen/Qwen3.5-0.8B`, local cache, revision
  `2fc06364715b967f1860aea9cf38778875588b17`
- Splits: `data/processed/synthesis-calibration/{train,validation,test}.jsonl`
- Manifest: `data/manifests/synthesis-calibration/manifest.json`
- Training code: `cyberlite/training/dataset.py`
- Configs: `configs/lora.yaml`, `configs/qlora.yaml`
- Mixture policy: `configs/synthesis/mix.yaml`

## Bottom line

1. **Tokenization and formatting are clean.** 0/500 encode failures, 0 discarded
   records, 0 all-masked label sequences, 12/12 chats valid, 15/15 FIM records
   valid, 473/473 completion records non-empty. `SFTDataset` builds
   444/33/23 examples with 0 skipped and 0 truncated.
2. **Using the shipped configs for these splits is blocked twice over.** The
   configs point at `data/processed/pilot-v2`, not the calibration splits, and
   the training license gate rejects **414/444 train, 30/33 validation, and
   23/23 test records** as `unresolved_license`. This is a governance gate, not
   a tokenizer failure, but it must be resolved before any run.
3. **Length is not the current constraint at 1,024 tokens.** 0/500 records
   exceed 1,024; p99 is 557 and max is 819. The residual risk is the near-limit
   819-token NVD triage record and the fact that `min_supervised_tokens: 1`
   would admit a future over-limit record even if truncation removed almost the
   entire answer.
4. **The 90/5/5 split is not adequate at n=500.** Validation and test have 33
   and 23 records; the 95% half-width at 70% accuracy is ±15.6 and ±18.7 points.
   Eight families are absent from validation, 14 from test, and there is no FIM
   and almost no chat evaluation data.
5. **The mixture policy does not cover the corpus it governs.** 84 records
   (16.8%) fall outside family caps (`command-explanation`, FIM,
   `multi-turn-troubleshooting`, `false-positive-recognition`); 80 records
   (16.0%, 19.6% of tokens) have no `domain` and bypass domain caps;
   `uncertainty-handling` is below its 2% floor (the policy was edited during
   this review); the curriculum assigns only 53.6% of records.
6. **Small-model stress is concentrated.** 17 records have more than 300
   supervised tokens, 41 evidence-grounded QA records ask the model to synthesise
   long evidence, 12 chats are four-turn, and 7 families have fewer than 10
   records. These are the records and families to watch for a 0.8B model.

## 1. Method

### 1.1 Token counting

I loaded the real fast tokenizer and encoded every record through the same
functions used by `SFTDataset`:

- chat: `render_chat` → `_encode_chat_detailed`
- completion: `_encode_completion_detailed`
- FIM: `_encode_fim_detailed`

Settings match the configs: `max_seq_length=1024`,
`truncation_policy="truncate"`, `min_supervised_tokens=1`,
`enable_thinking=False`, and the configured system prompt:

> You are CyberLite, a defensive cybersecurity assistant. Prefer verifiable,
> safe guidance. Never claim to have executed commands or accessed systems.

The reported length is `EncodingResult.original_length`: the token sequence after
the encoder appends a terminating EOS. This includes the full chat template and
system prompt for chat, the three FIM control tokens for FIM, and the appended
EOS; it excludes batch padding and packing. The system prompt is 27 tokens and
the chat template adds exactly 56 tokens over raw message content for every chat
record (27 system + 29 turn markers). FIM adds three one-token control tokens.

Tokenizer facts:

| Property | Value |
|---|---|
| Class | `Qwen3_5Tokenizer` (fast, offsets available) |
| Vocab size | 248,044 |
| EOS | `<|im_end|>` = 248,046 |
| PAD | `<|endoftext|>` = 248,044 |
| FIM prefix | `<|fim_prefix|>` = 248,060 |
| FIM suffix | `<|fim_suffix|>` = 248,062 |
| FIM middle | `<|fim_middle|>` = 248,061 |
| FIM pad | `<|fim_pad|>` = 248,063 |
| Chat template | Qwen3.5 template; `enable_thinking=False` accepted |

All four FIM tokens are defined. The three control tokens survive tokenization in
every FIM record; `<|fim_pad|>` is defined but is not emitted by the current FIM
encoder, which is expected and not a failure.

### 1.2 What is measured vs recommended

Everything in Sections 2–5 and 7 is **measured** from the snapshot. Section 6 is
**recommended** and is not validated by a training run.

## 2. Measured token distributions

### 2.1 Overall and by kind

| Kind | n | Min | p50 | p90 | p95 | p99 | Max | >512 | >768 | >1,024 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| chat | 12 | 376 | 472 | 536 | 577 | 615 | 625 | 3 | 0 | 0 |
| completion | 473 | 151 | 279 | 400 | 431 | 551 | 819 | 9 | 1 | 0 |
| FIM | 15 | 33 | 70 | 109 | 118 | 132 | 136 | 0 | 0 | 0 |
| **All** | **500** | **33** | **278** | **408** | **444** | **557** | **819** | **12** | **1** | **0** |

Total tokens: 146,674. Mean: 293.35. Total supervised tokens: 91,205 (62.2% of
tokens). The manifest’s own count (mean 292.43, p50 278, p90 401, p95 438, p99
557, max 819) agrees within a few tokens; the small difference is the review’s
system prompt and terminating EOS.

Chat is the longest kind by median (472) but has only 12 records. FIM is by far
the shortest (p50 70) and carries almost no supervised signal.

### 2.2 By task family

`Rec %` and `Tok %` are shares of the 500 records and 146,674 tokens. `Cap` is
the record-share cap in `mix.yaml` (`—` means no cap; `min 2%` means only a
minimum exists). Families are ordered by record count.

| Family | n | Rec % | Tok % | Sup % | Mean | p50 | p90 | p95 | p99 | Max | Cap |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| multiple-choice | 65 | 13.0 | 9.8 | 10.9 | 221 | 217 | 272 | 284 | 297 | 316 | 14% |
| instruction-response | 50 | 10.0 | 8.3 | 11.0 | 245 | 238 | 318 | 324 | 347 | 351 | 10% |
| command-explanation | 47 | 9.4 | 8.0 | 9.6 | 251 | 249 | 281 | 287 | 298 | 305 | — |
| evidence-grounded-qa | 41 | 8.2 | 9.9 | 5.2 | 353 | 352 | 411 | 417 | 449 | 464 | 20% |
| structured-json | 30 | 6.0 | 8.2 | 7.2 | 403 | 392 | 492 | 524 | 549 | 557 | 6% |
| configuration-analysis | 30 | 6.0 | 6.7 | 6.6 | 326 | 317 | 385 | 417 | 538 | 581 | 6% |
| multiple-choice-multi-answer | 25 | 5.0 | 4.4 | 3.7 | 256 | 260 | 280 | 285 | 296 | 299 | 5% |
| log-interpretation | 25 | 5.0 | 5.6 | 5.3 | 330 | 305 | 391 | 408 | 546 | 589 | 7% |
| secure-code-review | 21 | 4.2 | 4.9 | 5.9 | 342 | 341 | 416 | 423 | 433 | 435 | 8% |
| configuration-completion | 20 | 4.0 | 4.6 | 4.7 | 340 | 338 | 403 | 431 | 445 | 448 | 4% |
| misconception-correction | 20 | 4.0 | 2.9 | 3.8 | 210 | 210 | 248 | 250 | 255 | 256 | 4% |
| error-diagnosis | 20 | 4.0 | 3.4 | 4.4 | 248 | 236 | 288 | 311 | 332 | 337 | 4% |
| code-remediation | 17 | 3.4 | 3.7 | 4.5 | 323 | 325 | 360 | 390 | 453 | 469 | 7% |
| fill-in-the-middle | 15 | 3.0 | 0.8 | 0.2 | 76 | 70 | 109 | 118 | 132 | 136 | — |
| comparison | 13 | 2.6 | 3.0 | 4.1 | 342 | 322 | 414 | 426 | 436 | 438 | 4% |
| multi-turn-troubleshooting | 12 | 2.4 | 3.9 | 2.9 | 474 | 472 | 536 | 577 | 615 | 625 | — |
| false-positive-recognition | 10 | 2.0 | 2.7 | 1.7 | 398 | 400 | 454 | 474 | 490 | 494 | min 2% |
| uncertainty-handling | 9 | 1.8 | 2.1 | 1.5 | 348 | 339 | 394 | 395 | 396 | 396 | 5% |
| vulnerability-classification | 9 | 1.8 | 2.4 | 1.4 | 392 | 251 | 746 | 783 | 812 | 819 | 10% |
| general-retention | 8 | 1.6 | 1.9 | 2.7 | 349 | 344 | 390 | 396 | 400 | 401 | 4% |
| attack-technique-recognition | 4 | 0.8 | 0.7 | 0.4 | 240 | 229 | 265 | 273 | 279 | 281 | 6% |
| detection-rule-interpretation | 4 | 0.8 | 0.7 | 0.7 | 267 | 276 | 285 | 285 | 285 | 285 | 4% |
| vulnerability-remediation | 3 | 0.6 | 0.6 | 0.9 | 299 | 243 | 379 | 396 | 410 | 413 | 6% |
| incident-investigation | 2 | 0.4 | 0.7 | 0.8 | 532 | 532 | 546 | 547 | 549 | 549 | 4% |

Two distributions are visibly bimodal: `vulnerability-classification`
(p50 251 but p90 746, max 819) and `configuration-analysis` (p50 317, p99 538,
max 581). A mean is misleading for those families; use the tail.

### 2.3 Truncation risk at 1,024

| Threshold | Records over | Share |
|---|---:|---:|
| >1,024 | 0 | 0.0% |
| >768 | 1 | 0.2% |
| >512 | 12 | 2.4% |

The current build has **zero truncation at 1,024**. `SFTDataset` confirms
`truncated: 0` on all three splits. The residual risk is policy, not data:

- The longest record is 819 tokens, leaving 205 tokens of headroom.
- With `truncation_policy: truncate` and `min_supervised_tokens: 1`, a future
  1,024+ record whose prompt consumes nearly the whole window would be kept
  with only a few supervised tokens. One example from the superseded build had a
  1,017-token prompt and a 200-token answer: at 1,024 it retained **7 of 201**
  supervised tokens and was still accepted because 7 ≥ 1. The current build has
  no such record, but the configuration permits the failure mode.
- `truncate` cuts the answer, not the prompt. For a safety assistant, a truncated
  answer is a corrupt target. `drop` is safer.

### 2.4 Longest records by ID

| ID | Split | Kind | Family | Tokens | Supervised |
|---|---|---|---|---:|---:|
| `grnd-nist-nvd-nist-nvd-001f4beaa8f927d0-triage` | train | completion | vulnerability-classification | 819 | 298 |
| `grnd-nist-nvd-nist-nvd-00515c5c766e67b7-triage` | train | completion | vulnerability-classification | 728 | 258 |
| `syn-monitoring-detection-soc-log-network-layers-012-triage-dialogue` | train | chat | multi-turn-troubleshooting | 625 | 227 |
| `syn-incident-response-forensics-threat-intel-mal-c2-039-log-1` | train | completion | log-interpretation | 589 | 260 |
| `syn-incident-response-forensics-threat-intel-ti-stix-048-config-1` | train | completion | configuration-analysis | 581 | 253 |
| `grnd-nist-nvd-nist-nvd-00795ecd6c9525f0-json` | train | completion | structured-json | 557 | 74 |
| `syn-incident-response-forensics-threat-intel-forensics-antiforensics-032-incident-plan` | train | completion | incident-investigation | 549 | 359 |
| `syn-monitoring-detection-soc-log-powershell-encoded-108-triage-dialogue` | train | chat | multi-turn-troubleshooting | 538 | 248 |
| `syn-incident-response-forensics-threat-intel-attack-initial-053-checklist` | train | completion | structured-json | 530 | 294 |
| `syn-monitoring-detection-soc-log-benign-corroboration-112-triage-dialogue` | train | chat | multi-turn-troubleshooting | 519 | 215 |
| `syn-incident-response-forensics-threat-intel-mal-elf-037-checklist` | train | completion | structured-json | 517 | 286 |
| `syn-incident-response-forensics-threat-intel-ir-ransom-008-incident-plan` | train | completion | incident-investigation | 516 | 347 |

### 2.5 Supervised length

| Kind | n | Min | p50 | p90 | p95 | p99 | Max |
|---|---:|---:|---:|---:|---:|---:|---:|
| chat | 12 | 197 | 218 | 247 | 249 | 251 | 251 |
| completion | 473 | 65 | 183 | 267 | 287 | 350 | 386 |
| FIM | 15 | 6 | 13 | 25 | 26 | 28 | 29 |

Supervised tokens are 62.2% of all tokens overall, but only 0.2% for FIM. The
longest supervised target is 386 tokens (`comparison`), not the longest total
record. Length pressure in this corpus comes from prompts/evidence, not from
extremely long answers.

## 3. Chat formatting and SFT compatibility

### 3.1 Checklist

| Check | Result | Evidence |
|---|---|---|
| Encode failures via `dataset.py` | **0 / 500** | No exceptions from any encoder |
| Records discarded (empty/all-masked/truncated) | **0 / 500** | `SFTDataset` stats: skipped 0, truncated 0 |
| All-masked label sequences | **0 / 500** | Every encoded example has ≥1 supervised token |
| Chat ends with assistant turn | **12 / 12** | Schema + independent re-read |
| Chat roles valid | **12 / 12** | Roles are `user`/`assistant` only |
| Assistant masking | **12 / 12** | `n_spans == n_assistant`; span coverage 1.0; no user text in decoded supervised tokens |
| Chat template ends with `<|im_end|>` | **12 / 12** | Rendered text ends `<|im_end|>` |
| FIM control tokens present | **15 / 15** | prefix/suffix/middle IDs present in every encoded prompt |
| FIM middle non-empty | **15 / 15** | Min 6 supervised tokens; max 29 |
| Completion prompt/response non-empty | **473 / 473** | No empty or zero-token responses |
| Completion masking | **473 / 473** | Supervised text starts with the response; no prompt leakage |
| `SFTDataset` end-to-end | **444 / 33 / 23 examples** | 0 skipped, 0 truncated; max 819 / 449 / 426 |

### 3.2 Details and residual issues

- **Chat masking is correct.** `_assistant_char_spans` finds only assistant
  content and the immediately following terminator. I decoded the supervised
  token runs for all 12 chats: each starts with assistant text and contains no
  user prompt text. This is a stronger check than span coverage alone.
- **FIM is valid but tiny.** All 15 records use the three control tokens in the
  expected order. The encoder appends the tokenizer EOS `<|im_end|>` to the
  middle; it does not use `<|fim_pad|>`. That is internally consistent, but if
  the inference/autocomplete path expects `<|fim_pad|>` as the stop token, the
  training and serving conventions should be reconciled. Test this explicitly.
- **Double stop token in chat.** Every chat render ends `<|im_end|>\n`. The
  final token is the newline, so `_finalize_result` appends another `<|im_end|>`
  and supervises it. Labels therefore end
  `… <|im_end|> \n <|im_end|>`. This is not a correctness failure, but the
  model is trained to emit a second stop token after the newline. Stripping
  trailing whitespace before tokenizing, or not appending EOS when the rendered
  text already ends in one, would remove the redundancy.
- **The system prompt is almost absent from training.** Only the 12 chat
  records include it (2.4%). `SFTDataset` ignores `system_prompt` for completion
  and FIM records, so 473 completion + 15 FIM records (97.6%) never see the
  CyberLite persona. At inference the model will normally be prompted with the
  system message. This is a distribution mismatch, not a formatting error.
  Either convert instruction/QA records to chat format with the system prompt,
  or prepend it to completion prompts; measure the +27-token effect in a pilot.
- **Separate prompt/response tokenization.** Completions are encoded as
  `tokenize(prompt) + tokenize(response)`, not as one string. Labels are correct,
  but the boundary can differ from a joint tokenization. This is minor and
  consistent across the corpus, but worth knowing when comparing offline
  tokenization to serving.
- **`min_supervised_tokens: 1` is too permissive.** It is the only guard after
  truncation. Raise it (for example to 32) and use `drop`; otherwise a future
  over-limit record can train on a nearly empty answer.
- **Template fallback risk.** `render_chat` silently retries without template
  kwargs if a tokenizer rejects them. For this tokenizer `enable_thinking=False`
  is accepted, so the measured chats are correct; a future tokenizer change
  could silently fall back to a thinking-enabled template.

### 3.3 Training gate: configs and licenses

This is separate from tokenization but blocks the run.

| Check | Measured | Consequence |
|---|---|---|
| Config train file | `data/processed/pilot-v2/train.jsonl` | Configs do not point at calibration |
| Config manifest | `data/manifests/pilot-v2/manifest.json` | Wrong manifest/version for calibration |
| Config expected counts | 6,351 / 416 / 421 | Calibration is 444 / 33 / 23; integrity check would fail |
| Config dataset version | `cyberlite-data-2.0.0-04b01b437805` | Calibration is `cyberlite-syn-2.0.0-04a21fdaa5ec` |
| `require_resolved_licenses` | `true` | Unresolved licenses are rejected |
| `allow_unresolved_licenses` | `[]` | Nothing is acknowledged |
| License gate, train | 30 accepted, **414 rejected** | All rejections are `unresolved_license` |
| License gate, validation | 3 accepted, **30 rejected** | All `unresolved_license` |
| License gate, test | 0 accepted, **23 rejected** | All `unresolved_license` |

The unresolved licenses are `Synthetic` (the bulk of the corpus),
`MITRE-ATTACK`, `MITRE-CWE`, `IETF-Trust`, `CC-BY-SA-4.0`, the GPL variants,
`Linux-man-pages-1-para`, and `Linux-man-pages-copyleft`. This is the documented
fail-closed gate, not a bug. A human licensing decision must be recorded, or
`allow_unresolved_licenses` populated after review, before training. Do not set
`require_resolved_licenses: false` merely to make the run start.

Also: `preferences.jsonl` (183 pairs) is not part of the SFT splits. Preference
optimisation, if planned, is a separate stage and should not be counted in the
SFT 25k mixture.

## 4. Small-model suitability (0.8B)

### 4.1 Too long

- **0 records exceed 1,024.** The 819-token NVD triage record is the
  closest-to-limit case; 2 records are at least 728 tokens and 12 exceed 512.
- At 819 tokens, the record fits with ~205 tokens of headroom; its 298-token
  answer is already included in that count. That is workable but tight for a
  multi-constraint answer, and it is the record closest to the limit.
- The 1,024 limit is adequate for this calibration corpus. It will not be
  adequate for the longest production evidence records if synthesis grows them;
  cap prompt tokens at 768 and reserve 128 for the answer, or route longer
  evidence to a separate long-context evaluation set.

### 4.2 Too dense

Using >280 supervised tokens as “dense” and >300 as “heavy”:

- **28 dense records; 17 heavy records; max 386 supervised tokens.**
- Dense families: `comparison` (9), `general-retention` (7),
  `secure-code-review` (6), `structured-json` (3), plus a few
  `vulnerability-remediation`, `instruction-response`, and
  `incident-investigation` records.
- The heaviest records are not the longest total records: e.g.
  `syn-incident-response-forensics-threat-intel-forensics-bash-031-compare-forensics-cloudlogs-034`
  has 386 supervised tokens in 1,903 characters; `grnd-mitre-cwe-mitre-cwe-00c423fba47e9a8f-mitigation`
  has 370.
- No record exceeds 400 supervised tokens, so target length alone is not the
  main risk. The risk is multi-constraint answers (compare/contrast, mitigation
  plans) that a 0.8B model may satisfy superficially.

### 4.3 Multi-hop and long-context reasoning

Heuristic flags, not quality labels:

| Flag | Records | Meaning |
|---|---:|---|
| Evidence synthesis | 41 | `evidence-grounded-qa` with >500-character prompt; read evidence, then answer |
| Family multi-hop | 14 | 12 `multi-turn-troubleshooting` + 2 `incident-investigation` |
| Multi-turn chat | 12 | All chats are 4 turns (2 user / 2 assistant) |

A 0.8B model can learn the format of these, but four-turn chats and long
evidence prompts are where it is most likely to lose earlier context or answer
from the last turn only. The 625-token chat
(`syn-monitoring-detection-soc-log-network-layers-012-triage-dialogue`) and the
549/516-token incident plans are the specific stress cases.

### 4.4 Families with too little representation

Seven families have fewer than 10 records (and fewer than 2% record share):

| Family | Records | Record % | Token % |
|---|---:|---:|---:|
| incident-investigation | 2 | 0.4 | 0.7 |
| vulnerability-remediation | 3 | 0.6 | 0.6 |
| attack-technique-recognition | 4 | 0.8 | 0.7 |
| detection-rule-interpretation | 4 | 0.8 | 0.7 |
| general-retention | 8 | 1.6 | 1.9 |
| uncertainty-handling | 9 | 1.8 | 2.1 |
| vulnerability-classification | 9 | 1.8 | 2.4 |

FIM is a special case: 15 records (3.0% of records) but only **0.2% of supervised
tokens**. It cannot teach a useful autocomplete policy on its own. These families
can be present in a 25k production mixture, but they cannot be evaluated on the
current 33/23 splits.

### 4.5 Difficulty and diversity

- Difficulty: 150 foundational (30%), 200 intermediate (40%), 125 advanced
  (25%), 25 expert (5%). 30% advanced/expert is high for a 0.8B model, though
  expert records are short (mean 272 tokens) and not the token-heavy part.
- 420/500 records are synthetic; 80 are source-derived. The source-derived
  records are longer (19.6% of tokens from 16.0% of records) and often
  template-shaped (NVD JSON, MITRE claim/requirement views). A 0.8B model is
  more likely to memorise the template than learn the reasoning; keep
  source-derived records below the recommended 20% record cap and vary
  templates in production.
- The manifest already reports template concentration: 15 FIM records share an
  empty skeleton, and NVD-derived JSON records share a long skeleton. This is a
  diversity risk, not a formatting failure.

## 5. Mixture policy evaluation

Policy: `configs/synthesis/mix.yaml` (`cyberlite-synthesis-mix-v1`). Its shares
are explicitly **record shares**, not token shares, and are hard upper bounds.

### 5.1 Caps

| Check | Measured | Verdict |
|---|---|---|
| Family caps, record-weighted | 0 violations | All families at or below cap |
| Families exactly at cap | 7 | `instruction-response` 10%, `structured-json` 6%, `configuration-analysis` 6%, `multiple-choice-multi-answer` 5%, `configuration-completion` 4%, `misconception-correction` 4%, `error-diagnosis` 4% |
| Multiple-choice | 13.0% vs 14% cap | 1.0 pp headroom |
| Family cap sum | 1.47 | Caps are not a partition; they cannot all bind |
| Domain caps, record-weighted | 0 violations | (`language-security-retention` 12%, `cloud-container-supply-chain` 12%, `cryptography-identity-access` 10% are exactly at cap) |
| Domain cap sum | 1.10 | Same design note as family caps |
| Families in data, absent from policy | 3 | `command-explanation` (47), `fill-in-the-middle` (15), `multi-turn-troubleshooting` (12) |
| Families in policy, absent from SFT data | 2 | `secure-autocomplete`, `preference-pair` |
| Records outside family caps | 84 (16.8%) | 47 command + 15 FIM + 12 multi-turn + 10 false-positive (min only) |
| Records with no domain | 80 (16.0%) | 19.6% of tokens; domain caps cannot bind them |
| Domain cap coverage | 84.0% of records | Source-derived records bypass the domain policy |

Several families sit **exactly** at their caps. That is evidence the corpus was
quota-selected to the policy, not evidence that the caps are calibrated to the
underlying task distribution. For a production mixture, caps should be treated
as guardrails, not targets.

The domain gap is material: 80 source-derived records carry no
`metadata.domain`, so the domain caps govern only 84% of records. A plausible
mapping of those records to their nearest domain (NVD→vulnerability,
MITRE ATT&CK→detection/incident, IETF/man/OpenSSH→fundamentals, OWASP→web)
would push `fundamentals-linux-networking` to roughly 72–76 of 500 (14–15%),
above its 12% cap. That mapping is an estimate, but it shows the cap is not
currently verifiable for the whole corpus.

### 5.2 Minimums

| Family | Minimum | Actual record share | Status |
|---|---:|---:|---|
| uncertainty-handling | 2.0% | 1.8% (9 records) | **below** |
| false-positive-recognition | 2.0% | 2.0% (10 records) | exactly meets |
| general-retention | 1.0% | 1.6% (8 records) | meets |
| evidence-grounded-qa | 0.5% | 8.2% (41 records) | meets |

One of four minimums fails. The policy’s stated purpose is to keep reasoning and
uncertainty examples from disappearing; at 8–9 records they are effectively at
the noise floor for a 500-record calibration set. Note that `mix.yaml` was
edited during this review (13:30:27Z): `general-retention`’s floor moved from
2.0% to 1.0% and `evidence-grounded-qa` gained a 0.5% floor, while the policy
name stayed `cyberlite-synthesis-mix-v1`. The table above uses the current file.

### 5.3 Token-weighted vs record-weighted shares

The policy is record-weighted. Training compute and gradient influence are
token-weighted. Notable differences (token share minus record share):

| Family | Record % | Token % | Delta |
|---|---:|---:|---:|
| multiple-choice | 13.0 | 9.8 | **−3.2 pp** |
| fill-in-the-middle | 3.0 | 0.8 | **−2.2 pp** |
| instruction-response | 10.0 | 8.3 | −1.7 pp |
| command-explanation | 9.4 | 8.0 | −1.4 pp |
| structured-json | 6.0 | 8.2 | **+2.2 pp** |
| evidence-grounded-qa | 8.2 | 9.9 | +1.7 pp |
| multi-turn-troubleshooting | 2.4 | 3.9 | +1.5 pp |

Record caps therefore allow long-record families to consume more compute than
their nominal share. That is not a policy violation—the policy says records—but
it means the 25k mixture should be specified in token shares if compute balance
is the goal.

### 5.4 Curriculum coverage

| Phase | Records | Record % | Token % | Families |
|---|---:|---:|---:|---|
| phase 1 — foundations-and-evidence | 181 | 36.2 | 33.6 | instruction-response, evidence-grounded-qa, multiple-choice, log-interpretation |
| phase 2 — applied-defence | 87 | 17.4 | 19.8 | secure-code-review, code-remediation, configuration-analysis, vulnerability-classification, attack-technique-recognition, incident-investigation, detection-rule-interpretation |
| **Covered** | **268** | **53.6** | **53.4** | 11 families |
| Unassigned | 232 | 46.4 | 46.6 | 13 families |

Unassigned families: `command-explanation`, `comparison`,
`configuration-completion`, `error-diagnosis`, `false-positive-recognition`,
`fill-in-the-middle`, `general-retention`, `misconception-correction`,
`multi-turn-troubleshooting`, `multiple-choice-multi-answer`, `structured-json`,
`uncertainty-handling`, `vulnerability-remediation`.

The curriculum is incomplete: 46.4% of records have no phase, there is no phase
3, and no scheduling, replay, or per-phase epoch count is defined. Phase 2 is
only 87 records; a strict sequential pass would fine-tune on 87 examples after
phase 1 and risk forgetting. Use interleaved phases with replay of phase 1, not
a hard switch.

### 5.5 Policy targets vs configs

| Setting | Policy | Configs | Status |
|---|---|---|---|
| Max sequence length | 1,024 | 1,024 | matches |
| Epochs | 3 | 1 | **mismatch** |
| Data path | (not specified) | `pilot-v2` | **mismatch with calibration** |
| License gate | (not specified) | `require_resolved_licenses: true`, empty allow-list | **blocks calibration** |

## 6. Recommended 25k production mixture

**Status: recommended, not measured.** Assumption: 25,000 accepted SFT records
at 1,024 tokens. The table solves for the token budget that produces exactly
25,000 records under the proposed token shares and the measured mean length per
family. That budget is **7.28M tokens/epoch**; at 2 epochs, ~14.6M tokens.

### 6.1 Per-family targets

| Family | Token share | Implied records | Tokens/epoch | Measured mean |
|---|---:|---:|---:|---:|
| evidence-grounded-qa | 11.8% | 2,437 | 859,306 | 353 |
| multiple-choice | 8.7% | 2,877 | 635,203 | 221 |
| instruction-response | 8.0% | 2,379 | 582,815 | 245 |
| secure-code-review | 7.2% | 1,531 | 523,151 | 342 |
| code-remediation | 6.2% | 1,389 | 448,207 | 323 |
| vulnerability-classification | 5.4% | 1,011 | 395,819 | 392 |
| command-explanation | 5.3% | 1,551 | 388,543 | 251 |
| multiple-choice-multi-answer | 4.4% | 1,252 | 320,876 | 256 |
| vulnerability-remediation | 4.4% | 1,072 | 320,876 | 299 |
| configuration-analysis | 4.4% | 983 | 320,876 | 326 |
| log-interpretation | 4.4% | 971 | 320,876 | 330 |
| configuration-completion | 3.6% | 769 | 261,212 | 340 |
| structured-json | 3.1% | 556 | 224,104 | 403 |
| detection-rule-interpretation | 2.7% | 727 | 194,272 | 267 |
| incident-investigation | 2.7% | 365 | 194,272 | 532 |
| attack-technique-recognition | 2.7% | 811 | 194,272 | 240 |
| false-positive-recognition | 2.7% | 488 | 194,272 | 398 |
| uncertainty-handling | 2.4% | 494 | 171,716 | 348 |
| general-retention | 2.4% | 492 | 171,716 | 349 |
| misconception-correction | 1.8% | 642 | 134,608 | 210 |
| error-diagnosis | 1.8% | 543 | 134,608 | 248 |
| comparison | 1.3% | 283 | 96,772 | 342 |
| multi-turn-troubleshooting | 1.3% | 204 | 96,772 | 474 |
| fill-in-the-middle | 1.2% | 1,173 | 89,496 | 76 |
| **Total** | **100%** | **25,000** | **7,276,089** | |

Notes on the proposal:

- `fill-in-the-middle` is token-cheap (76 tokens/record), so a 1.2% token share
  implies 1,173 records (4.7% of records). That is intentional: FIM needs many
  examples per supervised token. Keep it under a 5% record cap.
- `incident-investigation` is record-expensive (532 tokens/record); 2.7% tokens
  gives 365 records, below a 400-record floor. The floor should override the
  token share; add ~35 records and accept ~2.9% tokens.
- `evidence-grounded-qa` is the largest token consumer at 11.8%. That is below
  the 15% token cap and consistent with its 8.2% measured record share after the
  longer records were removed. Do not let it exceed 15% tokens; long evidence
  is the most likely place for a 0.8B model to learn shortcuts.

### 6.2 Caps and floors

Recommended caps:

| Basis | Cap |
|---|---:|
| Any single family, token share | 15% |
| `evidence-grounded-qa`, token share | 15% |
| `multiple-choice`, token share | 10% |
| `instruction-response`, token share | 10% |
| `secure-code-review`, token share | 8% |
| Any single domain, token share | 18% |
| Any single family, record share | 15% |
| `fill-in-the-middle`, record share | 5% |
| Chat-format records, record share | 5% |
| `evidence-grounded-qa`, record share | 11% |
| Source-derived grounded records, record share | 20% |

Recommended floors (records, not shares): 500 each for
`uncertainty-handling`, `false-positive-recognition`, `general-retention`,
`vulnerability-remediation`; 400 each for `incident-investigation`,
`detection-rule-interpretation`, `attack-technique-recognition`. Floors override
token shares. Without floors, the token-weighted solution gives 365–494 records
for those families, which is below the policy’s 2% intent.

### 6.3 Epochs and optimisation

- **Epochs: 2** (range 2–3), early stopping after 2 evaluations without
  improvement. At ~7.28M tokens/epoch, 2 epochs is ~14.6M tokens. More than 3
  epochs on 25k records risks memorisation; 1 epoch (the current config)
  underuses the corpus.
- Keep the existing LoRA/QLoRA settings as the starting point: r=16, alpha=32,
  dropout 0.05, lr 2e-4, cosine schedule, warmup 3%, bf16, gradient
  checkpointing, effective batch 8. Tune only after the mixture is fixed.
- Reconcile `mix.yaml` `target_epochs: 3` with the training config before the
  run; do not leave the policy and config disagreeing.

### 6.4 Sequence packing and truncation

Recommended policy:

| Setting | Recommendation |
|---|---|
| `max_seq_length` | 1,024 |
| Over-limit records | **drop**, do not truncate the answer |
| Prompt token cap | 768 |
| Response reserve | 128 tokens |
| `min_supervised_tokens` | 32 (not 1) |
| Packing | Greedy length-bucketed packing to 1,024 with block-diagonal attention and position reset; fall back to length-sorted batching if packing is unavailable |
| Padding | Pad to multiple of 8 (current collator behaviour) |
| FIM terminator | Verify `<|im_end|>` vs `<|fim_pad|>` against the serving path |

The current `SFTDataset`/collator does not implement packing; it pads each batch
to its longest sequence. Packing is a throughput recommendation, not a statement
about current code. If packing is added, ensure labels from adjacent examples
are isolated; do not let a packed sequence attend across example boundaries.

### 6.5 Evaluation checkpoints

At effective batch 8, 25,000 records is 3,125 steps/epoch; 2 epochs is 6,250
steps. Checkpoints:

| Fraction | Step (no packing) | Purpose |
|---|---:|---|
| 25% | 1,563 | early-loss and format sanity |
| 50% | 3,125 | mid-run family check |
| 75% | 4,688 | overfitting check |
| 100% | 6,250 | final candidate |

Evaluate every 250 steps on validation loss, but run the full family-macro
evaluation at the four checkpoints. Metrics: validation loss; per-family loss
(macro-average, so small families are not hidden); exact-match/format validity
for MCQ/JSON/FIM; assistant-mask sanity; and a small safety/refusal probe.
Select the best checkpoint by family-macro validation loss, not overall loss.
Keep the test split locked until the final comparison. With packing, steps per
epoch drop by roughly 1.5–2×; recompute checkpoint steps after measuring the
packing factor.

### 6.6 Format recommendation

Put the CyberLite system prompt into every instruction/QA/chat training record,
not just the 12 chats. Either convert completion records to chat format or
prepend the system prompt in the prompt text. This adds 27 tokens per converted
record; re-measure the mixture after conversion. Do not convert FIM records.

Run a 2–5k pilot of the proposed mixture before the 25k run. The pilot should
compare (a) record-weighted vs token-weighted sampling, (b) 1 vs 2 epochs, and
(c) chat-with-system-prompt vs completion-only formatting. The recommendations
above are a starting point, not a validated recipe.

## 7. Split assessment

### 7.1 Current split

| Split | Records | Share | 95% half-width at p=0.70 | Families absent | Kinds |
|---|---:|---:|---:|---|---|
| train | 444 | 88.8% | ±4.3 pp | — | 418 completion, 15 FIM, 11 chat |
| validation | 33 | 6.6% | **±15.6 pp** | 8 | 33 completion; 0 chat, 0 FIM |
| test | 23 | 4.6% | **±18.7 pp** | 14 | 22 completion, 1 chat; 0 FIM |

The nominal 90/5/5 would be 450/25/25; the actual 444/33/23 differs. No group
leakage was found, so the split is group-safe, but it is not stratified by
family or kind.

Families absent from validation (8): `attack-technique-recognition`,
`code-remediation`, `configuration-completion`, `fill-in-the-middle`,
`incident-investigation`, `multi-turn-troubleshooting`, `secure-code-review`,
`vulnerability-remediation`.

Families absent from test (14): `attack-technique-recognition`,
`code-remediation`, `comparison`, `detection-rule-interpretation`,
`error-diagnosis`, `false-positive-recognition`, `fill-in-the-middle`,
`general-retention`, `incident-investigation`, `misconception-correction`,
`multiple-choice-multi-answer`, `uncertainty-handling`,
`vulnerability-classification`, `vulnerability-remediation`.

Fourteen families have fewer than 2 validation+test examples. Validation has no
chat and no FIM; test has one chat and no FIM. Chat and FIM behaviour cannot be
compared at all.

### 7.2 Is 90/5/5 appropriate?

**At n=500: no.** A 33-record validation set selected on loss is noisy; a
23-record test set cannot distinguish a real improvement from sampling luck.
The half-widths above imply that even a 15-point accuracy difference is at the
edge of resolution, and a two-model difference is roughly ±24 points under an
independent-proportion approximation. Per-family comparisons are impossible for
most families: 14 have fewer than 2 eval examples, and several have zero.

**At n=25,000: yes, conditionally.** 90/5/5 gives 22,500 / 1,250 / 1,250. At
p=0.70, each eval estimate has a 95% half-width of about ±2.5 points; a
two-model difference is about ±3.6 points. That supports overall comparisons and
most family comparisons, provided the split is stratified by family and kind and
rare families have floors (or are merged into macro-groups). Keep the test set
locked and report bootstrap confidence intervals.

### 7.3 Recommendation

- **Calibration (500):** do not rely on a single 90/5/5 split for model
  comparison. Use 5-fold grouped cross-validation (about 100 records per fold)
  or an 80/10/10 split (50/50) with per-family floors, and report bootstrap
  intervals. If a locked test is required, make it at least 50 records and
  stratify by family and kind.
- **Production (25k):** use 90/5/5 (22.5k/1.25k/1.25k), stratified by family and
  kind, group-safe, with at least 30 eval examples per family or an explicit
  “rare-family macro-group”. Keep a final locked test set that is never used for
  checkpoint selection.
- In both cases, evaluate chat and FIM separately; the current splits cannot.

## 8. Limitations

- **Snapshot, not a live guarantee.** The corpus was regenerated at
  `2026-11-25T13:22:29Z` during this review. The JSON records the measured file
  hashes; a later rebuild invalidates these numbers. The superseded build
  (`913298850f3e`) had 449/28/23 and one 1,218-token record; it was not used for
  the tables above.
- **The mixture policy also changed during review.** `configs/synthesis/mix.yaml`
  was edited at `13:30:27Z` (general-retention floor 2%→1%; evidence-grounded
  floor added at 0.5%) without a version bump. This report uses the current file;
  the JSON records its hash and mtime.
- **Per-record counts, not packing.** Token counts exclude batch padding and
  packing. They are comparable to `SFTDataset`’s `original_length`, not to a
  packed training step.
- **Heuristics.** “Dense”, “multi-hop”, and “likely to overwhelm” are thresholds
  on supervised length, prompt length, turn count, and family, not annotations.
  They identify review candidates, not measured difficulty.
- **Small n.** Family percentiles for families with fewer than 10 records are
  unstable; p99 for a 2–4 record family is effectively the max. Do not over-read
  those cells.
- **No training run.** The 25k mixture, epoch count, packing policy, and
  checkpoint schedule are recommendations. A 2–5k pilot is needed before the
  production run.
- **License gate is governance, not tokenization.** The 414/30/23 rejections are
  a deliberate fail-closed policy. Resolving them requires a human licensing
  decision, not an ML change.
- **System prompt and template assumptions.** Counts use the configured system
  prompt and `enable_thinking=False`. Changing either changes chat lengths by at
  least 27 tokens and may change the template.
- **FIM convention.** The encoder appends `<|im_end|>`, not `<|fim_pad|>`. The
  counts are correct for the current encoder, but serving compatibility should
  be tested explicitly.

## 9. Paths and most important findings

**Deliverables**

- Report: `docs/reports/ml-training-review.md`
- Evidence JSON: `data/manifests/synthesis-calibration/ml_review.json`

**Inputs measured**

- `data/processed/synthesis-calibration/train.jsonl` — 444 records, sha256
  `5e9673dc4b354ff20df9f02eeb0fdfa6873311742d48793004cf956849abc971`
- `data/processed/synthesis-calibration/validation.jsonl` — 33 records, sha256
  `5a018a4fd645d069f2a9c19111bc43a68d90371c0ca139c5f67e44a77b98343f`
- `data/processed/synthesis-calibration/test.jsonl` — 23 records, sha256
  `e131502494c867f5ef19df856c974288300ab5d95228ea5ddfc3a7fc1dcdb059`
- `data/manifests/synthesis-calibration/manifest.json`
- `configs/lora.yaml`, `configs/qlora.yaml`, `configs/synthesis/mix.yaml`
- `cyberlite/training/dataset.py`

**Most important findings**

1. **Formatting and tokenization pass.** 0 encode failures, 0 discarded, 0
   all-masked labels; all chats, FIM, and completion records validate.
2. **Training is blocked by config and licensing.** Configs target `pilot-v2`,
   not calibration; the license gate rejects 414/444 train records.
3. **1,024 is sufficient for this corpus, but the policy is unsafe.** 0 records
   over 1,024; max 819. `truncate` + `min_supervised_tokens: 1` would train on a
   nearly empty answer if a longer record appears.
4. **The split is too small for comparison.** 33/23 eval records give ±15.6/±18.7
   point half-widths; 14 families have <2 eval examples; chat/FIM are effectively
   unmeasured.
5. **The mixture policy has coverage gaps.** 84 records outside family caps, 80
   records without a domain, one minimum below its floor, and only 53.6% of
   records in a curriculum phase.
6. **A 0.8B model will be stressed by a minority of records.** 17 records have
   >300 supervised tokens, 41 evidence-grounded QA records require evidence
   synthesis, 12 chats are four-turn, and 7 families have <10 records. Weight
   these deliberately rather than by raw record count.

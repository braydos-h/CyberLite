# Privacy, provenance and safety review — CyberLite synthesis calibration corpus

- **Reviewer:** Agent H (independent security, privacy and provenance review)
- **Date:** 2026-11-25
- **Scope:** `data/processed/synthesis-calibration/{train,validation,test}.jsonl` (500 records: 449 train / 28 validation / 23 test), the eight knowledge packs, the detection-rule seed library, the source registry, and the build manifest.
- **Auxiliary files inspected but not counted in `records_scanned`:** `preferences.jsonl` (183 pairs) and `quarantine.jsonl` (26 rejected IDs).
- **Companion machine-readable result:** `data/manifests/synthesis-calibration/privacy_provenance.json`

No corpus, code, configuration or manifest file was modified. This report and the companion JSON are the only files written.

## Verdict

| Area | Result |
|---|---|
| Live credentials / private keys / tokens | **Pass** — none. Four pattern hits were synthetic placeholders or false positives. |
| PII | **Pass with note** — no personal data; seven public vendor PSIRT role mailboxes appear inside upstream NVD metadata. |
| Synthetic identifiers / documentation IPs | **Pass with one low finding** — all addresses are RFC 5737, RFC 1918, loopback, wildcard or the IMDS link-local endpoint; one `.net` domain is illustrative but not reserved. |
| Unsafe operational content | **Pass** — defensive analysis, inert vulnerable snippets and detection engineering only. No attack, evasion, malware-construction or credential-theft instruction. |
| Provenance and licensing metadata | **Conditional pass** — all required fields are present and all hashes verify, but there are systematic gaps (`license_url` empty on all 423 synthetic records), four unregistered detection records, and one stale pack hash. |
| AI vs human review | **Pass** — no record claims human review; all are `automated-screened` with `human_reviewed: false`. |
| Evaluation-only material in training | **Pass** — no evaluation leakage detected, but the manifest screens only 3 of the 6 evaluation files now on disk. |

## Method

1. Parsed every JSONL record and every pack/detection JSON file.
2. Ran regex sweeps for PEM private keys, AWS/GitHub/Slack/Stripe/Google credential shapes, JWTs, bearer tokens, credentialed connection strings, emails, SSNs, phone numbers, MAC addresses and Luhn-checked payment-card candidates. Every hit was opened and read in context; synthetic and false-positive handling is recorded below.
3. Extracted every IPv4 address and every URL/hostname, classified addresses against RFC 5737, RFC 3849, RFC 1918 and loopback, and reviewed each non-reserved hostname in context.
4. Keyword-scanned and manually read every record containing `ransomware`, `reverse shell`, `mimikatz`, `LSASS`, `rootkit`, `C2`, `exfiltration`, `/dev/tcp`, `vssadmin`, `certutil`, persistence and evasion terms.
5. Recomputed `content_hash` for all 500 records with the pipeline definition (`messages[*].content` then prompt/response/prefix/suffix/middle joined by newlines): **500/500 match**.
6. Recomputed SHA-256 for every pack, every split and every evaluation file; compared against the manifest.
7. Resolved every `upstream_id` against its pack and every `derivation_parent_id` against `data/processed/pilot-v2` (**77/77 resolved**).
8. Ran an independent 13-gram contamination screen between the six evaluation files and all three splits.
9. Spot-checked eight reference URLs over HTTP (not exhaustive, per instructions).

## 1. Credentials, secrets and sensitive identifiers

**Result: no real secret material.**

The corpus contains no PEM blocks, no JWTs, no cloud access keys, no GitHub/Slack/Stripe/Google tokens, and no credentialed connection strings. Long-token sweep hits were all benign paths, flags, GUIDs or placeholders.

Four hits required triage:

| Finding | Location | Classification |
|---|---|---|
| `API_KEY = "sk_live_[REDACTED]"` | `syn-cryptography-identity-access-crypto-hardcoded-keys-020-codefix-1` | **Synthetic placeholder.** The literal itself contains `synthetic_example_not_a_real_key`; used to teach why hard-coded keys are not secret. |
| `git log -p -S 'BEGIN PRIVATE KEY'` | pack `c4-cryptography-identity-access.json#crypto-hardcoded-keys-020` | **False positive.** A history-search pattern, not key material. No PEM text exists in any split. |
| `powershell.exe -EncodedCommand RwBlAHQ…` | `syn-monitoring-detection-soc-log-powershell-encoded-108-triage-dialogue` | **False positive.** Decodes from UTF-16LE to `Get-CimInstance Win32_OperatingSystem`; a benign SCCM inventory signal in a triage exercise. |
| `Bearer REDACTED_API_KEY` | `syn-web-api-secure-development-api-apikey-001-config-1` | **Already redacted.** Placeholder value. |

**False-positive handling:** every match was read in context before a decision. Pattern matching alone would have produced four false positives (a search string, a benign encoded command, a redacted placeholder, and a deliberately fake Stripe-shaped key) and zero real secrets. No secret is reproduced in this report; local parts and token values are redacted.

## 2. PII

**Result: no personal data identified.**

- **SSNs:** 0. **Payment cards:** 0 (three card-like numeric runs were a DNS SOA serial and two STIX object identifiers). **Phone numbers:** 0. **MAC addresses:** 0. **Named individuals as data subjects:** 0.
- **Emails:** 14 distinct string matches, of which:  - **7 are public CVE-programme / vendor role mailboxes** in NVD-derived metadata (`[redacted]@nist.gov`, `[redacted]@vuldb.com`, `[redacted]@patchstack.com`, `[redacted]@emc.com`, `[redacted]@adobe.com`, `[redacted]@vmware.com`, `[redacted]@oracle.com`). These are organisation addresses published in CVE records, not personal data. They are upstream NVD content; if the corpus is redistributed outside the NVD terms, local parts should be stripped.
  - **3 are synthetic** (two at `example.internal`, one at `example-relay.test`) on reserved domains.
  - **4 are regex false positives**: OpenSSH streamlocal directives (`direct-streamlocal@openssh.com`, `forwarded-streamlocal@openssh.com`) and JavaScript method names (`n@app.get`, `n@app.patch`).

Public author names that appear in citations or pack attribution (blog authors, tool maintainers) are bibliographic attribution, not data-subject records.

Auxiliary `preferences.jsonl` and `quarantine.jsonl` were also scanned: no secrets, no emails, no identifiers (quarantine rows contain only IDs and reasons).

## 3. Synthetic identifiers, IPs and domains

All 77 source-derived records carry `synthetic_identifiers: true`; all 423 curated records are labelled `synthetic: true` with no synthetic-identifier flag (minor metadata asymmetry, see §5).

**IPv4:** 23 distinct addresses across the full records.
- **14 distinct** in RFC 5737 documentation ranges (`192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24`).
- **8 distinct** in private/loopback/wildcard space (five `10.20.30.0/24` hosts, `127.0.0.1`, `127.0.0.53`, and the wildcard `0.0.0.0`).
- **1** is `169.254.169.254`, the cloud IMDS link-local endpoint, used deliberately as the subject of IMDSv2 hardening guidance rather than as leaked target data.
- No public routable address appears anywhere in the splits.

**Domains:** all scenario hostnames use `example.internal`, `example.com`, `example.test` or `example-relay.test`, which are reserved or clearly illustrative. Real service hostnames that appear (`s3.amazonaws.com`, `graph.microsoft.com`, `registry.npmjs.org`, `attack.mitre.org`, `learn.microsoft.com`) are documentation references, not customer infrastructure.

**Low finding — non-reserved domain.** One record uses `updates.example-vendor.net` and `cdn.example-vendor.net` (`syn-monitoring-detection-soc-log-network-layers-012-triage-dialogue`). The `example-` label signals intent, but `.net` is a real registrable TLD and `example-vendor.net` is not guaranteed reserved. Use `example.net`, `vendor.example`, or `*.example.test` instead.

**Anonymisation defect (quality, not safety).** In `grnd-mitre-attack-mitre-attack-01d4a8ba2e991f0d-match`, the ATT&CK tool name **CMSTP** was rewritten to **“this behaviour.exe”**, producing the nonsensical upstream sentence “this behaviour.exe is a command-line program used to install Connection Manager service profiles.” The identifier-substitution pass should skip proper product/tool names.

## 4. Unsafe operational content

**Result: no content crosses the line into harmful instruction.**

Every record containing a high-risk term was read. The material falls into four defensible categories:

1. **Detection engineering** — ten Sigma-style rules (SSH brute force, Windows 4625 burst, encoded PowerShell, setuid drift, 404 burst, root-without-MFA, privileged pod, sudoers change, long DNS query, wildcard IAM). All describe what to detect, required telemetry, false positives and tuning. None is an attack procedure.
2. **Inert vulnerable code** — 20 secure-code-review records pair a deliberately vulnerable snippet with a secure fix and explicitly instruct *“Do not write exploit code.”* Snippets target no live system.
3. **Incident response / forensics** — ransomware, C2 and credential-theft records discuss behaviour, evidence and containment trade-offs. One record includes `vssadmin delete shadows /all /quiet` as **observed log evidence** in an investigation plan; it is not an instruction, and the surrounding answer is defensive.
4. **Defensive command examples** — forensic imaging (`dc3dd if=/dev/sdb …`) and Sysmon hunting for proxy-execution binaries. Both are evidence-collection or detection actions.

No record gives step-by-step weaponisation, malware construction, AV/EDR bypass, credential dumping, third-party targeting, ransomware operation or destructive action against a named host. Records that mention LSASS, Kerberoasting or C2 describe how to respond or detect, not how to perform.

## 5. Provenance and licensing metadata

### Required fields

All 500 split records carry `source`, `license`, `source_version`, `source_url`, `upstream_id`, `origin`, `group`, `content_hash` and a top-level `url`. Recomputed content hashes match **500/500**. `group` never spans splits and no content hash is duplicated across splits.

Licence counts match the manifest exactly:

| Licence | Records |
|---|---|
| Synthetic | 423 |
| Public-Domain | 26 |
| MITRE-CWE | 18 |
| IETF-Trust | 10 |
| MITRE-ATTACK | 10 |
| OpenSSH | 6 |
| Linux-man-pages-copyleft | 3 |
| CC-BY-SA-4.0 | 2 |
| GPL-3.0-or-later | 1 |
| Linux-man-pages-1-para | 1 |

Source-derived licences correctly inherit the registry: NVD → `Public-Domain`, ATT&CK → `MITRE-ATTACK`, CWE → `MITRE-CWE`, RFCs → `IETF-Trust`, OpenSSH → `OpenSSH`, man-pages → per-page SPDX, OWASP → `CC-BY-SA-4.0`. Curated records are uniformly `Synthetic` with `synthetic: true`; source-derived records are uniformly `synthetic: false` with `synthetic_identifiers: true`. No contradiction found.

All 77 `derivation_parent_id` values resolve to records in `data/processed/pilot-v2`. All source-derived `source_url` values contain the matching CVE/CWE/T-number/RFC number.

### Gaps and contradictions

| # | Severity | Gap | Evidence |
|---|---|---|---|
| P1 | **Medium** | `license_url` is present but empty on **all 423** curated-synthetic records. | Values are `""`; the registry has a usable URL (`https://github.com/braydos-h/CyberLite/blob/main/LICENSE`). |
| P2 | **Medium** | 4 detection records use an unregistered source identity. | `source_version: detection-library-v1`, `source_title: "CyberLite authored detection-rule teaching library"`; neither appears in `data/sources.yaml`. Values are hard-coded in `cyberlite/data/detection.py`. |
| P3 | **Medium** | Restricted reference licences are not inherited by records that cite them. | 12 records (8 train, 3 validation, 1 test) are labelled `Synthetic`/redistributable while their pack fact cites ISO/IEC 27037 (paid standard), Volatility VSL, Splunk docs, Micro Focus docs or Sigma DRL-1.1. Text appears paraphrased, but per-record attribution is absent. |
| P4 | **Medium** | Pack hash drift breaks build reproducibility. | `c1-fundamentals-linux-networking.json` hashes to `3f52467f…`; the manifest and 49 embedded `pack_sha256` values still carry `35f7a67b…`. The pack was modified at 13:14, after the 13:13 manifest. |
| P5 | **Low** | Split files and manifest are internally consistent, but the manifest’s evaluation inventory is stale. | 6 evaluation files on disk, only 3 in `contamination.files`. See §7. |
| P6 | **Low** | `synthetic_identifiers` is absent from all 423 curated records. | Only source-derived records carry the flag; adding it would make the anonymisation claim explicit. |
| P7 | **Low** | 4 detection records attach licence `Synthetic` to a Microsoft Learn URL. | `metadata.references[0].license == "Synthetic"` while `url` is third-party documentation. |
| P8 | **Low** | `preferences.jsonl` (183 pairs) has no `content_hash`, no top-level `url` and empty `license_url`. | Auxiliary file, outside the 500 scanned records. |

**AI vs human review.** `review_status` is `automated-screened` on all 500 records, `human_reviewed` is `false` on all 500, and the manifest records `manual_review.completed: false` with `human_reviewed_records: 0`. No record text or metadata claims human or manual review. AI review is therefore distinguishable, although the label “automated-screened” is less explicit than “ai-reviewed”; using the latter would remove ambiguity.

## 6. Pack references and licence labels

The packs contain 439 facts and several hundred references. Spot checks of well-known URLs succeeded: RFC 9525 and RFC 9745 titles match their use (TLS service identity, deprecation header), FIRST EPSS, Splunk, NIST SP 800-63-4 and Microsoft Win32 pages resolve with HTTP 200. The ISO/IEC 27037 page returned HTTP 403 (bot blocking), so its content could not be verified; the citation itself is plausible. One cve.org path resolved but is a JavaScript application and could not be content-verified without rendering.

No fabricated URL was proven. One structural concern remains: **reference licence labels are not normalised**. The same licence appears as `MITRE-CWE`, `MITRE CWE Terms of Use` and `MITRE-CWE-Terms-Of-Use`; IETF as `IETF-Trust`, `IETF Trust Legal Provisions`, `IETF Trust RFC copyright` and `IETF-Trust-Legal-Provisions`; CC-BY-SA as `CC-BY-SA-4.0` and `CC BY-SA 4.0`. This will cause under-counting in any automated licence aggregation and should be canonicalised to SPDX identifiers.

A small number of references are inherently non-redistributable or unclear: `ISO copyright (paid standard)` (2 pack facts), `Author blog, all rights reserved` (1), `Micro-Focus-Docs` (1), `Splunk-Docs` (1), `Volatility Software License (VSL)` (1), `CC-BY-NC-SA-3.0` (1). The fact text in each case reads as independent paraphrase rather than copied expression, but P3 above means the record-level licence does not reflect that constraint.

## 7. Evaluation-only material in training splits

**No leakage found.**

- No record has `dataset_stage` other than `calibration`, and none carries `evaluation_only`.
- No evaluation item shares a 13-gram at the manifest’s 0.2 threshold with any split record. Maximum observed overlap was **0.04** (one vulnerability item), essentially incidental shared terminology.
- The test split itself contains only `Synthetic` (20) and `IETF-Trust` (3) records; no evaluation item ID or suite name appears in any split.

**Coverage caveat (P5).** `cyberlite_eval_factual_v1.jsonl`, `cyberlite_eval_logs_ir_v1.jsonl` and `cyberlite_eval_vulnerability_v1.jsonl` (55 items each, 165 total) were written at 13:17, four minutes after the manifest was generated, and are not in `manifest.contamination.files`. The manifest’s “screened” status therefore does not cover the evaluation material actually on disk. The independent screen above found no overlap, but the manifest should be regenerated so the recorded evidence matches the files.

## 8. Findings summary

| ID | Severity | Finding | Action |
|---|---|---|---|
| F1 | Medium | `license_url` empty on 423/423 curated records | Populate from the registry or drop the field rather than shipping an empty value. |
| F2 | Medium | 4 detection records use unregistered `source_version`/`source_title` | Register `detection-library-v1` in `data/sources.yaml` or align the metadata. |
| F3 | Medium | 12 records labelled Synthetic/redistributable while citing restricted sources | Record inherited/reference licence per record or quarantine affected facts. |
| F4 | Medium | c1 pack hash drift; 49 records pin a stale pack hash | Rebuild after the pack settles, or revert the pack change. |
| F5 | Low | Manifest screens 3 of 6 evaluation files | Regenerate the contamination report. |
| F6 | Low | `example-vendor.net` is not a reserved domain | Replace with `example.net`/`*.example.test`. |
| F7 | Low | Reference licence labels inconsistent (MITRE/IETF/CC variants) | Canonicalise to SPDX. |
| F8 | Low | `synthetic_identifiers` missing on curated records | Add the flag for symmetry. |
| F9 | Low | Anonymiser rewrote “CMSTP” to “this behaviour.exe” | Exclude product names from placeholder substitution. |
| F10 | Low | `preferences.jsonl` lacks `content_hash` | Add if preferences are to be shipped as a dataset artefact. |
| F11 | Info | 7 public vendor role mailboxes in NVD metadata | Document or redact before any redistribution outside NVD terms. |

No High or Critical finding was identified. Nothing found requires removal of a record on safety grounds.

## 9. Limitations

- Regex plus manual inspection, not a trained secret/PII classifier; unusual formats could be missed.
- URL verification was a targeted spot check (eight URLs), not a crawl. The ISO page was bot-blocked and cve.org is a JavaScript application.
- Contamination screening is lexical (13-gram); paraphrase and conceptual reuse are not detectable.
- The c1 pack and three evaluation files changed after the manifest was produced, so this review describes the state of the working tree at scan time (pack mtime 13:14, eval files 13:17).
- Public vendor role addresses were treated as non-personal data. A stricter publication policy may disagree.
- No binary, archive or external linked content was opened.
- **AI review is not human review.** All 500 records remain unverified by a person.

## Files

- Report: `docs/reports/privacy-provenance-review.md`
- Machine-readable manifest: `data/manifests/synthesis-calibration/privacy_provenance.json`

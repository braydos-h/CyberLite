# Code and Configuration Verification — Synthesis Calibration

Date: 2026-11-25
Verifier: Agent F (independent code/configuration verification)
Scope: knowledge packs, calibration splits, detection-rule seed set
Method: static only; no snippet was executed

## 1. Result summary

| Measure | Value |
|---|---:|
| Extracted code/config/command artifacts | 767 |
| Artifacts skipped as intentional `___` completion blanks | 20 |
| Artifacts analysed | 747 |
| Detection-rule documents analysed | 10 |
| **Total checked** | **757** |
| **Passed** | **745** |
| **Failed** | **12** |
| Hard parser failures (genuine syntax errors) | 0 |
| Semantic / claim-consistency failures | 12 |

No syntax error was found in 593 parser-checked artifacts. All failures are semantic: a code pair that does not contain the named flaw or its fix, one invalid Dockerfile stage reference, one Windows command presented as bash, and detection rules or rule interpretations whose stated behavior is not implemented by their fields.

## 2. Inputs and extraction

- Calibration splits: `/home/bh/qwen-cyber/CyberLite/data/processed/synthesis-calibration/{train,validation,test}.jsonl` (500 records; 142 contain at least one code or configuration fence).
- Knowledge packs: `/home/bh/qwen-cyber/CyberLite/data/synthesis/knowledge/*.json` (8 domain packs, 439 facts).
- Detection rules: `/home/bh/qwen-cyber/CyberLite/data/synthesis/seeds/detection_rules.json` (10 rules).
- Schema references: `cyberlite/data/schema.py`, `cyberlite/data/synthesis.py` (used to understand record shape; no modifications made).

Extracted artifacts:

| Source | Code snippets | Config snippets | Commands | Total |
|---|---:|---:|---:|---:|
| Knowledge packs | 202 (101 vulnerable/secure pairs) | 116 | 243 | 561 |
| Calibration corpus | 169 fenced blocks | 37 fenced blocks | — | 206 |
| **Total** | **371** | **153** | **243** | **767** |

`preferences.jsonl` and `quarantine.jsonl` contain no code fences and were not part of the requested splits.

## 3. Checks performed

| Language/format | Tool or method | Parser used |
|---|---|---|
| Python | `ast.parse` | yes |
| Bash | `bash -n` on a temporary file under `/tmp/opencode` | yes |
| JSON | `json.loads` (plus duplicate-key scan) | yes |
| YAML / Kubernetes | `yaml.safe_load_all` (plus duplicate-key scan) | yes |
| JavaScript | `node --check` | yes (JSX not supported) |
| TypeScript | `node --check` would not accept type syntax; no TypeScript artifacts existed | n/a |
| Go | `gofmt -e` | yes (parse only) |
| Rust | `rustfmt --edition 2021 --emit stdout` | yes (parse only) |
| C | `gcc -fsyntax-only -std=c11` | yes |
| Java | `javac -proc:none` with a generated class/method wrapper | yes (syntax only) |
| SQL / KQL / SPL | manual inspection | no parser |
| PowerShell | manual inspection | no parser available |
| PHP | manual inspection | `php` not installed |
| nginx, sshd_config, sudoers, pam.d, audit.rules, systemd, dockerfile, nftables, ini, fstab, aide.conf, reg, nsswitch.conf, zone/dns-zone, authorized_keys, requirements.txt, http, phc-string, text | structural checks (brace balance, record/header shape, directive shape) plus manual inspection | no native validator |

Every knowledge-pack `code` pair (101 pairs, 202 snippets) was read for flaw presence, fix root cause, and claim consistency. The 44 corpus code pairs were compared with the pack pairs and are byte-identical, so the pair review covers both sources.

## 4. Counts per language

A "failure" below means a confirmed semantic defect; parse-only failures are zero. Skipped artifacts are intentional completion blanks (`___`) and are excluded from checked/passed/failed.

| Language/format | Checked | Passed | Failed | Skipped (blank) |
|---|---:|---:|---:|---:|
| yaml | 52 | 49 | 3 | 9 |
| bash | 251 | 249 | 2 | 0 |
| python | 163 | 163 | 0 | 0 |
| powershell | 51 | 51 | 0 | 0 |
| javascript | 44 | 42 | 2 | 0 |
| json | 31 | 31 | 0 | 0 |
| go | 20 | 20 | 0 | 0 |
| rust | 18 | 18 | 0 | 0 |
| nginx | 16 | 16 | 0 | 2 |
| http | 14 | 14 | 0 | 2 |
| sql | 13 | 13 | 0 | 0 |
| c | 12 | 12 | 0 | 0 |
| ini | 8 | 8 | 0 | 1 |
| dockerfile | 7 | 5 | 2 | 1 |
| systemd | 6 | 6 | 0 | 1 |
| text | 5 | 5 | 0 | 1 |
| audit.rules | 4 | 4 | 0 | 0 |
| java | 4 | 4 | 0 | 0 |
| phc-string | 3 | 3 | 0 | 0 |
| kubernetes | 2 | 2 | 0 | 0 |
| nftables | 2 | 2 | 0 | 0 |
| nsswitch.conf | 2 | 2 | 0 | 0 |
| php | 2 | 2 | 0 | 0 |
| requirements.txt | 2 | 2 | 0 | 0 |
| sshd_config | 2 | 2 | 0 | 1 |
| sudoers | 2 | 2 | 0 | 0 |
| zone | 2 | 2 | 0 | 1 |
| dns-zone | 2 | 2 | 0 | 1 |
| aide.conf | 1 | 1 | 0 | 0 |
| authorized_keys | 1 | 1 | 0 | 0 |
| fstab | 1 | 1 | 0 | 0 |
| kql | 1 | 1 | 0 | 0 |
| pam.d | 1 | 1 | 0 | 0 |
| reg | 1 | 1 | 0 | 0 |
| spl | 1 | 1 | 0 | 0 |
| **Subtotal (extracted artifacts)** | **747** | **738** | **9** | **20** |
| detection_rule_yaml (seed rules) | 10 | 7 | 3 | 0 |
| **Total** | **757** | **745** | **12** | **20** |

Machine-readable form of the same counts:

```json
{
  "checked": 757,
  "passed": 745,
  "failed": 12,
  "skipped_incomplete": 20
}
```

Reclassifications applied during review:

- Four JavaScript artifacts (`web-output-encoding-001`, knowledge and corpus) failed `node --check` only because the parser does not accept JSX. The JSX is well formed; they are counted as manually passed and are not counted as parser failures.
- Three HTTP configuration artifacts are header-field blocks (`Set-Cookie`, `Cache-Control`) rather than a request line. The structural request-line heuristic flagged them, but they are valid header snippets and are counted as passed.
- One nginx artifact (`syn-web-api-secure-development-web-rate-limiting-001-config-complete`, response fence) is intentionally a single opening line (`location = /login {`) completing a blank inside an existing block. Its unbalanced brace is expected for a completion answer and it is counted as passed.


## 5. Detection-rule verification

All 10 seed rules parse as YAML, contain a `detection` mapping and a `condition`, and every condition references a selection key that exists. Three rules fail the "explanation matches the fields" test:

| Rule | Parse | detection/condition | Claim vs fields |
|---|---|---|---|
| `det-ssh-bruteforce` | pass | pass | warning: aggregates `src_ip` never defined by the selection |
| `det-windows-failed-logon` | pass | pass | warning: says interactive or network, no LogonType filter |
| `det-powershell-encoded` | pass | pass | pass |
| `det-linux-setuid` | pass | pass | **FAIL**: never tests setuid/setgid |
| `det-web-404-burst` | pass | pass | pass |
| `det-cloudtrail-root-no-mfa` | pass | pass | pass |
| `det-k8s-privileged-pod` | pass | pass | **FAIL**: host namespaces claimed, not tested |
| `det-sudoers-change` | pass | pass | warning: audit-key dependency, no path check |
| `det-dns-long-query` | pass | pass | pass |
| `det-iam-wildcard-policy` | pass | pass | **FAIL**: never inspects wildcard actions |

## 6. Confirmed defects (counted as failures)

### D01 — `iam-webauthn-038`: neither snippet contains the named server-side flaw or fix

- Location: `data/synthesis/knowledge/c4-cryptography-identity-access.json`, fact `iam-webauthn-038`, `code.vulnerable` and `code.secure`.
- Evidence: the vulnerable snippet is browser code (`navigator.credentials.get`, then `fetch("/login", ...)`) with a comment saying the server "never checks where the assertion came from"; no server verification code is shown. The secure snippet only adds `rpId` and `userVerification` to the browser call and a comment that the server verifies `clientDataJSON.origin`, `rpIdHash` and `challenge`.
- Why it fails: the issue names a server-side validation defect and its root-cause fix. The code demonstrates neither. The pair proves the claim only by comment.
- Severity: high. Artifacts failed: 2.

### D02 — `cont-image-digest-pinning`: `COPY --from=build` with no `build` stage

- Location: `data/synthesis/knowledge/c5-cloud-container-supply-chain.json`, fact `cont-image-digest-pinning`, `configs`; corpus record `syn-cloud-container-supply-chain-cont-image-digest-pinning-config-1`.
- Evidence:

```dockerfile
FROM python:3.12-slim@sha256:ca978112... AS runtime
COPY --from=build /opt/app /opt/app
```

  There is no `FROM ... AS build`.
- Why it fails: no stage named `build` exists, so Docker resolves the reference as an external image named `build` and the build fails. The digest-pinning statement on the first line is correct, but the snippet as supplied is not a plausible Dockerfile.
- Severity: medium. Artifacts failed: 2.

### D03 — `forensics-amcache-028`: a Windows `reg.exe` command declared and prompted as bash

- Location: `data/synthesis/knowledge/c7-incident-response-forensics-threat-intel.json`, fact `forensics-amcache-028`, `commands`; corpus record `syn-incident-response-forensics-threat-intel-forensics-amcache-028-command-1`.
- Evidence:

```bash
reg save HKLM\SYSTEM /evidence/SYSTEM.hiv
```

  The metadata says `artifact_language: bash` and the prompt says "this bash command".
- Why it fails: `reg` is a Windows-only executable. In bash, the unquoted `\S` is an escape, so the key argument becomes `HKLMSYSTEM`; `/evidence/SYSTEM.hiv` is also a POSIX path. As a bash artifact it cannot perform the described SYSTEM-hive export. The explanatory text about Amcache vs ShimCache is accurate, but it explains a different (Windows) command than the labelled artifact.
- Severity: medium. Artifacts failed: 2.

### D04 — `det-linux-setuid`: rule does not test setuid execution

- Location: `data/synthesis/seeds/detection_rules.json#det-linux-setuid`.
- Evidence: purpose "Detect execution of a setuid binary outside the known administrative baseline"; YAML selection `type: EXECVE`, filter `exe|startswith` for `sudo`, `passwd`, `su`.
- Why it fails: no setuid/setgid mode or effective-UID field is tested. In auditd the executable path is a SYSCALL-record field, not an EXECVE field, so the baseline filter may not apply at all. The rule reduces to "all execve except three paths".
- Severity: high. Artifacts failed: 1.

### D05 — `det-iam-wildcard-policy`: rule does not inspect wildcard actions

- Location: `data/synthesis/seeds/detection_rules.json#det-iam-wildcard-policy`.
- Evidence: purpose "Detect attachment of a customer-managed policy granting wildcard actions"; detection is only `eventName: AttachRolePolicy`.
- Why it fails: no policy ARN, policy document, or `Action: "*"` predicate is tested, and user/group attachments are not covered. Every role policy attachment matches.
- Severity: high. Artifacts failed: 1.

### D06 — `det-k8s-privileged-pod`: host namespaces claimed but not tested

- Location: `data/synthesis/seeds/detection_rules.json#det-k8s-privileged-pod`.
- Evidence: purpose "privileged security context or host namespaces"; detection only `requestObject.spec.containers.securityContext.privileged: true`.
- Why it fails: `hostNetwork`, `hostPID` and `hostIPC` are absent. The `containers` field is an array and the unindexed path is backend-dependent. A privileged container is covered, but a host-network pod is not, contrary to the stated behavior.
- Severity: medium. Artifacts failed: 1.

### D07 — Corpus detection-rule records claim fields and a window that the rule lacks

- Locations: `det-det-k8s-privileged-pod-interpret`, `det-det-k8s-privileged-pod-gap`.
- Evidence: the interpret response says "detect ... privileged security context or host namespaces" and "evaluated over the events in the stated window"; the gap response says an adversary can operate "outside the counting window". The supplied rule has no host-namespace fields and no `timeframe`.
- Why it fails: the explanation contradicts the rule text. These records also propagate the D06 over-claim.
- Severity: medium. Artifacts failed: 2.

### D08 — `det-det-dns-long-query-interpret`: nonexistent timeframe

- Location: `det-det-dns-long-query-interpret`.
- Evidence: response says "The condition is evaluated over the events in the stated window"; the rule is only `query|re: '^.{80,}$'` with `condition: selection`, no `timeframe`.
- Why it fails: generic boilerplate copied from a windowed rule contradicts the supplied rule.
- Severity: low. Artifacts failed: 1.

## 7. Warnings (not counted as failures)

These are incomplete demonstrations, placeholder values, or unstated dependencies. They do not make the artifact's security claim false, but they weaken reuse and should be fixed before publication.

| ID | Location | Finding |
|---|---|---|
| W01 | `attack-privesc-056` configs (c7) | Registry fragment declared `ini`; missing `Windows Registry Editor Version 5.00` header, so not importable as `.reg` |
| W02 | `api-mass-assignment-001` (c2) | Issue requires verifying `uid` ownership; secure handler ignores `uid` and patches the authenticated user |
| W03 | `web-csrf-001` (c2) | Issue requires `csrf_token()` in the form template; secure snippet only enables `CSRFProtect` |
| W04 | `crypto-argon2id-008` (c4) | Secure function verifies only; the claimed Argon2id hashing call is not shown |
| W05 | `sdlc-dependency-pinning-001` (c2) + corpus config record | All-zero hash placeholders; `pip --require-hashes` would reject every artifact |
| W06 | `sc-lockfile-integrity-hashes` text config (c5) | `ca978112...` is SHA-256 of the one-byte string `a`, not requests 2.32.3; hash would not verify |
| W07 | `proto-ssh-user-auth` authorized_keys (c1) | Key body contains literal `...synthetic...`; invalid base64, sshd would reject the line |
| W08 | `sdlc-secure-defaults-001` (c2) | Uses `os.environ` without `import os`; not self-contained |
| W09 | `sdlc-secrets-001` (c2) | Workflow excerpt lacks `on:` and `jobs:`; not a valid standalone workflow |
| W10 | `det-windows-failed-logon` + corpus interpret record | "Interactive or network" claim but no LogonType filter; batch/service 4625 included |
| W11 | `det-ssh-bruteforce` | Aggregates `src_ip` that the selection never defines; field-mapping risk |
| W12 | `det-sudoers-change` | Matches only audit key `sudoers_change`; no path filter and no stated audit-rule dependency |
| W13 | `ps-encoded-002` decode command (c8) | Uses `$enc` defined by another command in the same list; not standalone |
| W14 | `proto-dns-record-types` (c1) | In-zone NS target `ns1` has no A/AAAA record; zone is a format example, not servable |

## 8. Positive consistency findings

- SQL pairs use bound parameters and allowlisted identifiers correctly (`web-sqli`, `py-sql`, `sql-inj`, `sql-param`, `rev-sql`), including the identifier case that cannot be parameterised.
- Command-injection pairs remove the shell rather than filtering metacharacters (`py-subprocess`, `web-command-injection`, `cwe-78`, `go-exec`, `rust-cmd`); path-traversal pairs resolve and compare against a base (`py-path`, `web-path-traversal`, `cwe-22`, `go-path`).
- Crypto pairs use library AEAD with fresh 96-bit nonces, `hmac.compare_digest`, Argon2id/scrypt/PBKDF2 parameters that match their prose, and `crypto/rand`/`secrets` for tokens.
- Cookie snippets satisfy the `__Host-` constraints they claim: `Secure`, `Path=/`, no `Domain`; SameSite values match the stated behavior.
- Kubernetes manifests parse and match their stated controls: default-deny NetworkPolicy, PSA `restricted` labels, KMS v2 provider ordering with identity as read fallback, `FORCE ROW LEVEL SECURITY` with both `USING` and `WITH CHECK`, and audit-policy rule ordering that keeps Secrets at Metadata before the namespace RequestResponse rule.
- Detection rules all parse and all conditions reference declared selections; the CloudTrail root/MFA, PowerShell encoded-command, 404-burst and DNS-length rules match their descriptions at field level.
- No secure snippet was found that merely blocklists a single payload. The two blocklist-style fixes (`js-proto-001`, `cwe-1321-prototype-pollution`) also use own-property iteration and null-prototype objects, which addresses the root cause.

## 9. Coverage limits

1. **Static only.** No snippet was executed. Syntax checks do not prove runtime behavior, and no exploit was run.
2. **No type checking or symbol resolution.** `ast.parse`, `node --check`, `gofmt`, `rustfmt`, `gcc -fsyntax-only` and scaffolded `javac` do not resolve imports or types. Undefined names in illustrative fragments (for example `load_key`, `ISSUER`, `AUD`, `current_user`, `verifyPassword`, and the missing `os` in W08) were not treated as syntax failures.
3. **Parser gaps.** 51 PowerShell, 13 SQL, 1 KQL and 1 SPL artifacts had no parser and were inspected manually. Two PHP artifacts had no interpreter and were inspected manually. Four JSX snippets could not be parsed by `node --check` and were inspected manually. No TypeScript artifacts were present.
4. **Config formats lack native validators.** `nginx -t`, `docker build`, `sshd -t`, `visudo -c`, `kubeconform`/`kubeval`, `hadolint`, `sqlfluff` and a Sigma compiler were unavailable or not run. Config checks are structural plus manual, not authoritative.
5. **YAML semantics.** PyYAML implements YAML 1.1; for example the GitHub Actions key `on:` is parsed as boolean `true`. The GitHub workflow snippets were therefore reviewed manually as well as parsed. No CRD/OpenAPI schema validation was performed.
6. **JSON semantics.** `json.loads` checks syntax and a duplicate-key scan was run, but no JSON Schema or cloud-provider policy validation was performed. IAM/SCP/KMS snippets were checked by reading, not by an IAM simulator.
7. **Detection rules were not compiled or executed.** Field mappings, backend aggregation support and log-source field names were assessed from the rule text only.
8. **Semantic coverage is asymmetric.** All 101 knowledge code pairs were read; all 153 config artifacts were read for claim plausibility; the 243 commands were syntax-checked and their stated purposes were spot-checked (flag/claim alignment), not exhaustively verified line by line.
9. **Duplication.** All 44 corpus vulnerable/secure pairs are byte-identical to knowledge-pack pairs, and the corpus Dockerfile record duplicates D02. Defects in packs therefore propagate into the corpus; this report does not treat the duplicates as independent evidence.
10. **Scope.** The `preferences.jsonl` and `quarantine.jsonl` files were not part of the requested calibration splits and contain no code fences.

## 10. Artifacts written

- This report: `/home/bh/qwen-cyber/CyberLite/docs/reports/code-config-verification.md`
- Machine-readable manifest: `/home/bh/qwen-cyber/CyberLite/data/manifests/synthesis-calibration/code_verification.json`

The manifest contains `checked`, `passed`, `failed`, `by_language`, `defects`, `unavailable_tools`, and `method: "static only; no execution"`. Each counted defect records how many artifacts it accounts for; the counted defects sum to 12.

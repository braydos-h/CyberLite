# Source and license report

This report is a research aid, not legal advice. Public accessibility does not imply permission for unrestricted use. Verify upstream terms before redistributing derived text or a trained model.

| License | Records | Sources | Attribution | Permitted uses | Redistribution |
|---|---:|---|---|---|---|
| CC-BY-SA-4.0 | 1965 | owasp_cheatsheets | required | training, research | Share-alike; redistribution of derived text must satisfy CC BY-SA 4.0. |
| GPL-1.0-or-later | 6 | linux_man_pages | required | training, research | Copyleft; redistribute only with the license text and notices. |
| GPL-2.0-only | 40 | netfilter_nftables | required | training, research | Copyleft; redistribution of derived text may trigger GPL obligations. |
| GPL-2.0-or-later | 10 | linux_man_pages | required | training, research | Copyleft; redistribution of derived text may trigger GPL obligations. |
| GPL-3.0-or-later | 8 | linux_man_pages | required | training, research | Copyleft; redistribution of derived text may trigger GPL obligations. |
| IETF-Trust | 393 | ietf_rfcs | required | training, research | Subject to the IETF Trust legal provisions; retain copyright notices. |
| Linux-man-pages-1-para | 67 | linux_man_pages | required | training, research | One-paragraph permission notice; preserve it with copies. |
| Linux-man-pages-copyleft | 155 | linux_man_pages | required | training, research | Permission to copy and distribute verbatim or modified versions with the notice preserved. |
| MITRE-ATTACK | 959 | mitre_attack | required | training, research, commercial-use | Raw STIX is not redistributed; derived records remain subject to MITRE terms. |
| MITRE-CWE | 906 | mitre_cwe | required | training, research, commercial-use | Raw CWE XML is not redistributed; derived records preserve CWE identifiers. |
| Mixed-SPDX | 0 | linux_man_pages | required | training, research | Per-document SPDX licenses; see each record's license field. |
| OpenSSH | 28 | openssh_docs | required | training, research | BSD-style OpenSSH licence; retain the copyright and permission notice. |
| Public-Domain | 2615 | nist_nvd | not required | training, research, commercial-use, redistribution | Generally permitted for U.S. Government works; NVD requests attribution. |
| Synthetic | 36 | project_examples | not required | training, research, redistribution | Project-authored content; repository code is Apache-2.0. |

## Unresolved licensing questions

The following identifiers have no positively reviewed permitted-use set and must not be treated as cleared for redistribution:


- `CC-BY-SA-4.0`:
  - CyberLite does not redistribute OWASP text.
  - Whether a trained model or derived training corpus is a derivative work is unsettled.
- `GPL-1.0-or-later`:
  - Derived-corpus licensing is unsettled.
- `GPL-2.0-only`:
  - Derived-corpus and model-output licensing is unsettled.
  - Mixed GPL-2.0-only and GPL-2.0-or-later contributions; treated conservatively as GPL-2.0-only.
- `GPL-2.0-or-later`:
  - Derived-corpus and model-output licensing is unsettled.
- `GPL-3.0-or-later`:
  - Derived-corpus and model-output licensing is unsettled.
- `IETF-Trust`:
  - Derived-text redistribution requires a terms review.
- `Linux-man-pages-1-para`:
  - Training use is not explicitly addressed.
- `Linux-man-pages-copyleft`:
  - Training use is not explicitly addressed; no derived text is redistributed.
- `MITRE-ATTACK`:
  - Derived-text redistribution requires a terms review.
  - Whether a derived training corpus or model is a derivative work remains a legal question.
- `MITRE-CWE`:
  - Derived-text redistribution requires a terms review.
- `Mixed-SPDX`:
  - Documents without an explicit SPDX line are quarantined.
  - Pages without an SPDX header are quarantined and excluded from the corpus.
  - Training use of Linux-man-pages-copyleft pages is not explicitly addressed.
- `Synthetic`:
  - Human quality and safety review is pending for all project-authored records.
  - No human quality review has been completed.

## Redistribution policy

CyberLite commits manifests and reports only. Raw downloads, derived splits, and restricted benchmark items remain outside Git.

Restricted benchmark content (for example SecEval) is evaluation-only and is never committed or ingested. See `data/evaluation/README.md`.

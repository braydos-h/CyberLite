# Source and licensing review

**Status:** proposed, not approved. Date: 2026-11-25. Reviewer: Agent B.
**Scope:** close CyberLite coverage gaps for Windows security, cloud security
(AWS/Azure/GCP), Kubernetes, containers, software supply chain, IAM and
authentication, secure coding in Go/Rust/C/JavaScript, detection engineering,
incident response, digital forensics, malware behaviour, threat intelligence,
risk assessment, and general programming retention.

This review proposes **22 candidates** in
[`data/synthesis/source_candidates.yaml`](../../data/synthesis/source_candidates.yaml)
and records **11 rejections or quarantines**. Every proposed entry has
`enabled: false`; no non-commercial, no-derivatives, unlicensed, or
benchmark-only source is proposed for training. License identifiers and full
URLs are recorded in the YAML; this report explains the reasoning and the
remaining risk.

## Method and verification standard

I read `AGENTS.md`, `CONTRIBUTING.md`, `data/sources.yaml`, `DATASET_CARD.md`,
`docs/dataset.md`, `cyberlite/data/sources.py`, and
`cyberlite/data/licensing.py`. I then checked raw `LICENSE` files, GitHub
license metadata, and official license or terms pages on 2026-11-25. I did not
acquire bulk source text or run any training. Claims not directly verified are
marked **UNVERIFIED**.

The review uses four tests:

1. Is the license identifier and license URL explicit?
2. Does the license permit training and commercial use?
3. Does it permit redistribution of raw or derived text, and with what
   attribution or share-alike obligations?
4. Is there a stable pinned revision and an ingest path compatible with the
   current normalizers?

## Ranked shortlist

Ranking favours clean licensing, authoritative provenance, and low legal
ambiguity over raw volume. "Raw redist." means redistribution of source text,
not the separate question of whether a trained model is a derivative work.

| # | Candidate (homepage) | Gap | License | Pin | Training | Raw redist. | Contam. | Verdict |
|---:|---|---|---|---|---|---|---|---|
| 1 | [NIST SP 800-61r3](https://csrc.nist.gov/pubs/sp/800/61/r3/final) | incident response | [Public-Domain](https://www.nist.gov/open/license) | 2025-04-03 | yes | yes | low | approve after PDF normalizer |
| 2 | [NIST SP 800-86](https://csrc.nist.gov/pubs/sp/800/86/final) | digital forensics | [Public-Domain](https://www.nist.gov/open/license) | 2006-09-01 | yes | yes | low | approve; pair with current guidance |
| 3 | [NIST SP 800-30 Rev. 1](https://csrc.nist.gov/pubs/sp/800/30/r1/final) | risk assessment | [Public-Domain](https://www.nist.gov/open/license) | 2012-09-17 | yes | yes | low | approve; pair with CSF 2.0 |
| 4 | [NIST SP 800-218](https://csrc.nist.gov/pubs/sp/800/218/final) | supply chain | [Public-Domain](https://www.nist.gov/open/license) | 2022-02-03 | yes | yes | low | approve after PDF normalizer |
| 5 | [NIST SP 800-63B-4](https://csrc.nist.gov/pubs/sp/800/63/b/4/final) | IAM/authentication | [Public-Domain](https://www.nist.gov/open/license) | 2025-07-31 | yes | yes | low | approve after PDF normalizer |
| 6 | [Kubernetes docs](https://kubernetes.io/docs/concepts/security/) | Kubernetes | [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) | `1ad3951` | yes | yes | low | approve; review per-file code |
| 7 | [OCI Runtime Spec v1.3.0](https://github.com/opencontainers/runtime-spec) | containers | [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0) | v1.3.0 | yes | yes | low | approve |
| 8 | [SEI CERT C](https://cmu-sei.github.io/secure-coding-standards/) | C secure coding | [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) | `73ee7a0` | yes | yes | medium | approve; code is MIT |
| 9 | [SigmaHQ rules](https://github.com/SigmaHQ/sigma) | detection engineering | [DRL-1.1](https://github.com/SigmaHQ/Detection-Rule-License) | `7228ccc` | yes | conditional | low-med | legal review of DRL |
| 10 | [Splunk Security Content](https://github.com/splunk/security_content) | detection engineering | [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0) | `689e177` | yes | yes | low | approve |
| 11 | [capa rules](https://github.com/mandiant/capa-rules) | malware behaviour | [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0) | `ffd03fc` | yes | yes | low | approve; safety filter |
| 12 | [Go security documentation](https://go.dev/doc/security/) | Go secure coding | [BSD-3-Clause](https://opensource.org/license/bsd-3-clause) | `0eef789` | yes | yes | medium | approve; screen benchmarks |
| 13 | [The Rust Book](https://doc.rust-lang.org/book/) | Rust/programming | [MIT OR Apache-2.0](https://github.com/rust-lang/book#license) | `5c23042` | yes | yes | medium | approve; screen benchmarks |
| 14 | [MISP taxonomies](https://github.com/MISP/misp-taxonomies) | threat intelligence | [CC0-1.0](https://creativecommons.org/publicdomain/zero/1.0/) | `bd9d844` | yes | yes | low | approve |
| 15 | [AWS Security Hub guide](https://docs.aws.amazon.com/securityhub/latest/userguide/what-is-securityhub.html) | AWS cloud security | [CC-BY-SA-4.0](https://creativecommons.org/licenses/by-sa/4.0/) | `8923bfa` | yes | conditional | low | approve with share-alike review |
| 16 | [Azure security best practices](https://learn.microsoft.com/en-us/azure/security/fundamentals/best-practices-and-patterns) | Azure cloud security | [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) | `2c8012d` | yes | conditional | low | Microsoft TOU review |
| 17 | [Windows Server security](https://learn.microsoft.com/en-us/windows-server/security/security-and-assurance) | Windows security | [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) | `b640f2c` | yes | conditional | low | Microsoft TOU review |
| 18 | [Windows authentication](https://learn.microsoft.com/en-us/windows-server/security/windows-authentication/windows-authentication-overview) | Windows/IAM | [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) | `b640f2c` | yes | conditional | low | Microsoft TOU review |
| 19 | [Google Cloud security framework](https://cloud.google.com/architecture/framework/security) | GCP cloud security | [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) | site snapshot | yes | yes | low | needs a pinned snapshot |
| 20 | [MDN Web Security](https://developer.mozilla.org/en-US/docs/Web/Security) | JavaScript/web | [CC-BY-SA-2.5](https://creativecommons.org/licenses/by-sa/2.5/) | `eeebbb8` | yes | conditional | medium | share-alike review |
| 21 | [SLSA v1.2](https://slsa.dev/spec/v1.2/) | supply chain | [Community-Spec-1.0](https://github.com/slsa-framework/slsa/blob/v1.2/LICENSE.md) | v1.2 | yes | conditional | low | legal review of custom license |
| 22 | [RFC 9700](https://www.rfc-editor.org/rfc/rfc9700.html) | OAuth security | [IETF-Trust](https://trustee.ietf.org/license-info) | 2025-01 | yes | conditional | low | add to existing IETF selection |

### Why the top group ranks highest

The NIST publications are the cleanest: U.S. Government works are generally
not copyrighted in the United States, NIST grants worldwide reuse for its
technical series, and attribution is requested rather than required. They cover
incident response, forensics, risk, secure SDLC, and authentication with
authoritative language. The main cost is engineering: CyberLite has no
`pdf_text` normalizer yet, so these cannot be enabled until one exists.

Kubernetes, OCI, CERT C, Splunk, capa, Go, Rust, and MISP have standard,
well-understood licenses. Their main risks are per-file notices in large
repositories, share-alike for AWS and MDN prose, and benchmark overlap for
programming content.

Sigma and SLSA use custom but permissive-looking licenses. They are usable in
principle, but "training a model" is not expressly addressed. They should not
be enabled without counsel or a written clarification.

## Gap coverage map

| Gap | Proposed source(s) | Coverage note |
|---|---|---|
| Windows security | Windows Server security, Azure Windows guidance | Windows Server, not Windows client; no clean client-security repo was verified |
| Cloud: AWS | AWS Security Hub User Guide | Archived but pinned; use current docs for operations |
| Cloud: Azure | Azure security best practices | Single pinned file from a very large repo |
| Cloud: GCP | Google Cloud Architecture Framework | CC BY 4.0, but no stable revision |
| Kubernetes | Kubernetes documentation | Official project docs |
| Containers | OCI Runtime Specification | Normative runtime/container contract |
| Supply chain | NIST SSDF, SLSA v1.2 | Process framework plus build-level provenance |
| IAM/auth | NIST 800-63B-4, RFC 9700, Windows authentication | OIDC/SAML specs are quarantined; use OWASP for protocol-specific guidance |
| Go secure coding | Go security documentation | Security-resource hub, not a complete secure-coding standard |
| Rust secure coding | The Rust Book | Memory-safety orientation; not a security standard |
| C secure coding | SEI CERT C | Rules, examples, and risk assessments |
| JavaScript secure coding | MDN Web Security | Web platform security; CC BY-SA share-alike |
| Detection engineering | SigmaHQ, Splunk Security Content | Vendor-neutral and vendor-specific rules |
| Incident response | NIST SP 800-61r3 | CSF 2.0 community profile |
| Digital forensics | NIST SP 800-86 | Older but authoritative; supplement with current material |
| Malware behaviour | capa rules | Capability-detection logic, not malware samples |
| Threat intelligence | MISP taxonomies | Controlled vocabulary, not narrative reporting |
| Risk assessment | NIST SP 800-30 Rev. 1 | Classic risk method; pair with CSF 2.0 |
| Programming retention | Go security docs, Rust Book, MDN | General language and web material |

## Licensing risk table

| Risk class | Sources | Obligations and unresolved questions | Decision |
|---|---|---|---|
| Low | NIST public-domain set, MISP CC0 | No U.S. copyright; NIST asks for acknowledgment, change notice, and no endorsement. Foreign rights and third-party figures still need care. | approve after normalizer |
| Low | Kubernetes, CERT C, GCP | CC BY 4.0: attribution, license notice, modification notice, no endorsement. GCP has no stable pin. | approve conditionally |
| Low | OCI, Splunk, capa | Apache 2.0: LICENSE/NOTICE, mark modified files, patent grant, no trademark endorsement. | approve |
| Low | Go, Rust | BSD-3-Clause or MIT/Apache-2.0: retain notices, no endorsement. | approve |
| Medium | AWS, MDN | CC BY-SA 4.0/2.5: attribution plus share-alike on adapted material. Whether a model or a derived corpus is "adapted material" is unsettled. | legal review |
| High | Azure, Windows Server docs | CC BY 4.0 repository license, but Microsoft Learn TOU claims non-commercial use and no derivative works. The conflict is unresolved. | legal review; keep disabled |
| Medium | Sigma DRL 1.1 | Custom license. Sharing requires author attribution and a license notice. Training scope is not express. | legal review |
| Medium | SLSA Community Spec 1.0 | Custom license. Attribution must name the material, version, and source. Patent terms apply. Training scope is not express. | legal review |
| Medium | IETF RFC 9700 | IETF Trust/BCP 78. Retain notices; modified RFC text needs review. | add to existing IETF source |
| High | Microsoft Learn website (not repos) | TOU claims personal, non-commercial use and no derivative works; repository LICENSE grants CC BY 4.0. The TOU says explicit license terms control, but training use is untested. | quarantine until counsel |
| High | OpenID Connect, OASIS SAML | Custom licenses limited to specification development and implementation; training a model is outside the stated purpose. | reject/quarantine |

## Rejections and quarantines

| Source | Claimed license or status | Reason | Decision |
|---|---|---|---|
| SecEval | CC-BY-NC-SA-4.0 | Non-commercial and share-alike; benchmark-only and evaluation-only. | reject for training |
| CyberSecEval | Upstream benchmark terms; not locally available | Benchmark-only; no confirmed training or redistribution right; also an open contamination-coverage blocker. | reject for training |
| Elastic Detection Rules | Elastic License 2.0 | Non-OSI; prohibits providing the software as a hosted or managed service; training use is not expressly granted. | reject |
| CIS Benchmarks | Proprietary subscription | License restricts copying, redistribution, and derivative use; no training right. | reject **UNVERIFIED** exact terms |
| ISO/IEC 27001 and 27005 | Copyrighted standards | Paywalled; no training or redistribution right. | reject **UNVERIFIED** exact terms |
| SANS Reading Room and posters | Copyright, limited reuse | No explicit training or redistribution permission; some items are non-commercial. | reject **UNVERIFIED** exact terms |
| VirusTotal, MalwareBazaar | Service terms | Bulk access and redistribution are restricted; malware samples create safety and PII/credential risk. | reject **UNVERIFIED** exact terms |
| OpenID Connect Core 1.0 | OIDF custom copyright license | Grants reproduction and derivative works "solely for the purposes of" developing specifications and implementing them; training is not within that stated purpose. | reject/quarantine |
| OASIS SAML 2.0 | OASIS custom copyright terms | Copying and derivative-work permissions are limited; training permission is not explicit. | quarantine **UNVERIFIED** exact clause |
| Microsoft Learn website (not GitHub repos) | Microsoft Learn TOU | Personal, non-commercial use; no modification, derivative works, or redistribution without consent. Conflicts with the CC BY 4.0 repository LICENSE. | quarantine until counsel |
| Docker documentation | License not verified | Docker terms and documentation licensing were not confirmed in this review. | quarantine **UNVERIFIED** |

## Recommended next actions

1. **Get a Microsoft opinion.** Ask counsel whether the repository CC BY 4.0
   license or the Microsoft Learn TOU controls training and redistribution for
   Windows Server and Azure docs. Until then, keep those entries disabled and
   `redistributable: false`.
2. **Do not ingest OIDC or SAML specifications.** Their custom licenses are
   aimed at specification development and implementation, not training. Use
   NIST SP 800-63B-4, RFC 9700, and the existing OWASP Cheat Sheets for
   authentication coverage.
3. **Build the missing normalizers.** Add `pdf_text` for NIST, `yaml_rules` for
   Sigma/Splunk/capa, `json_taxonomy` for MISP, and either `html_docs` or a
   dated Markdown snapshot pipeline for Google Cloud. Do not enable an entry
   whose `kind` has no normalizer.
4. **Curate, do not bulk-download.** The Azure, Windows Server, Kubernetes,
   MDN, and Go repositories are large. Pin a commit, acquire only the selected
   files, store SHA-256 hashes, and record the allowlist in the build config.
5. **Audit per-file notices.** Repository-level CC BY 4.0 or Apache 2.0 may not
   cover images, diagrams, quoted third-party text, or code samples. Exclude
   unlicensed media and record per-file licenses.
6. **Re-run contamination screening.** Add cloud certification, CKS, secure
   coding, programming, and SOC/detection benchmarks to the 13-gram screen.
   Keep SecEval and CyberSecEval evaluation-only and out of training.
7. **Resolve custom licenses.** Obtain written clarification for Sigma DRL 1.1
   and SLSA Community Specification 1.0 on model training and derived-corpus
   redistribution. Treat silence as "not approved".
8. **Pin Google Cloud.** Create a dated, hashed snapshot of the selected pages,
   or find an authoritative GitHub mirror. A live URL is not a reproducible
   revision.
9. **Require human approval.** Every YAML entry is `enabled: false`. A reviewer
   must approve the license, revision, normalizer, and contamination screen
   before any build includes it.
10. **Record the change.** `AGENTS.md` requires a changelog entry. This review
    intentionally did not modify existing files, so the entry and any
    `DATASET_CARD.md`/`docs/dataset.md` updates remain for the integrating
    change.

## Limitations of this verification

- Licenses were checked on 2026-11-25. Upstream terms can change; re-verify at
  acquisition time and store the license URL and revision with the manifest.
- Raw `LICENSE` files were read for most repositories. CIS, ISO, SANS,
  VirusTotal, the exact OASIS SAML clause, and Docker documentation are marked
  **UNVERIFIED** because their terms were not fetched or parsed in full.
- This is not legal advice. No counsel reviewed the Microsoft TOU conflict, the
  share-alike scope, the custom Sigma/SLSA licenses, or the model-derivative
  question.
- Repository-level licenses do not guarantee that every file, image, diagram,
  or code sample is covered. A per-file audit is still required.
- No bulk source text was acquired and no content-quality review was performed.
  The candidates are judged on provenance and licensing, not on pedagogical
  quality.
- NIST works are public domain in the United States but may be subject to
  foreign copyright; NIST grants worldwide reuse for its technical series, but
  third-party figures may differ.
- Google Cloud has no pinned revision in this review. The proposed snapshot is
  a process, not a verified artifact.
- Contamination risk is qualitative. No n-gram measurement was run for the new
  candidates.
- Whether a trained model or a derived training corpus is a derivative work is
  unsettled for CC BY-SA, DRL, Community Specification, and IETF material.
- Windows client security remains a gap. The verified Microsoft repository
  covers Windows Server; no clean, public, appropriately licensed Windows
  client source was confirmed.

# Governance

CyberLite is a single-maintainer research project. This page states how
decisions, money, and releases are handled so that a funder, contributor, or
reviewer knows what they are dealing with. It is intentionally short.

## Status and open decisions

| Item | State |
|---|---|
| Maintainer | Brayden Habets |
| Team size | One person; no employees, contractors, or co-maintainers |
| Legal entity able to receive funds | **Not yet recorded** — see below |
| Fiscal host (if any) | **None** |
| Trademark | Unregistered; the name is used descriptively |
| Code license | Apache-2.0 |
| Data and model licenses | Per source; see [DATASET_CARD.md](DATASET_CARD.md) |

**Open decision — funds.** Before accepting money, record one of: a registered
company, a sole proprietorship, a university arrangement, or a fiscal host. A
funder cannot pay a GitHub repository. This is a blocking item for any grant or
sponsorship above in-kind hardware.

## Decisions

- **Routine changes** (code, docs, tests) are made by the maintainer and recorded
  in [CHANGELOG.md](CHANGELOG.md).
- **Research claims** require the evidence rules in
  [CONTRIBUTING.md](CONTRIBUTING.md): raw predictions, configuration, dataset
  version, hardware, and seeds. The maintainer cannot waive this for a favorable
  number.
- **Pre-registered analysis** is changed only through a dated deviation entry in
  [docs/preregistration.md](docs/preregistration.md), never silently.
- **Safety-blocking results** (see H6 in the pre-registration) override benchmark
  gains. A single maintainer decision can block a release; a benchmark gain
  cannot force one.
- **Contributions** are accepted by pull request. Review covers correctness,
  licensing, safety, and reproducibility, in that order.

## Money

- Hardware is the default use of funds. No cloud credits, rentals, or recurring
  subscriptions are requested.
- No salaries, contractors, or hires are assumed. If a funder wants to pay
  maintainer time, it is a separate agreement recorded in this file.
- Paid external review is allowed where it buys independence (evaluation
  protocol, safety review, paper), and is recorded as a distinct line item.
- Any single purchase over **$500** is listed publicly with its purpose in the
  changelog.
- Donated hardware is recorded on the project website and stays with the project
  unless the donor requests return.
- No funds are used for benchmark access that requires redistributing restricted
  test items.
- If the project winds down, unspent restricted funds are returned or
  transferred to a fiscal host; hardware is offered to a successor maintainer or
  donated to a public-interest lab.

## Conflicts of interest

The maintainer discloses employment, consulting, sponsorship, or hardware
donations that could affect a research claim. A disclosure does not disqualify a
result, but it is printed next to it in the paper and the release notes.

## Key-person risk

- Every experiment is reproducible from committed configuration, hashes, and
  commands; no result depends on a local notebook.
- Model weights and large artifacts are published with a DOI where licenses
  allow, not held only on one machine.
- If the maintainer becomes unavailable for **90 days**, the repository stays
  readable and the last release stays downloadable. A successor may fork under
  the Apache-2.0 license; the project name is not transferred without a written
  note in this file.
- The bus factor is currently **one**. Reducing it means external review,
  published artifacts, and collaboration, not a hire; a second maintainer would
  require a separate arrangement.

## Releases and claims

- A release is a tagged commit plus a changelog section. Research artifacts are
  versioned by dataset manifest and effective-configuration hash, not only by
  package version.
- No model is described as "safe", "production-ready", or "state of the art"
  without the evidence required by the paper's reporting rules.
- Security reports follow [SECURITY.md](SECURITY.md), not public issues.

## Changing this document

Amendments are pull requests with a changelog entry. Material changes to money
handling, licensing, or research-claim rules are announced on the project
website before they take effect.

# Security policy

## Supported versions

CyberLite is a research preview. Security fixes are applied to the `main` branch
and the latest tagged release. There is no long-term support commitment.

| Version | Supported |
|---|---|
| 0.1.x | Yes |
| < 0.1 | No |

## Reporting a vulnerability

Please **do not open a public issue** for a vulnerability.

Use GitHub's private vulnerability reporting for this repository
(**Security → Advisories → Report a vulnerability**). If that is unavailable,
contact the maintainers through the repository's listed security contact.

Include:

- affected version or commit,
- a minimal reproduction,
- impact and attack preconditions,
- whether generated command execution or data exfiltration is involved,
- any suggested remediation.

We aim to acknowledge reports within seven days and to publish a coordinated
advisory when a fix is available. This is a volunteer research project; no bug
bounty is offered.

## Security model

CyberLite explicitly does **not** execute model output. The primary security
properties are:

- generated text is returned as data;
- the autocomplete and inference APIs have no shell/tool execution surface;
- dataset preparation redacts common secrets before training;
- the local API binds to loopback by default and supports a bearer token;
- RAG evidence is labelled untrusted.

These properties can be weakened by integrators. If you build an agent, command
runner, or editor auto-apply feature on top of CyberLite, you own the sandbox,
authorization, and review controls.

## Out of scope

- Model hallucinations or incorrect security advice (report as a model-quality
  issue, not a software vulnerability);
- Prompt-injection content in third-party datasets (report upstream, and to us
  if the pipeline handles it unsafely);
- Vulnerabilities in PyTorch, Transformers, PEFT, FastAPI, or other dependencies
  (report upstream, and notify us if CyberLite's usage amplifies impact);
- Denial of service from intentionally huge local prompts on a single-user
  machine (still welcome as a hardening report).

## Safe harbor

We support good-faith security research on CyberLite itself. Do not test against
systems or data you do not own or have explicit permission to use. Do not upload
production secrets or personal data while reproducing an issue.

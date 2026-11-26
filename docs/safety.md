# Safety and responsible use

## Scope

CyberLite is intended for **defensive** security research, education, detection
engineering, secure coding, and authorized lab work. It is not a penetration
testing service, an autonomous agent, or an incident-response authority.

## Hard boundaries in the code

- No generated command or code is executed by the inference, evaluation, or
  server modules.
- Evaluation checks Python syntax with `ast.parse`; it never imports or runs
  generated code.
- The local API has no tool-calling or shell tool surface.
- RAG evidence is labelled untrusted and the system prompt tells the model not
  to follow instructions embedded in retrieved text.

These are code-level boundaries, not a complete security architecture.

## Threats to consider

### Prompt injection

Source documents, code comments, README files, and retrieved evidence can
contain instructions aimed at the model. The RAG prompt marks evidence as data,
but a model can still be influenced. Treat outputs as untrusted, validate
citations, and never wire model output directly into an executor.

### Data leakage

Prompts may contain credentials, customer data, or sensitive logs. The local
service does not send data to a provider, but logs, feedback files, crash dumps,
and evaluation outputs can persist. Configure retention, redact before logging,
and avoid sending production secrets to any model.

### Harmful or dual-use content

Cybersecurity corpora contain exploitation and malware discussions. The project
focuses on defensive framing and remediation, but a language model can
recombine knowledge in unsafe ways. Apply organizational policy, rate limits, and
human review. Do not deploy CyberLite to advise on actions outside authorized
environments.

### Over-trust

Small models are fluent and can be wrong. A confident answer is not evidence.
Require verification against authoritative sources, version-specific advisories,
and tested configurations.

## Dataset safety

- Prefer licensed, authoritative sources.
- Do not include live credentials, personal data, or target data from
  unauthorized environments.
- Secret scanning and redaction are best-effort; review quarantine and samples.
- Authorized lab exercises must state scope and authorization and contain no
  real target data.
- Benchmark test items must stay out of training.

## Model release checklist

Before publishing a checkpoint or adapter:

- [ ] Document base model, license, and adapter license.
- [ ] Publish the dataset manifest, not restricted raw data.
- [ ] Report evaluation tasks, licenses, prompts, and limitations.
- [ ] Red-team for prompt injection, credential leakage, and harmful guidance.
- [ ] Include a model card with intended use and out-of-scope use.
- [ ] Provide a contact for security reports.
- [ ] Do not claim safety or production readiness without evidence.

## Deployment checklist

- [ ] Bind to loopback or place behind authenticated, encrypted access.
- [ ] Set `CYBERLITE_API_KEY` if the service is reachable by other users.
- [ ] Disable request logging of prompt bodies or redact them.
- [ ] Never connect output to a shell, CI runner, or production system.
- [ ] Monitor resource use and rate-limit requests.
- [ ] Keep the model, tokenizer, and dependencies patched.
- [ ] Provide a human escalation path for security decisions.

## Reporting

Report vulnerabilities in CyberLite according to [SECURITY.md](../SECURITY.md).
Report vulnerabilities in upstream models or datasets to their maintainers.

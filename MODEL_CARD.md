# CyberLite model card

## Model details

| Field | Value |
|---|---|
| Model name | CyberLite (research preview) |
| Version | 0.1.0 (repository scaffold; no research checkpoint released) |
| Base model | `Qwen/Qwen3.5-0.8B` (instruct); matched runs pin revision `2fc06364715b967f1860aea9cf38778875588b17` |
| Architecture | `Qwen3_5ForConditionalGeneration`; hybrid linear/full attention, multimodal, text-only use |
| Parameters | 852,985,920 total; 100,592,896 vision; LoRA adapters add ~2.7M at rank 4 |
| Adaptation | LoRA / 4-bit QLoRA supervised fine-tuning |
| Planned variants | Base reference, LoRA, QLoRA, offline-distilled, RAG, quantized |
| Repository license | Apache-2.0 for original code |
| Base model license | Apache-2.0 (verify upstream) |
| Contact | Repository issues; security reports via private advisory |

### Released artifacts

- **No trained research checkpoint or adapter is released in 0.1.0.**
- The smoke adapter under `runs/` (if generated locally) is a two-step pipeline
  validation artifact. It is not a cybersecurity model.
- The repository releases code, configurations, tests, and a paper scaffold.

## Intended use

CyberLite is intended for:

- research on parameter-efficient cybersecurity adaptation;
- measuring performance/compute trade-offs on consumer hardware;
- local, offline experimentation and teaching;
- defensive detection engineering, secure coding, and remediation drafting with
  human review;
- cybersecurity-aware completion research in editors and lab notebooks.

## Out-of-scope use

Do not use CyberLite as:

- an autonomous penetration-testing or exploitation system;
- an incident-response authority or source of final security decisions;
- a medical, legal, or compliance authority;
- a replacement for vulnerability databases, vendor advisories, or expert review;
- a system that executes generated commands without a sandbox and authorization;
- a tool for surveilling, attacking, or accessing systems without explicit
  permission.

## Factors

Relevant variation includes:

- **Language:** primarily English technical content; other languages are
  untested.
- **Domain:** defensive security, Linux/networking operations, secure coding,
  vulnerability management, detection rules.
- **Deployment:** CPU (slow), consumer GPU, Apple MPS; 4/8-bit quantization;
  context length.
- **Prompt style:** chat/instruct vs raw completion; FIM vs prefix completion.
- **Data mix:** ATT&CK/CWE/NVD-derived explanations vs project-authored
  workflows and code.

## Metrics

Planned metrics, with exact definitions in `docs/evaluation.md`:

- MCQ accuracy with bootstrap confidence intervals;
- vulnerability classification accuracy, macro F1, false-positive rate;
- secure code completion exact match, token F1, edit similarity, Python syntax
  validity;
- grounded QA token F1 and a lexical unsupported-token proxy;
- refusal and execution-claim rates;
- general capability retention;
- peak training VRAM, peak inference memory, latency, throughput;
- estimated cost only with explicit rates;
- performance per billion parameters and per dollar.

No metric has been measured for a research CyberLite checkpoint. The untrained
base model's SecEval baseline is recorded in
[`results/baseline/e0-instruct-seceval/`](results/baseline/e0-instruct-seceval/README.md).
It describes the starting point, not a CyberLite model.

## Evaluation data

Obtained locally and not redistributed: a pinned SecEval revision (CC BY-NC-SA
4.0, evaluation-only) and project-authored held-out tasks. CyberSecEval /
CyberSecEval 2 remain planned because their tasks require upstream terms and, for
the attack-helpfulness suite, a judge model. The bundled `smoke_eval.jsonl` is
synthetic and for pipeline validation only.

## Training data

No research training corpus is released. The planned pipeline uses licensed
public sources and project-authored examples, with provenance, secret redaction,
deduplication, contamination screening, and a frozen-manifest integrity gate.
See `DATASET_CARD.md`. The committed smoke corpus is 34 original synthetic
records.

Research training is **not currently authorized** by the repository: the
pilot-v2 license report contains unresolved model-output questions, the manual
quality/safety review is incomplete, and the analysis plan is not externally
pre-registered. The preflight reports these as research blockers instead of
treating public accessibility as training permission.

## Quantitative analyses

There are no verified benchmark results, fairness audits, or red-team
measurements for a trained CyberLite model. The only real-benchmark measurement
in the repository is the untrained base model's SecEval baseline. Any numbers in
issues or drafts must be treated as unverified until reproduced and reviewed.

## Ethical considerations

- Cybersecurity knowledge is dual-use. The project emphasizes defensive framing,
  authorization, and human review.
- Small models can hallucinate commands, CVEs, mitigations, and citations.
- Training data may contain outdated or vulnerable guidance; verify against
  current advisories.
- Dataset licenses may impose attribution, share-alike, non-commercial, or
  redistribution constraints.
- Local deployment reduces data exposure but does not remove logging or endpoint
  risk.
- Accessibility is a goal: the project should remain usable without paid APIs or
  enterprise hardware.

## Caveats and recommendations

- Treat all output as untrusted.
- Never execute generated commands automatically.
- Report the exact base model, adapter, quantization, prompt, and decoding
  settings with any result.
- Measure memory and latency on the target hardware; planning estimates are not
  guarantees.
- Do not claim safety, accuracy, or production readiness without evidence.
- Re-evaluate after every base-model, library, or dataset update.

## Usage

```python
from cyberlite.inference.engine import InferenceEngine, GenerationSettings

engine = InferenceEngine(
    "Qwen/Qwen3.5-0.8B",
    adapter_path="runs/qlora",   # replace with a validated adapter
    device="cpu",
)
result = engine.chat(
    [{"role": "user", "content": "How do I verify SSH host keys?"}],
    GenerationSettings(max_new_tokens=256, temperature=0.0),
)
print(result.text)
```

See `README.md`, `docs/inference.md`, and `docs/safety.md`.

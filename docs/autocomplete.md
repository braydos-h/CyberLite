# Cybersecurity autocomplete

## What it is

A local completion service for code, shell commands, detection rules, and
configuration. It returns **text as data**. It does not execute, evaluate, or
write generated commands to disk.

## Modes

| Mode | Prompt | Use when |
|---|---|---|
| `fim` | `<|fim_prefix|>{prefix}<|fim_suffix|>{suffix}<|fim_middle|>` | Checkpoint was trained for fill-in-the-middle |
| `prefix` | Instruction/chat prompt with before/after-cursor context | Instruction-tuned models, or FIM quality is inadequate |
| `auto` | FIM if the tokenizer defines FIM tokens, else prefix | Default; inspect the returned `mode` |

The Qwen3.5 tokenizer defines FIM control tokens, but token presence does **not**
guarantee the checkpoint was trained for FIM. In a CPU smoke test, the
two-step smoke adapter returned a poor FIM completion (a single `/`) while the
prefix path was more coherent. That is an engineering observation on an
intentionally undertrained adapter, not a scientific result. Treat FIM quality
as an experimental variable and always report which mode was used.

## Supported profiles

`bash`, `python`, `powershell`, `yara`, `sigma`, `regex`, `bpf`, `tcpdump`,
`nginx`, `dockerfile`, `sql`, `json`, `generic`.

Detection uses an explicit `language`, a filename extension, or `auto` fallback.
Profiles choose a fence and comment style for instruction prompts; they do not
claim language-server semantics.

## API

```bash
cyberlite-autocomplete \
  --model Qwen/Qwen3.5-0.8B \
  --adapter runs/qlora \
  --device cpu \
  --port 8765
```

```bash
curl http://127.0.0.1:8765/v1/autocomplete \
  -H 'Content-Type: application/json' \
  -d '{
    "prefix": "def safe_join(base: Path, value: str) -> Path:\n",
    "suffix": "\n",
    "language": "python",
    "mode": "auto",
    "max_tokens": 96
  }'
```

Response fields include `completion`, `language`, `mode`, `latency_seconds`,
`prompt_tokens`, `completion_tokens`, `tokens_per_second`, `peak_memory`,
`fim_supported`, `executed: false`, `requires_review: true`, and a warning.

`/health` reports FIM availability and supported languages. Language models can
be wrong; the response is untrusted input for the editor.

## Editor integration

CyberLite does not ship an editor extension. Any client that can POST JSON can
integrate:

1. Capture the text before and after the cursor (bounded to a few thousand
   characters).
2. Infer the language from the filename or send it explicitly.
3. POST to `/v1/autocomplete`.
4. Show the returned `completion` as a suggestion, not as an automatic edit.
5. Optionally POST acceptance feedback to `/v1/autocomplete/feedback`.

Keep the service bound to `127.0.0.1` unless you add authentication and network
controls. Set `CYBERLITE_API_KEY` to require a bearer token.

## Measuring completion quality

Offline metrics implemented in the evaluation harness:

- exact match against a held-out completion,
- token F1 and mean character edit similarity,
- Python syntax validity (`ast.parse`, no execution),
- latency, time to first token for streaming, tokens/second, peak memory.

Online metric:

```text
acceptance_rate = accepted_suggestions / shown_suggestions
```

Feedback storage records **hashes**, not completion text, by default:

```bash
cyberlite-autocomplete ... --feedback-file results/autocomplete_feedback.jsonl
python scripts/autocomplete_metrics.py results/autocomplete_feedback.jsonl
```

Acceptance is biased by suggestion quality, UI, latency, and user population.
Report the protocol, number of suggestions, and confidence interval. Do not
present acceptance as correctness.

## Safety properties

- The engine has no `subprocess`, shell, or tool-execution path.
- Generated commands are returned as strings and flagged for review.
- Prompt-injection text in code comments is untrusted input; the instruction
  prompt says to complete code, not follow comments.
- Secrets should not be sent to remote services; this service is local.
- Logs and feedback should not contain sensitive code by default.

See [SECURITY.md](../SECURITY.md) and [docs/safety.md](safety.md).

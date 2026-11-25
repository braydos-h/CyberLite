# Programmatic synthesis inputs

This directory holds **original, structured knowledge packs** used by
`scripts/synthesize_dataset.py` to build the CyberLite synthetic training
corpus. Packs are authored content, not scraped text. They are committed because
they are small, redistributable, and make the corpus reproducible without a
network connection or a paid model API.

Rules:

- Never paste third-party text into a pack. Write the explanation in your own
  words and record the primary reference (title, publisher, URL, license).
- Facts must be checkable against an authoritative primary source. If a
  behaviour is version-specific, name the version.
- Commands and code samples must be inert examples. Do not include live
  credentials, customer data, real hostnames, or instructions for causing harm.
- Use synthetic identifiers (`host-01`, `example.internal`, `10.20.30.0/24`,
  `203.0.113.0/24`, `2001:db8::/32`).
- The pipeline rejects a pack that fails schema validation. Duplicate fact IDs
  across packs are a hard error.

## Pack format

`knowledge/_schema.json` is the JSON Schema. Every pack is one JSON object:

```json
{
  "schema_version": 1,
  "domain": "linux-security",
  "display_name": "Linux host security",
  "author": "worker:C1",
  "facts": [
    {
      "id": "lnx-perm-001",
      "subtopic": "file-permissions",
      "difficulty": "intermediate",
      "title": "Why a world-writable directory without the sticky bit is risky",
      "fact": "Two to five sentences of accurate explanation.",
      "details": ["A concrete supporting detail.", "Another one."],
      "pitfalls": ["A common wrong belief or operational mistake."],
      "commands": [
        {"language": "bash", "code": "find /tmp -xdev -type d -perm -0002 ! -perm -1000", "purpose": "Find world-writable directories without the sticky bit."}
      ],
      "configs": [
        {"language": "sshd_config", "snippet": "PermitRootLogin no", "purpose": "Disable direct root SSH login."}
      ],
      "code": [
        {"language": "python", "vulnerable": "...", "secure": "...", "issue": "..."}
      ],
      "logs": [
        {"context": "sshd auth log", "text": "...", "reading": "..."}
      ],
      "mcqs": [
        {"question": "...", "options": ["...", "..."], "answer": [0], "rationale": "..."}
      ],
      "misconceptions": [
        {"claim": "A wrong but plausible claim.", "correction": "The correction with evidence."}
      ],
      "references": [
        {"title": "Linux man-pages: chmod(2)", "publisher": "Linux man-pages project", "url": "https://man7.org/linux/man-pages/man2/chmod.2.html", "license": "Linux-man-pages-copyleft"}
      ],
      "tags": ["permissions", "sticky-bit"]
    }
  ]
}
```

Optional fields may be omitted. Every fact must have `id`, `subtopic`,
`difficulty`, `title`, `fact`, and at least one `reference`. `details`,
`commands`, `configs`, `code`, `logs`, `mcqs`, `misconceptions`, and `pitfalls`
are optional, but a pack whose facts never carry a concrete artifact (command,
config, code, log, or MCQ) is low value and may be rejected at review.

Difficulty values: `foundational`, `intermediate`, `advanced`, `expert`.

## Evaluation authoring

`eval_authored/` is written by authors who are isolated from training-pack
authors. Evaluation items use a different schema (`eval/_schema.json`) and are
never consumed by the training synthesiser.

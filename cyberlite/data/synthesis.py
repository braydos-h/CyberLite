"""Deterministic synthesis of training records from curated knowledge packs.

The synthesiser is intentionally boring: it composes authored facts into several
task families with stable IDs and explicit provenance. It never calls a model at
build time, so a corpus can be rebuilt byte-for-byte from the committed packs.

Every record is grouped by its source fact (``synthesis:<fact-id>``) so that
multiple task views of one fact cannot straddle train/validation/test.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cyberlite.data.schema import Record, sha256_file

PACK_SCHEMA_VERSION = 1
SYNTHESIS_VERSION = "synthesis-v1"
DOMAINS = {
    "fundamentals-linux-networking",
    "web-api-secure-development",
    "vulnerability-classification-remediation",
    "cryptography-identity-access",
    "cloud-container-supply-chain",
    "monitoring-detection-soc",
    "incident-response-forensics-threat-intel",
    "language-security-retention",
}
DIFFICULTIES = ("foundational", "intermediate", "advanced", "expert")
ARTIFACT_LANGUAGES = {
    "bash",
    "powershell",
    "sql",
    "yaml",
    "json",
    "nginx",
    "nftables",
    "sshd_config",
    "dockerfile",
    "kubernetes",
    "toml",
    "ini",
    "http",
    "python",
    "javascript",
    "typescript",
    "go",
    "rust",
    "c",
    "java",
    "php",
}
MAX_FACT_CHARS = 2400
MAX_ARTIFACT_CHARS = 3000


class PackValidationError(ValueError):
    """A knowledge pack violates the committed schema."""


@dataclass
class Fact:
    pack_domain: str
    pack_author: str
    pack_sha256: str
    raw: dict[str, Any]

    @property
    def id(self) -> str:
        return str(self.raw["id"])

    @property
    def subtopic(self) -> str:
        return str(self.raw["subtopic"])

    @property
    def difficulty(self) -> str:
        return str(self.raw["difficulty"])

    @property
    def title(self) -> str:
        return str(self.raw["title"])

    @property
    def fact(self) -> str:
        return str(self.raw["fact"])

    @property
    def details(self) -> list[str]:
        return [str(item) for item in self.raw.get("details", [])]

    @property
    def pitfalls(self) -> list[str]:
        return [str(item) for item in self.raw.get("pitfalls", [])]

    @property
    def references(self) -> list[dict[str, str]]:
        return [dict(item) for item in self.raw.get("references", [])]

    @property
    def group(self) -> str:
        return f"synthesis:{self.pack_domain}:{self.id}"

    def metadata(self, task_family: str) -> dict[str, Any]:
        first_reference = self.references[0] if self.references else {}
        return {
            "group": self.group,
            "domain": self.pack_domain,
            "subtopic": self.subtopic,
            "difficulty": self.difficulty,
            "task_family": task_family,
            "source_version": SYNTHESIS_VERSION,
            "source_title": "CyberLite curated synthesis knowledge pack",
            "source_url": first_reference.get("url", ""),
            "license_url": "https://github.com/braydos-h/CyberLite/blob/main/LICENSE",
            "upstream_id": self.id,
            "synthetic": True,
            "origin": "curated-synthetic",
            "generation_method": "curated-fact-composition",
            "authoring_agent": self.pack_author,
            "pack_sha256": self.pack_sha256,
            "references": self.references,
            "review_status": "automated-screened",
            "human_reviewed": False,
        }


@dataclass
class KnowledgePack:
    domain: str
    display_name: str
    author: str
    path: str
    sha256: str
    facts: list[Fact] = field(default_factory=list)

    def validate(self) -> None:
        if self.domain not in DOMAINS:
            raise PackValidationError(f"{self.path}: unknown domain {self.domain!r}")
        if not self.display_name.strip():
            raise PackValidationError(f"{self.path}: display_name is empty")
        if not self.author.strip():
            raise PackValidationError(f"{self.path}: author is empty")
        if not self.facts:
            raise PackValidationError(f"{self.path}: pack has no facts")
        seen: set[str] = set()
        for fact in self.facts:
            if fact.id in seen:
                raise PackValidationError(f"{self.path}: duplicate fact id {fact.id!r}")
            seen.add(fact.id)


@dataclass
class SynthesisResult:
    records: list[Record]
    preferences: list[dict[str, Any]]
    packs: list[KnowledgePack]
    stats: dict[str, Any]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PackValidationError(message)


def _string_list(value: Any, field_name: str, maximum: int) -> list[str]:
    if value is None:
        return []
    _require(isinstance(value, list), f"{field_name} must be a list")
    items = [str(item).strip() for item in value]
    _require(all(items), f"{field_name} must not contain empty strings")
    _require(len(items) <= maximum, f"{field_name} has more than {maximum} items")
    return items


def _validate_fact(payload: Any, path: str) -> dict[str, Any]:
    _require(isinstance(payload, dict), f"{path}: fact must be an object")
    required = {"id", "subtopic", "difficulty", "title", "fact", "references"}
    missing = required - set(payload)
    _require(not missing, f"{path}: missing fields {sorted(missing)}")
    allowed = required | {
        "details",
        "pitfalls",
        "commands",
        "configs",
        "code",
        "logs",
        "mcqs",
        "misconceptions",
        "tags",
    }
    unknown = set(payload) - allowed
    _require(not unknown, f"{path}: unknown fields {sorted(unknown)}")

    fact_id = str(payload["id"])
    _require(
        re.fullmatch(r"[a-z][a-z0-9-]{2,63}", fact_id) is not None,
        f"{path}: invalid id {fact_id!r}",
    )
    _require(bool(str(payload["subtopic"]).strip()), f"{path}: empty subtopic")
    _require(
        str(payload["difficulty"]) in DIFFICULTIES,
        f"{path}: invalid difficulty {payload['difficulty']!r}",
    )
    title = str(payload["title"]).strip()
    fact_text = str(payload["fact"]).strip()
    _require(8 <= len(title) <= 160, f"{path}: title length out of range")
    _require(80 <= len(fact_text) <= MAX_FACT_CHARS, f"{path}: fact length out of range")

    payload["details"] = _string_list(payload.get("details"), f"{path}.details", 8)
    payload["pitfalls"] = _string_list(payload.get("pitfalls"), f"{path}.pitfalls", 6)
    payload["tags"] = _string_list(payload.get("tags"), f"{path}.tags", 10)

    references = payload.get("references")
    _require(isinstance(references, list), f"{path}: references must be a list")
    _require(bool(references), f"{path}: references required")
    _require(len(references) <= 5, f"{path}: too many references")
    for index, reference in enumerate(references):
        _require(isinstance(reference, dict), f"{path}: reference {index} must be an object")
        for key in ("title", "publisher", "url", "license"):
            _require(
                bool(str(reference.get(key, "")).strip()),
                f"{path}: reference {index} missing {key}",
            )
        _require(
            str(reference["url"]).startswith(("https://", "http://")),
            f"{path}: reference {index} URL must be http(s)",
        )

    for key in ("commands", "configs", "code", "logs", "mcqs", "misconceptions"):
        items = payload.get(key, [])
        _require(isinstance(items, list), f"{path}.{key} must be a list")
        _require(len(items) <= 6, f"{path}.{key} has more than 6 items")
        for index, item in enumerate(items):
            _require(isinstance(item, dict), f"{path}.{key}[{index}] must be an object")
            _require(bool(item), f"{path}.{key}[{index}] must not be empty")
            if key in {"code"}:
                for code_key in ("language", "vulnerable", "secure", "issue"):
                    _require(
                        bool(str(item.get(code_key, "")).strip()),
                        f"{path}.{key}[{index}] missing {code_key}",
                    )
                _require(
                    str(item["language"]) in ARTIFACT_LANGUAGES,
                    f"{path}.{key}[{index}] unsupported language",
                )
                _require(
                    len(str(item["vulnerable"])) <= MAX_ARTIFACT_CHARS
                    and len(str(item["secure"])) <= MAX_ARTIFACT_CHARS,
                    f"{path}.{key}[{index}] artifact too long",
                )
            if key == "mcqs":
                options = item.get("options")
                answers = item.get("answer")
                _require(
                    isinstance(options, list) and 3 <= len(options) <= 6,
                    f"{path}.mcqs[{index}] needs 3-6 options",
                )
                _require(
                    isinstance(answers, list) and 1 <= len(answers) <= 3,
                    f"{path}.mcqs[{index}] needs 1-3 answers",
                )
                _require(
                    all(
                        isinstance(value, int) and 0 <= int(value) < len(options)
                        for value in answers
                    ),
                    f"{path}.mcqs[{index}] answer index out of range",
                )
                _require(
                    len(set(int(value) for value in answers)) == len(answers),
                    f"{path}.mcqs[{index}] duplicate answer index",
                )
                _require(
                    bool(str(item.get("question", "")).strip())
                    and bool(str(item.get("rationale", "")).strip()),
                    f"{path}.mcqs[{index}] needs question and rationale",
                )
            if key == "misconceptions":
                _require(
                    bool(str(item.get("claim", "")).strip())
                    and bool(str(item.get("correction", "")).strip()),
                    f"{path}.misconceptions[{index}] needs claim and correction",
                )
            if key == "logs":
                for log_key in ("context", "text", "reading"):
                    _require(
                        bool(str(item.get(log_key, "")).strip()),
                        f"{path}.logs[{index}] missing {log_key}",
                    )
            if key == "commands":
                for command_key in ("language", "code", "purpose"):
                    _require(
                        bool(str(item.get(command_key, "")).strip()),
                        f"{path}.commands[{index}] missing {command_key}",
                    )
            if key == "configs":
                for config_key in ("language", "snippet", "purpose"):
                    _require(
                        bool(str(item.get(config_key, "")).strip()),
                        f"{path}.configs[{index}] missing {config_key}",
                    )
    return payload


def load_pack(path: str | Path) -> KnowledgePack:
    file_path = Path(path)
    payload = json.loads(file_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PackValidationError(f"{file_path}: pack must be a JSON object")
    _require(
        payload.get("schema_version") == PACK_SCHEMA_VERSION,
        f"{file_path}: schema_version must be {PACK_SCHEMA_VERSION}",
    )
    for key in ("domain", "display_name", "author", "facts"):
        _require(key in payload, f"{file_path}: missing {key}")
    _require(isinstance(payload["facts"], list), f"{file_path}: facts must be a list")
    digest = sha256_file(file_path)
    pack = KnowledgePack(
        domain=str(payload["domain"]),
        display_name=str(payload["display_name"]),
        author=str(payload["author"]),
        path=str(file_path),
        sha256=digest,
    )
    for index, fact_payload in enumerate(payload["facts"]):
        validated = _validate_fact(fact_payload, f"{file_path}:fact[{index}]")
        pack.facts.append(
            Fact(
                pack_domain=pack.domain,
                pack_author=pack.author,
                pack_sha256=pack.sha256,
                raw=validated,
            )
        )
    pack.validate()
    return pack


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _pick(options: list[str], key: str) -> str:
    if not options:
        raise ValueError("cannot pick from an empty list")
    return options[int(_digest(key)[:12], 16) % len(options)]


def _bullets(items: Iterable[str], *, limit: int = 6) -> str:
    selected = [item.strip() for item in items if item.strip()][:limit]
    return "\n".join(f"- {item}" for item in selected)


def _verification_hint(language: str, key: str) -> str:
    """A concrete, read-only check for a configuration directive."""

    lowered = language.lower()
    if lowered in {"sshd_config", "ssh_config"}:
        return f"run `sshd -T` or `ssh -G` and confirm the effective value of `{key}`"
    if lowered == "nginx":
        return f"render with `nginx -T` and locate the effective `{key}` directive"
    if lowered in {"kubernetes", "yaml"}:
        if "detection:" in key.lower() or "logsource:" in key.lower():
            return "load the rule in the target SIEM, replay a safe synthetic event, and confirm the expected match and field mapping"
        if "kind:" in key.lower():
            return f"inspect the admitted object with `kubectl get -o yaml` and confirm `{key}` survived defaulting and admission"
        return "parse the YAML and inspect the effective object after defaults and admission"
    if lowered == "dockerfile":
        return "run the built image as a non-root user and inspect the process UID, mounts, and capabilities"
    if lowered == "json":
        return "parse the effective policy with the provider's policy simulator or an equivalent read-only evaluator"
    return "reload the service and read the effective value from the running process"


def _security_code_issue(issue: str) -> bool:
    terms = re.compile(
        r"inject|traversal|overflow|underflow|authentic|authoriz|credential|secret|"
        r"crypto|cipher|hash|salt|xss|csrf|ssrf|deserial|permission|privilege|race|"
        r"prototype|path|exec|shell|tls|certificate|sanit|escape|access|disclos|"
        r"spoof|tamper|denial|dos|buffer|use-after|double-free|command|sql|template",
        re.IGNORECASE,
    )
    return bool(terms.search(issue))


def _record(
    fact: Fact,
    *,
    suffix: str,
    task: str,
    prompt: str,
    response: str,
    family: str,
    kind: str = "completion",
    messages: list[dict[str, str]] | None = None,
    prefix: str | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> Record:
    metadata = fact.metadata(family)
    metadata["task_family"] = family
    metadata["synthesis_version"] = SYNTHESIS_VERSION
    if extra_metadata:
        metadata.update(extra_metadata)
    record_id = f"syn-{fact.pack_domain}-{fact.id}-{suffix}"
    record_id = re.sub(r"[^a-z0-9-]", "-", record_id.lower())[:120]
    payload: dict[str, Any] = {
        "id": record_id,
        "source": "cyberlite_synthesis",
        "license": "Synthetic",
        "task": task,
        "url": metadata.get("source_url", ""),
        "metadata": metadata,
    }
    if messages is not None:
        payload["messages"] = messages
    elif prefix is not None:
        payload["prefix"] = prefix
        payload["suffix"] = response
        payload["middle"] = prompt
    else:
        payload["prompt"] = prompt
        payload["response"] = response
    record = Record.from_dict(payload)
    if kind == "fim" and record.kind != "fim":
        raise ValueError(f"{record_id}: expected a FIM record")
    return record


def _base_answer(fact: Fact) -> str:
    parts = [fact.fact]
    if fact.details:
        parts.append("Key specifics:\n" + _bullets(fact.details))
    if fact.pitfalls:
        parts.append("Common mistakes:\n" + _bullets(fact.pitfalls, limit=4))
    return "\n\n".join(parts)


def _base_question(fact: Fact) -> str:
    templates = [
        (
            "A security engineer is reviewing {subtopic} for a production service. "
            "Explain the following point and state the conditions that make the guidance "
            "apply and any operational mistake to avoid: {title}."
        ),
        (
            "During a design review, a colleague asks for a precise explanation of this "
            "topic: {title}. Give the technical answer, including the specific settings, "
            "defaults, or failure modes that matter."
        ),
        (
            "What should an analyst understand about {subtopic} to apply this correctly? "
            "Topic: {title}. Give concrete conditions and verification steps, not a definition."
        ),
        (
            "Training brief: {title}. Explain it to an engineer who will verify the "
            "behaviour in a lab, and call out the assumptions and failure modes that "
            "the verification should test."
        ),
    ]
    template = _pick(templates, f"base-question:{fact.id}")
    return template.format(
        subtopic=fact.subtopic.replace("-", " "),
        title=fact.title,
    )


def _mcq_prompt(question: str, options: list[str], *, multiple: bool) -> str:
    letters = "ABCDEFGH"
    rendered = "\n".join(f"{letters[index]}. {text}" for index, text in enumerate(options))
    instruction = "Select all correct options." if multiple else "Select the single best option."
    return f"{question}\n\n{rendered}\n\n{instruction}"


def _mcq_answer(letters: list[str], rationale: str, fact: Fact) -> str:
    label = "Correct answers" if len(letters) > 1 else "Correct answer"
    return f"**{label}: {', '.join(letters)}**\n\n{rationale}\n\nSupporting point: {fact.fact}"


def _shuffle_options(
    options: list[str], answers: list[int], key: str
) -> tuple[list[str], list[int]]:
    indexed = list(enumerate(options))
    indexed.sort(key=lambda pair: _digest(f"{key}:{pair[1]}"))
    new_answers: list[int] = []
    shuffled: list[str] = []
    old_to_new: dict[int, int] = {}
    for new_index, (old_index, text) in enumerate(indexed):
        shuffled.append(text)
        old_to_new[old_index] = new_index
    for answer in answers:
        new_answers.append(old_to_new[answer])
    return shuffled, sorted(new_answers)


def _letters(indexes: list[int]) -> list[str]:
    return ["ABCDEFGH"[index] for index in indexes]


def generate_fact_records(fact: Fact) -> tuple[list[Record], list[dict[str, Any]]]:
    """Compose one fact into several task families.

    The number of views is bounded and deterministic. Every available artifact
    gets at most one view, and the base explanation is emitted once so a single
    fact cannot flood the corpus with paraphrase variants.
    """

    records: list[Record] = []
    preferences: list[dict[str, Any]] = []

    base_prompt = _base_question(fact)
    base_family = "general-retention" if fact.id.startswith("gen-") else "instruction-response"
    records.append(
        _record(
            fact,
            suffix="explain",
            family=base_family,
            task="security-knowledge",
            prompt=base_prompt,
            response=_base_answer(fact),
        )
    )

    for index, mcq in enumerate(fact.raw.get("mcqs", [])[:2]):
        options, answers = _shuffle_options(
            [str(item) for item in mcq["options"]],
            [int(item) for item in mcq["answer"]],
            f"{fact.id}:mcq:{index}",
        )
        prompt = _mcq_prompt(
            str(mcq["question"]),
            options,
            multiple=len(answers) > 1,
        )
        response = _mcq_answer(
            _letters(answers),
            str(mcq["rationale"]),
            fact,
        )
        records.append(
            _record(
                fact,
                suffix=f"mcq-{index + 1}",
                family=("multiple-choice-multi-answer" if len(answers) > 1 else "multiple-choice"),
                task="security-knowledge",
                prompt=prompt,
                response=response,
                extra_metadata={
                    "mcq_options": options,
                    "mcq_answer_indexes": answers,
                    "multi_answer": len(answers) > 1,
                },
            )
        )

    for index, misconception in enumerate(fact.raw.get("misconceptions", [])[:1]):
        claim = str(misconception["claim"])
        correction = str(misconception["correction"])
        prompt = (
            f'A teammate states: "{claim}"\n\n'
            "Is the statement correct? If not, correct it and explain the practical "
            "consequence of acting on it."
        )
        response = (
            f"No. {correction}\n\n"
            f"Why it matters: {fact.fact.split('. ')[0]}.\n\n"
            "Verify the correction against the deployed configuration or test case before "
            "relying on it."
        )
        records.append(
            _record(
                fact,
                suffix=f"misconception-{index + 1}",
                family="misconception-correction",
                task="security-knowledge",
                prompt=prompt,
                response=response,
                extra_metadata={"misconception": claim},
            )
        )
        # A preference pair contrasts the corrected answer with the claim. The
        # rejected side is clearly wrong, not merely a differently worded answer.
        preferences.append(
            {
                "id": f"pref-syn-{fact.pack_domain}-{fact.id}-{index + 1}",
                "source": "cyberlite_synthesis",
                "license": "Synthetic",
                "prompt": prompt,
                "chosen": response,
                "rejected": (
                    f"Yes. {claim} This is a common configuration baseline, so no "
                    "further verification is needed."
                ),
                "metadata": {
                    **fact.metadata("preference-pair"),
                    "task_family": "preference-pair",
                    "rejection_reason": "unsupported_absolute_claim",
                    "group": fact.group,
                },
            }
        )

    for index, log in enumerate(fact.raw.get("logs", [])[:2]):
        context = str(log["context"])
        text = str(log["text"]).strip()
        reading = str(log["reading"]).strip()
        prompt = (
            f"Review this {context} excerpt:\n\n```\n{text}\n```\n\n"
            "What does it support, what does it not prove, and what is the next "
            "verification step? Distinguish observations from inferences."
        )
        response = (
            f"{reading}\n\n"
            f"Relevant principle: {fact.fact}\n\n"
            "Do not treat a single log line as proof of intent. Correlate it with "
            "identity, endpoint, and network telemetry covering the same time window "
            "before escalating or changing the system."
        )
        records.append(
            _record(
                fact,
                suffix=f"log-{index + 1}",
                family="log-interpretation",
                task="log-analysis",
                prompt=prompt,
                response=response,
                extra_metadata={"artifact": "log"},
            )
        )
        if index == 0 and (fact.raw.get("pitfalls") or fact.pitfalls):
            follow_up = (
                "The alert is noisy and the on-call engineer wants to close it as a "
                "false positive. What evidence would justify that decision, and what "
                "would force escalation?"
            )
            records.append(
                _record(
                    fact,
                    suffix="triage-dialogue",
                    family="multi-turn-troubleshooting",
                    task="incident-triage",
                    prompt="",
                    response="",
                    messages=[
                        {
                            "role": "user",
                            "content": (
                                f"This {context} event fired at 02:14 UTC:\n\n```\n{text}\n```\n"
                                "How should I triage it?"
                            ),
                        },
                        {
                            "role": "assistant",
                            "content": (
                                f"{reading}\n\nStart by establishing scope and context: the "
                                "account, host, and source address, whether the activity is "
                                "expected for that asset, and what happened immediately before "
                                "and after. Preserve the raw event with its original timestamp."
                            ),
                        },
                        {"role": "user", "content": follow_up},
                        {
                            "role": "assistant",
                            "content": (
                                "Closing as a false positive requires positive evidence, not "
                                "absence of an obvious payload. Confirm the initiating process, "
                                "user authorization, change record, and matching behaviour on "
                                "peer assets. Escalate if the account or host is unusual, if "
                                "the activity continues after the user stops, if persistence or "
                                "credential access appears, or if the same pattern appears on "
                                "multiple hosts.\n\n"
                                f"{_bullets(fact.pitfalls, limit=3)}"
                            ),
                        },
                    ],
                    extra_metadata={"artifact": "log", "turns": 2},
                )
            )

    for index, command in enumerate(fact.raw.get("commands", [])[:2]):
        language = str(command["language"])
        code = str(command["code"]).strip()
        purpose = str(command["purpose"]).strip()
        prompt = (
            f"Explain what this {language} command does, what could go wrong if it is "
            f"run with the wrong assumptions, and how to verify the result before "
            f"acting on it:\n\n```{language}\n{code}\n```"
        )
        response = (
            f"Purpose: {purpose}\n\n"
            f"{fact.fact}\n\n"
            "Run it first in a non-production or read-only context, capture the output "
            "with timestamps, and compare it with an independent source such as the "
            "service configuration or audit log. Generated commands in this corpus are "
            "examples and are never executed by the project."
        )
        records.append(
            _record(
                fact,
                suffix=f"command-{index + 1}",
                family="command-explanation",
                task="system-administration",
                prompt=prompt,
                response=response,
                extra_metadata={"artifact": "command", "artifact_language": language},
            )
        )

    for index, config in enumerate(fact.raw.get("configs", [])[:2]):
        language = str(config["language"])
        snippet = str(config["snippet"]).strip()
        purpose = str(config["purpose"]).strip()
        if language.lower() in {"http"}:
            continue
        if language.lower() == "json" and "stix" in (purpose + snippet).lower():
            continue
        prompt = (
            f"Review this {language} configuration snippet for a security review:\n\n"
            f"```{language}\n{snippet}\n```\n\n"
            "What security property does it establish, what assumption could make it "
            "unsafe, and what should be verified in the deployed system?"
        )
        hint = _verification_hint(language, "the reviewed directive")
        response = (
            f"Intended property: {purpose}\n\n"
            f"{fact.fact}\n\n"
            f"Check: {hint}; then attempt the action the control is meant to block "
            "and confirm it fails for the intended identity and scope. A syntactically "
            "valid directive can still be overridden by a more specific rule or a later "
            "scope, so compare the rendered/effective configuration, not only the file."
        )
        records.append(
            _record(
                fact,
                suffix=f"config-{index + 1}",
                family="configuration-analysis",
                task="system-hardening",
                prompt=prompt,
                response=response,
                extra_metadata={"artifact": "config", "artifact_language": language},
            )
        )

    for index, code in enumerate(fact.raw.get("code", [])[:2]):
        if not _security_code_issue(str(code.get("issue", ""))):
            continue
        language = str(code["language"])
        vulnerable = str(code["vulnerable"]).strip()
        secure = str(code["secure"]).strip()
        issue = str(code["issue"]).strip()
        prompt = (
            f"Review this {language} code for security defects:\n\n"
            f"```{language}\n{vulnerable}\n```\n\n"
            "Identify the weakness class, the condition required to exploit it, the "
            "impact, and a secure fix. Do not write exploit code."
        )
        response = (
            f"{issue}\n\n"
            f"Exploit condition: {issue}\n\n"
            f"Why it matters: {fact.fact}\n\n"
            f"Secure version:\n\n```{language}\n{secure}\n```\n\n"
            "Regression test: exercise the abuse case and a legitimate case against the "
            "patched revision. Review the diff for the root cause, not only for the "
            "specific input that triggered the report."
        )
        records.append(
            _record(
                fact,
                suffix=f"codereview-{index + 1}",
                family="secure-code-review",
                task="secure-coding",
                prompt=prompt,
                response=response,
                extra_metadata={"artifact": "code", "artifact_language": language},
            )
        )
        records.append(
            _record(
                fact,
                suffix=f"codefix-{index + 1}",
                family="code-remediation",
                task="secure-coding",
                prompt=(
                    f"The following {language} function was reported as vulnerable. "
                    "Explain the root cause and provide a corrected version.\n\n"
                    f"```{language}\n{vulnerable}\n```"
                ),
                response=(
                    f"Root cause: {issue}\n\n"
                    f"Corrected version:\n\n```{language}\n{secure}\n```\n\n"
                    f"{fact.fact}\n\n"
                    "Add a regression test for the abuse case before merging the fix."
                ),
                extra_metadata={"artifact": "code", "artifact_language": language},
            )
        )
        # Fill-in-the-middle is emitted only when the secure sample has a clean
        # line boundary and is small enough to avoid splitting a multi-line
        # string or a block that would make the completion ambiguous.
        fim = _fim_from_code(fact, secure, language, index)
        if fim is not None:
            records.append(fim)

    if (
        fact.raw.get("details")
        and len(fact.details) >= 2
        and int(_digest(f"{fact.id}:json")[:8], 16) % 10 < 3
    ):
        records.append(
            _record(
                fact,
                suffix="checklist",
                family="structured-json",
                task="security-knowledge",
                prompt=(
                    "Return a JSON object summarizing this guidance for a runbook. "
                    "Use exactly the keys `principle`, `checks`, and `failure_modes`. "
                    "`checks` and `failure_modes` must be arrays of short strings.\n\n"
                    f"Guidance: {fact.fact}"
                ),
                response=json.dumps(
                    {
                        "principle": fact.fact.split(". ")[0][:400],
                        "checks": [item.split(". ")[0][:200] for item in fact.details[:5]],
                        "failure_modes": [item.split(". ")[0][:200] for item in fact.pitfalls[:4]],
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                extra_metadata={"structured_output": "json"},
            )
        )

    return records, preferences


def _config_completion(fact: Fact) -> Record | None:
    configs = fact.raw.get("configs", [])
    if not configs:
        return None
    config = configs[0]
    language = str(config["language"])
    if language.lower() not in {
        "sshd_config",
        "nginx",
        "nftables",
        "kubernetes",
        "yaml",
        "ini",
        "toml",
        "json",
    }:
        return None
    snippet = str(config["snippet"]).strip()
    lines = snippet.splitlines()
    candidates: list[tuple[int, str, str, str]] = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "//", ";")):
            continue
        match = re.match(r"^(\s*)([A-Za-z_][\w.-]*)(\s*[:=]\s*|\s+)(\S.*)$", line)
        if match is None:
            continue
        value = match.group(4).strip()
        if not value or value in {"{", "[", "}", "]"}:
            continue
        candidates.append((index, match.group(2), match.group(3), value))
    if not candidates:
        return None
    purpose_text = str(config["purpose"]).lower()
    preferred = [
        candidate
        for candidate in candidates
        if candidate[1].lower().replace("_", " ") in purpose_text
        or candidate[1].lower() in purpose_text
    ]
    pool = preferred or candidates
    index, key, separator, value = pool[int(_digest(f"{fact.id}:completion")[:8], 16) % len(pool)]
    blanked = list(lines)
    blanked[index] = re.sub(r"(\S.*)$", "___", lines[index], count=1)
    prompt = (
        f"Complete the blanked directive in this {language} configuration so that it "
        f"achieves the stated purpose: {str(config['purpose']).strip()}\n\n"
        f"```{language}\n" + "\n".join(blanked) + "\n```\n\n"
        "Give the completed line and one reason the value matters."
    )
    completed = f"{key}{separator}{value}"
    response = (
        f"Completed line:\n\n```{language}\n{completed}\n```\n\n"
        f"Why this line: it sets `{key}` to `{value}`, which is the condition needed for "
        f"the stated purpose ({str(config['purpose']).strip()}).\n\n"
        f"{fact.fact}\n\n"
        f"Check: {_verification_hint(language, key)}. If the purpose can be met by a "
        "different value, the configuration is ambiguous and should be narrowed before use."
    )
    return _record(
        fact,
        suffix="config-complete",
        family="configuration-completion",
        task="system-hardening",
        prompt=prompt,
        response=response,
        extra_metadata={
            "artifact": "config",
            "artifact_language": language,
            "completion_line": completed,
        },
    )


def _fim_from_code(fact: Fact, secure: str, language: str, index: int) -> Record | None:
    lines = secure.splitlines()
    if len(lines) < 4 or len(secure) > 1800:
        return None
    security_terms = re.compile(
        r"auth|token|secret|key|nonce|iv|cipher|encrypt|decrypt|sanitize|escape|"
        r"validate|verify|permission|owner|query|execute|exec|open|path|hash|salt",
        re.IGNORECASE,
    )
    candidates = [
        position
        for position, line in enumerate(lines)
        if line.strip()
        and not line.strip().startswith(("import ", "from ", "#"))
        and len(line) <= 160
        and security_terms.search(line)
    ]
    if len(candidates) < 1:
        return None
    if len(candidates) < 2:
        return None
    position = candidates[int(_digest(f"{fact.id}:fim:{index}")[:8], 16) % len(candidates)]
    prefix = "\n".join(lines[:position]) + "\n"
    middle = lines[position]
    suffix = "\n" + "\n".join(lines[position + 1 :])
    if not middle.strip():
        return None
    return _record(
        fact,
        suffix=f"fim-{index + 1}",
        family="fill-in-the-middle",
        task="secure-autocomplete",
        prompt=middle,
        response=suffix,
        prefix=prefix,
        kind="fim",
        extra_metadata={
            "artifact": "code",
            "artifact_language": language,
            "completion_line": middle,
        },
    )


def generate_comparisons(packs: list[KnowledgePack], *, limit_per_domain: int = 8) -> list[Record]:
    """Create a small number of cross-fact comparison questions per domain."""

    records: list[Record] = []
    for pack in packs:
        facts = sorted(pack.facts, key=lambda item: item.id)
        pairs: list[tuple[Fact, Fact]] = []
        for first_index in range(0, len(facts) - 1, 2):
            first = facts[first_index]
            second = facts[first_index + 1]
            shared_tags = set(first.raw.get("tags", [])) & set(second.raw.get("tags", []))
            same_family = first.subtopic.split("-")[0] == second.subtopic.split("-")[0]
            if first.subtopic == second.subtopic or not (len(shared_tags) >= 3 or same_family):
                continue
            pairs.append((first, second))
            if len(pairs) >= limit_per_domain:
                break
        for first, second in pairs:
            suffix = f"compare-{second.id}"
            response = (
                f"{first.title}: {first.fact}\n\n"
                f"{second.title}: {second.fact}\n\n"
                f"They are not interchangeable. The first concerns "
                f"{first.subtopic.replace('-', ' ')}, while the second concerns "
                f"{second.subtopic.replace('-', ' ')}. Choose the control that matches "
                "the asset, threat model, and evidence you actually have, and state the "
                "assumption that would change the decision."
            )
            records.append(
                _record(
                    first,
                    suffix=suffix,
                    family="comparison",
                    task="security-knowledge",
                    prompt=(
                        f'Compare these two controls: "{first.title}" and '
                        f'"{second.title}". What problem does each address, when should '
                        "an engineer choose one, and what mistake conflates them?"
                    ),
                    response=response,
                    extra_metadata={"compared_fact": second.id},
                )
            )
    return records


def synthesize(
    pack_dir: str | Path,
    *,
    include_globs: tuple[str, ...] = ("c[1-8]-*.json",),
) -> SynthesisResult:
    directory = Path(pack_dir)
    paths: list[Path] = []
    for pattern in include_globs:
        paths.extend(sorted(directory.glob(pattern)))
    if not paths:
        raise FileNotFoundError(f"no knowledge packs matched {include_globs} in {directory}")

    packs: list[KnowledgePack] = []
    seen_ids: dict[str, str] = {}
    for path in paths:
        pack = load_pack(path)
        for fact in pack.facts:
            if fact.id in seen_ids:
                raise PackValidationError(
                    f"duplicate fact id {fact.id!r} in {path} and {seen_ids[fact.id]}"
                )
            seen_ids[fact.id] = str(path)
        packs.append(pack)

    records: list[Record] = []
    preferences: list[dict[str, Any]] = []
    task_counts: dict[str, int] = {}
    domain_counts: dict[str, int] = {}
    difficulty_counts: dict[str, int] = {}
    have_artifacts = 0
    for pack in packs:
        for fact in pack.facts:
            fact_records, fact_preferences = generate_fact_records(fact)
            records.extend(fact_records)
            preferences.extend(fact_preferences)
            if fact_records:
                have_artifacts += int(
                    any(key in fact.raw for key in ("commands", "configs", "code", "logs"))
                )
            for record in fact_records:
                task_counts[record.task] = task_counts.get(record.task, 0) + 1
                domain_counts[pack.domain] = domain_counts.get(pack.domain, 0) + 1
                difficulty_counts[fact.difficulty] = difficulty_counts.get(fact.difficulty, 0) + 1

    stats = {
        "packs": len(packs),
        "facts": sum(len(pack.facts) for pack in packs),
        "facts_with_artifacts": have_artifacts,
        "records": len(records),
        "preference_pairs": len(preferences),
        "task_counts": dict(sorted(task_counts.items())),
        "domain_counts": dict(sorted(domain_counts.items())),
        "difficulty_counts": dict(sorted(difficulty_counts.items())),
        "pack_hashes": {pack.domain: pack.sha256 for pack in packs},
    }
    return SynthesisResult(
        records=records,
        preferences=preferences,
        packs=packs,
        stats=stats,
    )

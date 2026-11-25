"""Detection-rule interpretation records from a small authored Sigma library.

The library is a teaching aid, not a production rule pack. Records explain the
rule's intent, required telemetry, false positives, and tuning trade-offs; they
do not claim that a rule is complete or validated in a specific SIEM.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from cyberlite.data.schema import Record

DEFAULT_LIBRARY = Path("data/synthesis/seeds/detection_rules.json")


@dataclass
class DetectionRule:
    id: str
    title: str
    purpose: str
    logsource: str
    level: str
    yaml_text: str
    falsepositives: list[str]
    tuning: str
    tags: list[str]
    references: list[str]


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_detection_rules(path: str | Path = DEFAULT_LIBRARY) -> list[DetectionRule]:
    file_path = Path(path)
    payload = json.loads(file_path.read_text(encoding="utf-8"))
    rules: list[DetectionRule] = []
    seen: set[str] = set()
    for raw in payload.get("rules", []):
        if not isinstance(raw, dict):
            raise ValueError(f"{file_path}: rule must be an object")
        rule_id = str(raw.get("id", ""))
        if not re.fullmatch(r"det-[a-z0-9-]{2,60}", rule_id):
            raise ValueError(f"{file_path}: invalid rule id {rule_id!r}")
        if rule_id in seen:
            raise ValueError(f"{file_path}: duplicate rule id {rule_id!r}")
        seen.add(rule_id)
        for key in ("title", "purpose", "logsource", "level", "yaml", "tuning"):
            if not str(raw.get(key, "")).strip():
                raise ValueError(f"{file_path}: {rule_id} missing {key}")
        parsed = yaml.safe_load(str(raw["yaml"]))
        if not isinstance(parsed, dict) or "detection" not in parsed:
            raise ValueError(f"{file_path}: {rule_id} YAML is not a Sigma-like detection rule")
        rules.append(
            DetectionRule(
                id=rule_id,
                title=str(raw["title"]),
                purpose=str(raw["purpose"]),
                logsource=str(raw["logsource"]),
                level=str(raw["level"]),
                yaml_text=str(raw["yaml"]).strip(),
                falsepositives=[str(item) for item in raw.get("falsepositives", [])],
                tuning=str(raw["tuning"]),
                tags=[str(item) for item in raw.get("tags", [])],
                references=[str(item) for item in raw.get("references", [])],
            )
        )
    if not rules:
        raise ValueError(f"{file_path}: no rules")
    return rules


def _record(
    rule: DetectionRule,
    *,
    suffix: str,
    family: str,
    prompt: str,
    response: str,
    difficulty: str,
    extra: dict[str, Any] | None = None,
) -> Record:
    metadata: dict[str, Any] = {
        "group": f"detection_rule:{rule.id}",
        "domain": "monitoring-detection-soc",
        "subtopic": "detection-rule-interpretation",
        "difficulty": difficulty,
        "task_family": family,
        "source_version": "detection-library-v1",
        "source_title": "CyberLite authored detection-rule teaching library",
        "source_url": rule.references[0] if rule.references else "",
        "license_url": "https://github.com/braydos-h/CyberLite/blob/main/LICENSE",
        "upstream_id": rule.id,
        "synthetic": True,
        "origin": "curated-synthetic",
        "generation_method": "detection-rule-composition",
        "authoring_agent": "worker:orchestrator",
        "references": [
            {"title": rule.title, "publisher": "CyberLite", "url": url, "license": "Synthetic"}
            for url in rule.references
        ],
        "review_status": "automated-screened",
        "human_reviewed": False,
        "rule_level": rule.level,
        "rule_tags": rule.tags,
        "logsource": rule.logsource,
    }
    if extra:
        metadata.update(extra)
    return Record(
        id=f"det-{rule.id}-{suffix}",
        source="cyberlite_synthesis",
        license="Synthetic",
        task="detection-engineering",
        prompt=prompt.strip(),
        response=response.strip(),
        url=rule.references[0] if rule.references else "",
        metadata=metadata,
    )


def generate_detection_records(
    rules: list[DetectionRule] | None = None,
) -> list[Record]:
    rules = rules or load_detection_rules()
    records: list[Record] = []
    for rule in rules:
        prompt = (
            "Interpret this Sigma-style detection rule for a SOC engineer. Explain what it "
            "detects, which telemetry it requires, one false positive, and what it does not "
            "prove.\n\n"
            f"```yaml\n{rule.yaml_text}\n```"
        )
        windowed = "timeframe:" in rule.yaml_text or "| count(" in rule.yaml_text
        response = (
            f"Intent: {rule.purpose}\n\n"
            f"Telemetry: {rule.logsource}. The rule level is {rule.level}; level is a "
            "triage hint, not a measure of confidence. "
            + (
                "The condition aggregates over the stated time window, so missing or delayed "
                "ingestion changes the result.\n\n"
                if windowed
                else "This is a per-event match with no aggregation window; each event is "
                "evaluated on its own fields.\n\n"
            )
            + "False positives to expect:\n"
            + "\n".join(f"- {item}" for item in rule.falsepositives[:4])
            + "\n\nWhat it does not prove: a match is an observation about the named fields, "
            "not proof of malicious intent or successful compromise. Correlate with identity, "
            "asset criticality, and adjacent events before escalating. Confirm that the SIEM "
            "field mapping matches the rule's field names; a rule that parses but never matches "
            "is worse than a noisy one because it looks healthy."
        )
        records.append(
            _record(
                rule,
                suffix="interpret",
                family="detection-rule-interpretation",
                prompt=prompt,
                response=response,
                difficulty="intermediate",
            )
        )
        tuning_prompt = (
            "The rule below is producing false positives. Explain how to tune it without "
            "creating a blind spot, and name the metric you would watch after the change.\n\n"
            f"```yaml\n{rule.yaml_text}\n```"
        )
        tuning_response = (
            f"Current guidance: {rule.tuning}\n\n"
            "Tune by narrowing the entity, time window, or field relationship, not by "
            "suppressing the rule globally. For each proposed exclusion, state what malicious "
            "behaviour would also be excluded. Keep a canary or lower-severity variant so the "
            "suppressed path remains observable, and record the change with an owner and review "
            "date. After deployment, watch the match rate, the true-positive ratio from "
            "sampled alerts, and the ingestion latency for the required log source."
        )
        records.append(
            _record(
                rule,
                suffix="tuning",
                family="detection-rule-interpretation",
                prompt=tuning_prompt,
                response=tuning_response,
                difficulty="advanced",
            )
        )
    return records

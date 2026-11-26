"""Source-grounded task generation from the licensed pilot corpus.

These records are *derived* from a frozen source record. The source, license,
group, URL, and upstream identifier are preserved; the task view is new. The
generator is deliberately conservative:

* it consumes only training-split records from the frozen pilot, never
  validation, test, or evaluation files;
* answers are composed from metadata and evidence that the source record
  already contains, and say so when the evidence is insufficient;
* extractive answers are labelled, so a reviewer can distinguish them from
  authored explanations;
* every derived record stays in the same leakage group as its parent.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

from cyberlite.data.schema import Record

GROUNDING_VERSION = "grounded-v1"
MAX_EVIDENCE_CHARS = 1600
MAX_RESPONSE_CHARS = 3200
MAX_CLAIM_CHARS = 320
_NORMATIVE = ("MUST NOT", "MUST", "SHOULD NOT", "SHOULD", "REQUIRED", "RECOMMENDED", "SHALL", "MAY")
_NUMBER_RE = re.compile(r"(?<![\w.-])(\d{1,5})(?![\w.-])")
_URL_RE = re.compile(r"https?://\S+")
_ATTACK_ID_RE = re.compile(r"\bT\d{4}(?:\.\d{3})?\b")
_CWE_ID_RE = re.compile(r"\bCWE-\d{1,5}\b")
_CVE_ID_RE = re.compile(r"\bCVE-\d{4}-\d{4,}\b")
_SPACE_RE = re.compile(r"\s+")

CVSS_V3_METRICS: dict[str, dict[str, str]] = {
    "AV": {"N": "network", "A": "adjacent network", "L": "local", "P": "physical"},
    "AC": {"L": "low", "H": "high"},
    "PR": {"N": "none", "L": "low", "H": "high"},
    "UI": {"N": "none", "R": "required"},
    "S": {"U": "unchanged", "C": "changed"},
    "C": {"H": "high", "L": "low", "N": "none"},
    "I": {"H": "high", "L": "low", "N": "none"},
    "A": {"H": "high", "L": "low", "N": "none"},
}

CWE_ROOT_CAUSE: dict[str, str] = {
    "CWE-20": "insufficient validation of untrusted input",
    "CWE-22": "untrusted path components reaching filesystem operations",
    "CWE-78": "untrusted input reaching an operating-system command shell",
    "CWE-79": "untrusted input reaching an HTML/script output context without context-aware encoding",
    "CWE-89": "untrusted input concatenated into SQL instead of bound as a parameter",
    "CWE-94": "untrusted input evaluated as code",
    "CWE-125": "a read past the end of a buffer",
    "CWE-190": "an arithmetic result that exceeds the destination type",
    "CWE-287": "an authentication decision that can be bypassed or is incomplete",
    "CWE-306": "a sensitive function reachable without authentication",
    "CWE-319": "sensitive data transmitted without transport protection",
    "CWE-327": "a broken or risky cryptographic primitive or mode",
    "CWE-330": "predictable or insufficiently random values used in a security decision",
    "CWE-352": "a state-changing request that lacks a trustworthy CSRF defense",
    "CWE-400": "uncontrolled consumption of a finite resource",
    "CWE-434": "an uploaded file that can be executed or served as active content",
    "CWE-502": "untrusted serialized data deserialized into objects",
    "CWE-611": "an XML parser resolving external entities",
    "CWE-732": "a permission assigned more broadly than the task requires",
    "CWE-770": "allocation of a resource without a limit or throttling",
    "CWE-798": "hard-coded credentials embedded in code or configuration",
    "CWE-862": "a sensitive operation that lacks an authorization check",
    "CWE-863": "an authorization check that uses the wrong subject or scope",
    "CWE-918": "a user-controlled URL fetched by the server without destination restrictions",
    "CWE-1321": "recursive merging of untrusted object properties into a prototype",
}


@dataclass
class GroundedResult:
    records: list[Record]
    stats: dict[str, Any] = field(default_factory=dict)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _clean(text: str) -> str:
    return _SPACE_RE.sub(" ", text.replace("\u00a0", " ")).strip()


def _clip(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    boundary = max(cut.rfind(". "), cut.rfind("\n"), cut.rfind("; "))
    if boundary >= limit // 2:
        return cut[: boundary + 1].rstrip() + " …"
    return cut.rstrip() + " …"


def _strip_markdown(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    # Drop heading lines entirely. Keeping their text merges a section title
    # into the first sentence of the body and produces misleading options.
    text = re.sub(r"^#{1,6}\s*.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*|__", "", text)
    # Treat bullet separators as sentence boundaries so a long list is not
    # presented as one "statement" in an evidence-comprehension question.
    text = re.sub(r"\s*[•]\s*", ". ", text)
    text = re.sub(r"\s+-\s+", ". ", text)
    text = re.sub(r"\bNotes:\s*", "", text)
    return _clean(text)


def _sentences(text: str) -> list[str]:
    cleaned = _strip_markdown(text)
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9(])", cleaned)
    return [_clean(part) for part in parts if _clean(part)]


def _claim_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    for sentence in _sentences(text):
        if not 50 <= len(sentence) <= MAX_CLAIM_CHARS:
            continue
        if _URL_RE.search(sentence) or "@" in sentence:
            continue
        upper = sentence.upper()
        has_normative = any(keyword in upper for keyword in _NORMATIVE)
        has_number = bool(_NUMBER_RE.search(sentence))
        if not (has_normative or has_number):
            continue
        if len(re.findall(r"\b(?:MUST|SHOULD|SHALL|MAY|REQUIRED|RECOMMENDED)\b", upper)) > 3:
            continue
        if sentence.lower().startswith(("the key words", "notes", "for example,")):
            continue
        if sentence.count("(") != sentence.count(")"):
            continue
        candidates.append(sentence)
    # Deduplicate while preserving evidence order.
    seen: set[str] = set()
    unique: list[str] = []
    for sentence in candidates:
        key = _digest(sentence)[:16]
        if key in seen:
            continue
        seen.add(key)
        unique.append(sentence)
    return unique


def _swap_normative(sentence: str) -> tuple[str, str] | None:
    upper = sentence.upper()
    for source, target in (
        ("MUST NOT", "SHOULD NOT"),
        ("SHOULD NOT", "MUST NOT"),
        ("MUST", "SHOULD"),
        ("SHOULD", "MUST"),
        ("REQUIRED", "RECOMMENDED"),
        ("RECOMMENDED", "REQUIRED"),
        ("SHALL", "MAY"),
        ("MAY", "SHALL"),
    ):
        if source in upper:
            index = upper.find(source)
            return sentence[:index] + target + sentence[index + len(source) :], (
                f'changes "{source}" to "{target}"'
            )
    return None


def _swap_number(sentence: str) -> tuple[str, str] | None:
    match = _NUMBER_RE.search(sentence)
    if match is None:
        return None
    value = int(match.group(1))
    if value == 0:
        replacement = "1"
    elif value < 10:
        replacement = str(value + 1)
    else:
        replacement = str(value * 2)
    return (
        sentence[: match.start(1)] + replacement + sentence[match.end(1) :],
        f"changes the value {value} to {replacement}",
    )


def _drop_negation(sentence: str) -> tuple[str, str] | None:
    match = re.search(
        r"\b(?:does not|do not|is not|are not|must not|should not|cannot|can not)\b", sentence, re.I
    )
    if match is None:
        return None
    replacement = {
        "does not": "does",
        "do not": "do",
        "is not": "is",
        "are not": "are",
        "must not": "must",
        "should not": "should",
        "cannot": "can",
        "can not": "can",
    }[match.group(0).lower()]
    return (
        sentence[: match.start()] + replacement + sentence[match.end() :],
        "removes a negation",
    )


def _evidence_requirement(
    record: Record, *, index: int = 0
) -> tuple[Record, dict[str, Any]] | None:
    """Ask whether a deployment behaviour is supported by a normative sentence.

    The option-proofreading format was rejected in review: it rewarded matching a
    verbatim sentence. This variant weakens the modal in the source sentence and
    asks the model to decide whether the weaker behaviour is still supported.
    """

    if record.source != "ietf_rfcs":
        return None
    evidence = _clip(_strip_markdown(record.response or ""), 900)
    candidates = [sentence for sentence in _claim_candidates(evidence) if sentence in evidence]
    normative = [
        sentence
        for sentence in candidates
        if re.search(
            r"\b(?:MUST NOT|MUST|SHOULD NOT|SHOULD|REQUIRED|RECOMMENDED|SHALL)\b", sentence.upper()
        )
    ]
    if len(normative) <= index:
        return None
    requirement = normative[index]
    upper = requirement.upper()
    if "MUST NOT" in upper:
        strength = "prohibited (MUST NOT)"
        behaviour = re.sub(r"MUST NOT", "MAY", requirement, count=1)
    elif "SHOULD NOT" in upper:
        strength = "discouraged (SHOULD NOT), not an absolute prohibition"
        behaviour = re.sub(r"SHOULD NOT", "MAY", requirement, count=1)
    elif "MUST" in upper:
        strength = "required (MUST)"
        behaviour = re.sub(r"MUST", "MAY", requirement, count=1)
    elif "SHOULD" in upper:
        strength = "recommended (SHOULD), not mandatory"
        behaviour = re.sub(r"SHOULD", "MAY", requirement, count=1)
    elif "REQUIRED" in upper:
        strength = "required (REQUIRED)"
        behaviour = requirement.replace("REQUIRED", "OPTIONAL", 1)
    else:
        strength = "normative"
        behaviour = requirement.replace("SHALL", "MAY", 1)
    prompt = (
        "Use only the excerpt below. A deployment plan states the following behaviour. "
        "Is that behaviour supported by the excerpt? Quote the relevant requirement, "
        "explain the difference in normative strength, and state one operational "
        "consequence of treating it as optional.\n\n"
        f'Excerpt:\n"""\n{evidence}\n"""\n\n'
        f"Proposed behaviour: {behaviour}"
    )
    response = (
        f'No. The excerpt makes this {strength}: "{requirement}" The proposed '
        "behaviour weakens or reverses that requirement. Treating a MUST as optional "
        "changes interoperability or security assumptions; treating a SHOULD as optional "
        "may be defensible only with a documented reason and compensating control. "
        "Confirm the exact normative keyword in the current version of the source before "
        "making the decision, and record the deployment exception if one is taken."
    )
    metadata = _metadata(record, "evidence-grounded-qa", "normative-requirement-application")
    metadata.update(
        {
            "evidence_chars": len(evidence),
            "normative_strength": strength,
            "requirement": requirement,
        }
    )
    return (
        _derive(
            record,
            suffix=f"requirement-{index + 1}",
            task="grounded-reasoning",
            prompt=prompt,
            response=response,
            metadata=metadata,
        ),
        {"strength": strength},
    )


def _difficulty(record: Record, variant: str) -> str:
    """A transparent difficulty proxy for derived task views."""

    source = record.source
    digest = _digest(f"{record.id}:{variant}")
    bucket = int(digest[:8], 16) % 100
    if variant == "normative-requirement-application":
        if source in {"ietf_rfcs", "linux_man_pages", "openssh_docs", "netfilter_nftables"}:
            return "advanced" if bucket < 25 else "intermediate"
        return "foundational" if bucket < 35 else "intermediate"
    if variant in {"nvd-insufficient-evidence", "nvd-extraction"}:
        return "foundational"
    if variant == "nvd-triage":
        return "intermediate"
    if variant == "nvd-cwe-explanation":
        return "intermediate"
    if variant == "nvd-cvss-counterfactual":
        return "advanced"
    if variant == "nvd-cpe-applicability":
        return "intermediate"
    if variant == "attack-detection":
        return "advanced"
    if variant == "attack-matching":
        return "intermediate"
    if variant == "cwe-mitigation":
        return "advanced"
    if variant == "cwe-review-questions":
        return "advanced"
    if variant == "cwe-matching":
        return "intermediate"
    return "intermediate"


SOURCE_DOMAIN = {
    "nist_nvd": "vulnerability-classification-remediation",
    "mitre_cwe": "vulnerability-classification-remediation",
    "mitre_attack": "incident-response-forensics-threat-intel",
    "owasp_cheatsheets": "web-api-secure-development",
    "ietf_rfcs": "fundamentals-linux-networking",
    "linux_man_pages": "fundamentals-linux-networking",
    "openssh_docs": "fundamentals-linux-networking",
    "netfilter_nftables": "fundamentals-linux-networking",
    "project_examples": "incident-response-forensics-threat-intel",
}


def _metadata(record: Record, family: str, variant: str) -> dict[str, Any]:
    metadata = dict(record.metadata or {})
    if not metadata.get("domain"):
        metadata["domain"] = SOURCE_DOMAIN.get(record.source, record.source)
    metadata.setdefault("difficulty", _difficulty(record, variant))
    metadata.update(
        {
            "task_family": family,
            "variant": variant,
            "derivation_parent_id": record.id,
            "derivation_version": GROUNDING_VERSION,
            "origin": "source-derived",
            "synthetic": False,
            "generation_method": "grounded-evidence-composition",
            "review_status": "automated-screened",
            "human_reviewed": False,
            "synthetic_identifiers": True,
        }
    )
    return metadata


def _derive(
    record: Record,
    *,
    suffix: str,
    task: str,
    prompt: str,
    response: str,
    metadata: dict[str, Any],
) -> Record:
    identifier = re.sub(r"[^a-z0-9-]", "-", f"grnd-{record.source}-{record.id}-{suffix}".lower())
    prompt = prompt.strip()
    response = response.strip()
    if len(response) > MAX_RESPONSE_CHARS:
        response = response[:MAX_RESPONSE_CHARS].rsplit("\n", 1)[0]
    return Record(
        id=identifier[:140],
        source=record.source,
        license=record.license,
        task=task,
        prompt=prompt,
        response=response,
        url=record.url,
        metadata=metadata,
    )


def _cvss_entries(record: Record) -> list[dict[str, Any]]:
    entries = (record.metadata or {}).get("cvss", [])
    return [entry for entry in entries if isinstance(entry, dict) and entry.get("vector")]


def _cvss_v3(record: Record) -> dict[str, Any] | None:
    for entry in _cvss_entries(record):
        vector = str(entry.get("vector", ""))
        if vector.startswith("CVSS:3."):
            metrics: dict[str, str] = {}
            for part in vector.split("/")[1:]:
                if ":" not in part:
                    continue
                key, value = part.split(":", 1)
                if key in CVSS_V3_METRICS and value in CVSS_V3_METRICS[key]:
                    metrics[key] = CVSS_V3_METRICS[key][value]
            if len(metrics) == 8:
                return {
                    "vector": vector,
                    "score": entry.get("score"),
                    "severity": entry.get("severity"),
                    "metrics": metrics,
                    "metric_codes": {
                        part.split(":", 1)[0]: part.split(":", 1)[1]
                        for part in vector.split("/")[1:]
                        if ":" in part
                    },
                }
    return None


def _nvd_triage(record: Record) -> Record | None:
    metadata = record.metadata or {}
    cve_id = str(metadata.get("cve_id") or "")
    if not cve_id:
        return None
    cvss = _cvss_v3(record)
    weaknesses = [str(item) for item in metadata.get("weaknesses", [])][:4]
    cpes = [str(item) for item in metadata.get("cpe_configurations", [])][:3]
    description = _clip(_strip_markdown(record.response or ""), 700)
    evidence = {
        "cve_id": cve_id,
        "description": description,
        "weaknesses": weaknesses,
        "cpe": cpes,
        "cvss": (
            {
                "version": "3.x",
                "vector": cvss["vector"],
                "base_score": cvss["score"],
                "severity": cvss["severity"],
            }
            if cvss
            else metadata.get("cvss", [])[:1]
        ),
        "vuln_status": metadata.get("vuln_status"),
    }
    prompt = (
        "A vulnerability scanner flags this NVD record on an internet-facing service. "
        "Using only the record, explain what it establishes and what must be verified "
        "before the finding is prioritized.\n\n" + json.dumps(evidence, indent=2)
    )
    lines = [
        f"The record describes {cve_id}. It establishes the published description, "
        "the NVD weakness mapping, and any CVSS assessment present; it does not "
        "establish that a particular host is affected.",
    ]
    if cvss:
        metrics = cvss["metrics"]
        lines.append(
            f"The CVSS v3 vector {cvss['vector']} scores {cvss['score']} "
            f"({cvss['severity']}). Attack vector is {metrics['AV']}, attack complexity "
            f"is {metrics['AC']}, privileges required are {metrics['PR']}, and user "
            f"interaction is {metrics['UI']}. Scope is {metrics['S']}; confidentiality, "
            f"integrity, and availability impact are {metrics['C']}, {metrics['I']}, and "
            f"{metrics['A']} respectively."
        )
        if metrics["AV"] == "network" and metrics["PR"] == "none" and metrics["UI"] == "none":
            lines.append(
                "That combination describes a remotely reachable issue with no prerequisite "
                "credentials or user action, so exposure and patch availability drive urgency."
            )
    if weaknesses:
        lines.append("NVD maps the issue to " + ", ".join(weaknesses) + ".")
    if cpes:
        lines.append(
            "Applicability is expressed through CPE configurations such as "
            + ", ".join(f"`{item}`" for item in cpes)
            + "; compare those product and version constraints with the asset inventory."
        )
    lines.append(
        "Before prioritizing, verify the installed product and version against the CPE "
        "range, whether the vulnerable component is reachable, whether exploitation is "
        "observed (for example KEV or telemetry), and what compensating controls exist. "
        "CVSS base score alone is not a risk decision, and an NVD description is not a "
        "vendor confirmation for your build."
    )
    metadata = _metadata(record, "vulnerability-classification", "nvd-triage")
    metadata.update({"cve_id": cve_id, "license_status": "public-domain-source"})
    return _derive(
        record,
        suffix="triage",
        task="vulnerability",
        prompt=prompt,
        response="\n\n".join(lines),
        metadata=metadata,
    )


def _nvd_metric_counterfactual(record: Record) -> Record | None:
    cvss = _cvss_v3(record)
    metadata = record.metadata or {}
    cve_id = str(metadata.get("cve_id") or "")
    if cvss is None or not cve_id:
        return None
    metrics = cvss["metrics"]
    focus = "availability"
    reasoning = ""
    if metrics["AV"] != "network":
        focus = "attack vector"
        reasoning = (
            f"The vector is {metrics['AV']}, not network. If the vulnerable service were "
            "exposed to an untrusted network, the same base metrics would describe a much "
            "broader population of reachable targets."
        )
    elif metrics["PR"] != "none":
        focus = "privileges required"
        reasoning = (
            f"The vector requires {metrics['PR']} privileges. Losing that prerequisite "
            "(for example through credential theft or a confused-deputy path) would change "
            "the exposure materially, even though the base score would not change."
        )
    elif metrics["UI"] != "none":
        focus = "user interaction"
        reasoning = (
            f"The vector requires user interaction ({metrics['UI']}). Removing that "
            "requirement, for example through a service that processes the input "
            "automatically, would widen the attack surface."
        )
    elif metrics["S"] == "changed":
        focus = "scope"
        reasoning = (
            "Scope is changed, so impact can cross a security boundary. Confirm which "
            "component is the vulnerable one and which component is affected; remediation "
            "may need to happen in both."
        )
    else:
        focus = "impact"
        reasoning = (
            f"Confidentiality, integrity, and availability impacts are {metrics['C']}, "
            f"{metrics['I']}, and {metrics['A']}. A high impact metric raises urgency only "
            "if the affected data or function matters to this asset; that is an environmental "
            "judgement, not a property of the base score."
        )
    prompt = (
        f"The NVD record for {cve_id} carries the CVSS v3 vector {cvss['vector']}. "
        "Which metric most affects how this score should be interpreted for a specific "
        "environment, and what evidence would change the priority? Do not invent a new score."
    )
    response = (
        f"The vector scores {cvss['score']} ({cvss['severity']}). The metric to examine "
        f"first is {focus}. {reasoning}\n\n"
        "CVSS base metrics describe the vulnerability, not your exposure. Environmental "
        "evidence that can change priority includes whether the component is reachable, "
        "whether the required privileges or user action are realistic for this deployment, "
        "the value of the affected data, existing compensating controls, and whether "
        "exploitation is observed in the wild. Do not recalculate a base score by hand; use "
        "a maintained CVSS calculator and record the environmental metrics you changed."
    )
    out = _metadata(record, "vulnerability-classification", "nvd-cvss-counterfactual")
    out.update({"cve_id": cve_id, "cvss_vector": cvss["vector"], "focus_metric": focus})
    return _derive(
        record,
        suffix="cvss",
        task="vulnerability",
        prompt=prompt,
        response=response,
        metadata=out,
    )


def _nvd_cwe_mapping(record: Record, cwe_names: dict[str, str]) -> Record | None:
    metadata = record.metadata or {}
    weaknesses = [str(item) for item in metadata.get("weaknesses", [])]
    if not weaknesses:
        return None
    cve_id = str(metadata.get("cve_id") or "")
    description = _clip(_strip_markdown(record.response or ""), 600)
    options = []
    for cwe in weaknesses:
        name = cwe_names.get(cwe, "a related weakness class")
        options.append(f"{cwe} — {name}")
    prompt = (
        "An NVD record maps a vulnerability to one or more CWE identifiers. Explain what "
        "the mapping implies for root-cause review, and why the mapping alone is not a "
        "complete diagnosis.\n\n"
        f"CVE: {cve_id}\nDescription: {description}\nMapped weaknesses: " + ", ".join(weaknesses)
    )
    parts = [
        f"NVD maps this record to {', '.join(weaknesses)}.",
    ]
    for cwe in weaknesses:
        name = cwe_names.get(cwe, "")
        root_cause = CWE_ROOT_CAUSE.get(cwe)
        if name and root_cause:
            parts.append(f"- {cwe} ({name}) points to {root_cause}.")
        elif name:
            parts.append(f"- {cwe} ({name}) is the recorded weakness class.")
    parts.append(
        "Use the mapping to choose code-review questions, not to close the investigation. "
        "NVD mappings can be incomplete, disputed, or assigned to a consequence rather than "
        "the root cause. Confirm the affected code path, reproduce the condition in a lab, "
        "and check whether the vendor advisory names additional weaknesses."
    )
    metadata = _metadata(record, "vulnerability-classification", "nvd-cwe-explanation")
    metadata.update({"cve_id": cve_id, "weaknesses": weaknesses})
    return _derive(
        record,
        suffix="cwe",
        task="vulnerability",
        prompt=prompt,
        response="\n\n".join(parts),
        metadata=metadata,
    )


def _nvd_applicability(record: Record) -> Record | None:
    metadata = record.metadata or {}
    cve_id = str(metadata.get("cve_id") or "")
    cpes = [str(item) for item in metadata.get("cpe_configurations", [])]
    if not cve_id or not cpes:
        return None
    if int(_digest(f"{record.id}:applicability")[:8], 16) % 3 != 0:
        return None
    description = _clip(_strip_markdown(record.response or ""), 500)
    prompt = (
        "A scanner reports this CVE against a production host. Explain how to test "
        "whether the CPE applicability actually matches the host, and what evidence "
        "would justify a false-positive decision.\n\n"
        f"CVE: {cve_id}\nCPE configurations: {', '.join(cpes[:4])}\n"
        f"Description: {description}"
    )
    parsed_cpes = []
    for cpe in cpes[:4]:
        parts = cpe.split(":")
        if len(parts) >= 6:
            target_sw = parts[10] if len(parts) > 10 else ""
            parsed_cpes.append(
                f"vendor={parts[3] or '*'}, product={parts[4] or '*'}, "
                f"version={parts[5] or '*'}, target_sw={target_sw or '*'}"
            )
    response = (
        f"For {cve_id}, the record carries {len(cpes)} CPE configuration(s): "
        + "; ".join(parsed_cpes)
        + ". A CPE is a product-and-version expression, not proof that the asset is affected.\n\n"
        "A `*` or `-` in the version field is a wildcard: the CPE alone cannot exclude any "
        "version, so the advisory's fixed version or range must be resolved separately. Resolve "
        "each field against the installed product, vendor, version, update, edition, language, "
        "and target software. For a package, compare the installed version with the vulnerable "
        "range using the package manager's evidence; for a container, inspect the image digest "
        "and the package database inside that digest, not the image tag alone.\n\n"
        "A false-positive decision needs positive evidence: the product is absent, the version "
        "is outside every vulnerable range, the vulnerable component is not installed or not "
        "reachable, or a vendor advisory explicitly excludes the build. Record the command "
        "output and the advisory section used. Do not close the finding because the description "
        "sounds unrelated or because a different scanner disagrees."
    )
    out = _metadata(record, "false-positive-recognition", "nvd-cpe-applicability")
    out.update({"cve_id": cve_id, "cpe_configurations": cpes[:6]})
    return _derive(
        record,
        suffix="applicability",
        task="vulnerability-applicability",
        prompt=prompt,
        response=response,
        metadata=out,
    )


def _nvd_uncertainty(record: Record) -> Record | None:
    metadata = record.metadata or {}
    cve_id = str(metadata.get("cve_id") or "")
    if not cve_id:
        return None
    description = _clip(_strip_markdown(record.response or ""), 500)
    prompt = (
        f'A ticket says: "Host host-01 is vulnerable because scanner output lists {cve_id}." '
        "Does the NVD record prove that claim? Explain what is established and what evidence "
        "is missing.\n\n"
        f"NVD description: {description}"
    )
    response = (
        f"No. The NVD record identifies {cve_id} and describes the vulnerability; it does not "
        "show that host-01 runs an affected product or version. To support the claim, collect "
        "the installed package or build version, the CPE applicability, the exposed service and "
        "network path, and the scanner's evidence for its version match. Then check whether the "
        "asset is actually reachable by the described attack vector and whether a vendor fix or "
        "compensating control exists.\n\n"
        "If the version cannot be established from inventory, verify it on the host with an "
        "authenticated check and record the command output. Label the finding 'unconfirmed' "
        "until that evidence exists; do not close it as a false positive merely because the "
        "description sounds inapplicable."
    )
    metadata = _metadata(record, "uncertainty-handling", "nvd-insufficient-evidence")
    metadata.update({"cve_id": cve_id})
    return _derive(
        record,
        suffix="uncertainty",
        task="uncertainty",
        prompt=prompt,
        response=response,
        metadata=metadata,
    )


def _nvd_json(record: Record) -> Record | None:
    metadata = record.metadata or {}
    cve_id = str(metadata.get("cve_id") or "")
    if not cve_id:
        return None
    if int(_digest(f"{record.id}:json")[:8], 16) % 2 != 0:
        return None
    cvss = _cvss_v3(record)
    evidence = {
        "id": cve_id,
        "published": metadata.get("published"),
        "vulnStatus": metadata.get("vuln_status"),
        "descriptions": [
            {"lang": "en", "value": _clip(_strip_markdown(record.response or ""), 500)}
        ],
        "metrics": {
            "cvssMetricV31": (
                [
                    {
                        "cvssData": {
                            "vectorString": cvss["vector"],
                            "baseScore": cvss["score"],
                            "baseSeverity": cvss["severity"],
                        }
                    }
                ]
                if cvss
                else []
            )
        },
        "weaknesses": [
            {"description": [{"value": item}]} for item in metadata.get("weaknesses", [])
        ],
    }
    prompt = (
        "Extract a compact triage object from this NVD-style JSON. Return only a JSON object "
        "with keys `cve_id`, `severity`, `base_score`, `attack_vector`, and `weaknesses`. "
        "`weaknesses` must be an array. If a value is absent, use null. Do not add keys.\n\n"
        + json.dumps(evidence, indent=2)
    )
    answer = {
        "cve_id": cve_id,
        "severity": str(cvss["severity"]).lower() if cvss and cvss.get("severity") else None,
        "base_score": cvss["score"] if cvss else None,
        "attack_vector": cvss["metrics"]["AV"] if cvss else None,
        "weaknesses": [str(item) for item in metadata.get("weaknesses", [])],
    }
    metadata_out = _metadata(record, "structured-json", "nvd-extraction")
    metadata_out.update({"structured_output": "json", "cve_id": cve_id})
    return _derive(
        record,
        suffix="json",
        task="structured-extraction",
        prompt=prompt,
        response=json.dumps(answer, indent=2),
        metadata=metadata_out,
    )


def _attack_description(record: Record) -> str:
    body = record.response or ""
    body = re.split(r"\n\nPlatforms:", body, maxsplit=1)[0]
    body = _ATTACK_ID_RE.sub("", body)
    name = str((record.metadata or {}).get("name") or "")
    if name:
        body = body.replace(name, "this behaviour")
    return _clip(_strip_markdown(body), 800)


def _attack_matching(
    record: Record, technique_index: dict[str, list[tuple[str, str]]]
) -> Record | None:
    metadata = record.metadata or {}
    name = str(metadata.get("name") or "")
    attack_id = str(metadata.get("attack_id") or "")
    phase = str(metadata.get("kill_chain_phases") or "").split(",")[0].strip()
    if not name or not attack_id or not phase:
        return None
    pool = [
        (other_name, other_id)
        for other_name, other_id in technique_index.get(phase, [])
        if other_name != name and other_id != attack_id
    ]
    if len(pool) < 3:
        return None
    chosen = sorted(pool, key=lambda item: _digest(f"{record.id}:attack:{item[1]}"))[:3]
    options = [name] + [item[0] for item in chosen]
    order = sorted(
        range(len(options)), key=lambda position: _digest(f"{record.id}:attack-order:{position}")
    )
    shuffled = [options[position] for position in order]
    correct_position = shuffled.index(name)
    letters = "ABCD"
    lines = "\n".join(f"{letters[index]}. {text}" for index, text in enumerate(shuffled))
    description = _attack_description(record)
    prompt = (
        "Which MITRE ATT&CK technique does the following observed behaviour most closely "
        "match? Select one option.\n\n"
        f"Observed behaviour: {description}\n\n{lines}"
    )
    answer = (
        f"**Correct answer: {letters[correct_position]} — {name} ({attack_id})**\n\n"
        f"The behaviour aligns with {name} in the {phase} phase. The other options name "
        "different techniques and would require different evidence: match on the action "
        "actually observed, not on a tool name or a single string.\n\n"
        "Confirm the mapping with the technique's documented procedure examples and the "
        "telemetry available in your environment. ATT&CK mapping is an analytic judgement, "
        "not a detection by itself."
    )
    out_metadata = _metadata(record, "attack-technique-recognition", "attack-matching")
    out_metadata.update(
        {
            "attack_id": attack_id,
            "mcq_options": shuffled,
            "mcq_answer_indexes": [correct_position],
        }
    )
    return _derive(
        record,
        suffix="match",
        task="attack-technique",
        prompt=prompt,
        response=answer,
        metadata=out_metadata,
    )


def _attack_detection(record: Record) -> Record | None:
    body = record.response or ""
    marker = "Detection considerations:"
    if marker not in body:
        return None
    detection = body.split(marker, 1)[1].strip()
    detection = _clip(_strip_markdown(detection), 1200)
    metadata = record.metadata or {}
    name = str(metadata.get("name") or "")
    attack_id = str(metadata.get("attack_id") or "")
    platforms = str(metadata.get("platforms") or "the listed platforms")
    prompt = (
        f"A defender is prioritizing telemetry for {name} ({attack_id}). Using the ATT&CK "
        "detection guidance, what should be collected, what is hard to observe, and what "
        "mitigation reduces the opportunity?"
    )
    response = (
        f"ATT&CK's detection considerations for {name} are:\n\n{detection}\n\n"
        f"The technique lists platforms: {platforms}. Translate the guidance into concrete "
        "log sources for those platforms, then test the detection against known-good activity. "
        "A technique can be executed with different tools; a rule that matches only one tool "
        "name will miss variants. Pair detection with prevention or hardening where the "
        "technique's prerequisites can be removed."
    )
    out_metadata = _metadata(record, "detection-engineering", "attack-detection-guidance")
    out_metadata.update({"attack_id": attack_id, "extraction": True})
    return _derive(
        record,
        suffix="detection",
        task="detection-engineering",
        prompt=prompt,
        response=response,
        metadata=out_metadata,
    )


def _cwe_description(record: Record) -> str:
    body = record.response or ""
    body = _CWE_ID_RE.sub("", body)
    name = str((record.metadata or {}).get("name") or "")
    if name:
        body = body.replace(name, "the weakness")
    body = re.sub(r"^[\s:;,.\-]+", "", body)
    body = re.sub(r"\bthe weakness\s*[.:;]\s*", "", body, count=1)
    return _clip(_strip_markdown(body), 700)


def _cwe_matching(record: Record, cwe_index: dict[str, list[tuple[str, str]]]) -> Record | None:
    metadata = record.metadata or {}
    cwe_id = str(metadata.get("cwe_id") or "")
    name = str(metadata.get("name") or "")
    abstraction = str(metadata.get("abstraction") or "")
    if not cwe_id or not name:
        return None
    pool = [
        (other_name, other_id)
        for other_name, other_id in cwe_index.get(abstraction, [])
        if other_id != cwe_id and other_name != name
    ]
    if len(pool) < 3:
        return None
    chosen = sorted(pool, key=lambda item: _digest(f"{record.id}:cwe:{item[1]}"))[:3]
    options = [name] + [item[0] for item in chosen]
    order = sorted(
        range(len(options)), key=lambda position: _digest(f"{record.id}:cwe-order:{position}")
    )
    shuffled = [options[position] for position in order]
    correct_position = shuffled.index(name)
    letters = "ABCD"
    lines = "\n".join(f"{letters[index]}. {text}" for index, text in enumerate(shuffled))
    description = _cwe_description(record)
    prompt = (
        "A code review identifies the weakness pattern below. Which CWE class best matches "
        "it? Select one option.\n\n"
        f"Pattern: {description}\n\n{lines}"
    )
    answer = (
        f"**Correct answer: {letters[correct_position]} — {cwe_id} ({name})**\n\n"
        f"The description matches {name}. The other options describe different root causes; "
        "classify by the flaw in the code, not by the visible impact. Confirm the choice "
        "against the CWE definition and record the affected code path."
    )
    out_metadata = _metadata(record, "vulnerability-classification", "cwe-matching")
    out_metadata.update(
        {
            "cwe_id": cwe_id,
            "mcq_options": shuffled,
            "mcq_answer_indexes": [correct_position],
        }
    )
    return _derive(
        record,
        suffix="match",
        task="weakness-classification",
        prompt=prompt,
        response=answer,
        metadata=out_metadata,
    )


def _cwe_review_questions(record: Record) -> Record | None:
    metadata = record.metadata or {}
    cwe_id = str(metadata.get("cwe_id") or "")
    name = str(metadata.get("name") or "")
    if not cwe_id or not name:
        return None
    root_cause = CWE_ROOT_CAUSE.get(cwe_id)
    if root_cause is None:
        return None
    prompt = (
        f"A team is reviewing a service for {cwe_id} ({name}). Give three code-review "
        "questions that would expose the weakness and one negative test that should fail "
        "before the fix and pass after it."
    )
    response = (
        f"Review questions for {cwe_id} ({name}):\n\n"
        f"1. Where does untrusted data enter the component, and can it reach the code path "
        f"associated with {root_cause}? Trace the value from the boundary to the sink and "
        "record every transformation.\n"
        f"2. Which API or configuration creates the condition ({root_cause}), and is there a "
        "safer API or framework default that removes the choice entirely?\n"
        f"3. What evidence shows the control is applied consistently on every route, job, "
        "and error path, rather than only on the reviewed handler?\n\n"
        "Negative test: send a benign, authorized reproduction of the abuse case in a test "
        "environment and assert that it is rejected or neutralized without a server error. "
        "The test must fail against the vulnerable revision and pass against the fix; a test "
        "that only asserts a specific payload string is blocked is not sufficient."
    )
    out = _metadata(record, "secure-code-review", "cwe-review-questions")
    out.update({"cwe_id": cwe_id})
    return _derive(
        record,
        suffix="review",
        task="secure-code-review",
        prompt=prompt,
        response=response,
        metadata=out,
    )


def _cwe_mitigation(record: Record) -> Record | None:
    body = record.response or ""
    if "Potential mitigations:" not in body:
        return None
    mitigation = body.split("Potential mitigations:", 1)[1]
    if "Detection methods:" in mitigation:
        mitigation, detection = mitigation.split("Detection methods:", 1)
    else:
        detection = ""
    mitigation = _clip(_strip_markdown(mitigation), 1000)
    detection = _clip(_strip_markdown(detection.split("Related weaknesses:", 1)[0]), 700)
    metadata = record.metadata or {}
    cwe_id = str(metadata.get("cwe_id") or "")
    name = str(metadata.get("name") or "")
    prompt = (
        f"CWE-{cwe_id.split('-')[-1]} ({name}) lists potential mitigations and detection "
        "methods. Summarize the defensive options and state which one addresses the root "
        "cause rather than a symptom."
    )
    lines = [f"Recorded potential mitigations for {cwe_id} ({name}):", mitigation]
    if detection:
        lines.append(f"Recorded detection methods:\n{detection}")
    root_cause = CWE_ROOT_CAUSE.get(cwe_id)
    if root_cause:
        lines.append(
            f"Prefer the control that removes the root cause ({root_cause}) over a filter "
            "that blocks known payloads. Detection is compensating evidence, not remediation. "
            "Validate the control with an abuse-case test and a check that legitimate "
            "functionality still works."
        )
    else:
        lines.append(
            "Apply the recorded mitigation and confirm that it addresses the recorded root "
            "cause; do not substitute a generic input filter. Detection is compensating "
            "evidence, not remediation. Validate the control with an abuse-case test and a "
            "check that legitimate functionality still works."
        )
    out_metadata = _metadata(record, "vulnerability-remediation", "cwe-mitigation")
    out_metadata.update({"cwe_id": cwe_id, "extraction": True})
    return _derive(
        record,
        suffix="mitigation",
        task="vulnerability-remediation",
        prompt=prompt,
        response="\n\n".join(lines),
        metadata=out_metadata,
    )


def _two_claims(record: Record) -> list[Record | None]:
    """Return up to two evidence-application views from one document."""

    records: list[Record | None] = []
    for index in (0, 1):
        result = _evidence_requirement(record, index=index)
        if result is not None:
            records.append(result[0])
    return records


def _confidence_for(record: Record) -> float:
    """A transparent evidence-coverage signal, not a model confidence."""

    metadata = record.metadata or {}
    score = 0.35
    if record.url:
        score += 0.15
    if metadata.get("source_version"):
        score += 0.15
    if metadata.get("upstream_id"):
        score += 0.1
    if len(record.response or "") >= 300:
        score += 0.1
    if metadata.get("license_url"):
        score += 0.05
    if metadata.get("cvss") or metadata.get("cwe_id") or metadata.get("attack_id"):
        score += 0.1
    return round(min(score, 1.0), 2)


def generate_grounded(
    records: list[Record],
    *,
    cwe_names: dict[str, str] | None = None,
    max_per_record: int = 3,
) -> GroundedResult:
    """Generate grounded task views from source records."""

    cwe_names = cwe_names or {}
    attack_index: dict[str, list[tuple[str, str]]] = {}
    cwe_index: dict[str, list[tuple[str, str]]] = {}
    for record in records:
        metadata = record.metadata or {}
        if record.source == "mitre_attack" and metadata.get("object_type") == "attack-pattern":
            phase = str(metadata.get("kill_chain_phases") or "").split(",")[0].strip()
            name = str(metadata.get("name") or "")
            attack_id = str(metadata.get("attack_id") or "")
            if phase and name and attack_id:
                attack_index.setdefault(phase, []).append((name, attack_id))
        if record.source == "mitre_cwe":
            abstraction = str(metadata.get("abstraction") or "")
            name = str(metadata.get("name") or "")
            cwe_id = str(metadata.get("cwe_id") or "")
            if abstraction and name and cwe_id:
                cwe_index.setdefault(abstraction, []).append((name, cwe_id))
                cwe_names.setdefault(cwe_id, name)

    generated: list[Record] = []
    variant_counts: dict[str, int] = {}
    skipped = 0
    for record in records:
        candidates: list[Record | None] = []
        if record.source == "nist_nvd":
            candidates = [
                _nvd_triage(record),
                _nvd_cwe_mapping(record, cwe_names),
                _nvd_uncertainty(record),
                _nvd_json(record),
                _nvd_applicability(record),
                _nvd_metric_counterfactual(record),
            ]
            requirement = _evidence_requirement(record)
            if requirement:
                candidates.append(requirement[0])
        elif record.source == "mitre_attack":
            candidates = [
                _attack_matching(record, attack_index),
                _attack_detection(record),
            ]
            requirement = _evidence_requirement(record)
            if requirement:
                candidates.append(requirement[0])
        elif record.source == "mitre_cwe":
            candidates = [
                _cwe_matching(record, cwe_index),
                _cwe_mitigation(record),
                _cwe_review_questions(record),
            ]
            requirement = _evidence_requirement(record)
            if requirement:
                candidates.append(requirement[0])
        elif record.source in {
            "owasp_cheatsheets",
            "ietf_rfcs",
            "linux_man_pages",
            "openssh_docs",
            "netfilter_nftables",
        }:
            candidates = _two_claims(record)
        else:
            continue
        selected = [item for item in candidates if item is not None][:max_per_record]
        if not selected:
            skipped += 1
            continue
        for item in selected:
            metadata = item.metadata
            metadata["evidence_coverage"] = _confidence_for(record)
            generated.append(item)
            family = str(metadata.get("variant", "unknown"))
            variant_counts[family] = variant_counts.get(family, 0) + 1
    stats = {
        "input_records": len(records),
        "generated_records": len(generated),
        "skipped_records": skipped,
        "variant_counts": dict(sorted(variant_counts.items())),
        "source_counts": _count(generated, lambda item: item.source),
        "license_counts": _count(generated, lambda item: item.license),
        "extractive_records": sum(
            1 for item in generated if (item.metadata or {}).get("extraction")
        ),
    }
    return GroundedResult(records=generated, stats=stats)


def _count(records: list[Record], key: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = str(key(record))
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))

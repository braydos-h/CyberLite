"""Source registry and source-specific normalizers.

No source is downloaded unless the caller explicitly requests it. Normalizers
operate on local files and preserve provenance in every generated record. The
pipeline separates *acquisition* (cache/download) from *normalization* so that
an offline rebuild can reuse exact cached inputs.
"""

from __future__ import annotations

import json
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

import yaml

from cyberlite.data.acquire import fetch_file
from cyberlite.data.cleaning import normalize_license, normalize_text, strip_html
from cyberlite.data.markdown import load_markdown_sections
from cyberlite.data.nvd import NvdClient, NvdError
from cyberlite.data.schema import Record, load_records
from cyberlite.data.textdocs import parse_rfc, parse_roff
from cyberlite.logging_utils import get_logger

logger = get_logger(__name__)

SOURCE_REGISTRY_SCHEMA = 1
TRANSFORMATION = "cyberlite-normalize-v2"

_MANPAGE_TASK_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("chmod", "chown", "umask", "access", "capabilities", "credentials", "passwd", "group"),
        "permissions",
    ),
    (
        (
            "tcp",
            "udp",
            "ip",
            "arp",
            "netlink",
            "socket",
            "unix",
            "resolv.conf",
            "hosts",
            "nsswitch",
        ),
        "networking",
    ),
    (("syslog", "proc", "sysctl", "journal", "audit"), "logging-monitoring"),
    (("sshd_config", "ssh_config", "nft", "iptables", "nftables"), "system-hardening"),
    (("random", "getrandom", "crypto"), "cryptography"),
)

_RFC_TASK_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("tls", "transport layer security", "certificate"), "tls"),
    (("dns", "domain name"), "dns"),
    (("ssh", "secure shell"), "ssh"),
    (("syslog", "logging"), "logging-monitoring"),
    (("ip", "address", "routing", "network"), "networking"),
)


@dataclass
class SourceSpec:
    name: str
    title: str
    kind: str
    license: str
    homepage: str = ""
    url: str = ""
    filename: str = ""
    enabled: bool = True
    redistributable: bool = False
    citation: str = ""
    notes: str = ""
    max_records: int | None = None
    revision: str = ""
    license_url: str = ""
    terms_url: str = ""
    attribution_required: bool = False
    commercial_use: bool | None = None
    allowed_uses: list[str] = field(default_factory=list)
    redistribution_notes: str = ""
    unresolved: list[str] = field(default_factory=list)
    options: dict[str, Any] = field(default_factory=dict)

    _ALLOWED: ClassVar[set[str]] = {
        "title",
        "kind",
        "license",
        "homepage",
        "url",
        "filename",
        "enabled",
        "redistributable",
        "citation",
        "notes",
        "max_records",
        "revision",
        "license_url",
        "terms_url",
        "attribution_required",
        "commercial_use",
        "allowed_uses",
        "redistribution_notes",
        "unresolved",
        "options",
    }

    @classmethod
    def from_dict(cls, name: str, payload: dict[str, Any]) -> SourceSpec:
        unknown = set(payload) - cls._ALLOWED
        if unknown:
            raise ValueError(f"source {name!r} has unknown fields: {sorted(unknown)}")
        if not payload.get("license"):
            raise ValueError(f"source {name!r} is missing a license")
        if not payload.get("kind"):
            raise ValueError(f"source {name!r} is missing a kind")
        options = payload.get("options", {})
        if not isinstance(options, dict):
            raise ValueError(f"source {name!r} options must be a mapping")
        allowed_uses = payload.get("allowed_uses", [])
        if isinstance(allowed_uses, str):
            allowed_uses = [allowed_uses]
        unresolved = payload.get("unresolved", [])
        if isinstance(unresolved, str):
            unresolved = [unresolved]
        return cls(
            name=name,
            title=str(payload.get("title", name)),
            kind=str(payload["kind"]),
            license=str(payload["license"]),
            homepage=str(payload.get("homepage", "")),
            url=str(payload.get("url", "")),
            filename=str(payload.get("filename", "")),
            enabled=bool(payload.get("enabled", True)),
            redistributable=bool(payload.get("redistributable", False)),
            citation=str(payload.get("citation", "")),
            notes=str(payload.get("notes", "")),
            max_records=(
                int(payload["max_records"]) if payload.get("max_records") is not None else None
            ),
            revision=str(payload.get("revision", "")),
            license_url=str(payload.get("license_url", "")),
            terms_url=str(payload.get("terms_url", "")),
            attribution_required=bool(payload.get("attribution_required", False)),
            commercial_use=payload.get("commercial_use"),
            allowed_uses=[str(item) for item in allowed_uses],
            redistribution_notes=str(payload.get("redistribution_notes", "")),
            unresolved=[str(item) for item in unresolved],
            options=dict(options),
        )


@dataclass
class SourceRegistry:
    schema_version: int
    sources: dict[str, SourceSpec] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> SourceRegistry:
        payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("sources.yaml root must be a mapping")
        version = int(payload.get("schema_version", SOURCE_REGISTRY_SCHEMA))
        if version != SOURCE_REGISTRY_SCHEMA:
            raise ValueError(f"unsupported source registry schema: {version}")
        raw_sources = payload.get("sources")
        if not isinstance(raw_sources, dict):
            raise ValueError("sources.yaml must contain a 'sources' mapping")
        sources = {name: SourceSpec.from_dict(name, spec) for name, spec in raw_sources.items()}
        return cls(schema_version=version, sources=sources)

    def get(self, name: str) -> SourceSpec:
        if name not in self.sources:
            raise KeyError(f"unknown source {name!r}; known: {', '.join(sorted(self.sources))}")
        return self.sources[name]

    def enabled(self) -> list[SourceSpec]:
        return [spec for spec in self.sources.values() if spec.enabled]


def download_source(spec: SourceSpec, destination_dir: str | Path, *, force: bool = False) -> Path:
    """Download a registered source with an explicit user action.

    The default workflow never calls this function. Callers must pass
    ``--download`` and accept the source license before use.
    """

    if not spec.url:
        raise ValueError(f"source {spec.name!r} does not define a download URL")
    destination_dir = Path(destination_dir)
    destination = destination_dir / (spec.filename or Path(spec.url).name or f"{spec.name}.json")
    result = fetch_file(
        spec.url,
        destination,
        force=force,
        timeout=120.0,
        retries=4,
        resume=True,
    )
    return result.path


def _record(
    spec: SourceSpec,
    *,
    identifier: str,
    prompt: str,
    response: str,
    task: str,
    metadata: dict[str, Any] | None = None,
    url: str = "",
    license_id: str = "",
) -> Record | None:
    response = normalize_text(response, max_chars=20_000)
    prompt = normalize_text(prompt, max_chars=4_000)
    if len(response) < 120:
        return None
    payload = dict(metadata or {})
    payload.setdefault("upstream_id", identifier)
    payload.setdefault("source_version", spec.revision or "unversioned")
    payload.setdefault("source_url", url or spec.homepage)
    payload.setdefault("transformation", TRANSFORMATION)
    payload.setdefault("source_title", spec.title)
    payload.setdefault("citation", spec.citation)
    if spec.license_url:
        payload.setdefault("license_url", spec.license_url)
    if spec.terms_url:
        payload.setdefault("terms_url", spec.terms_url)
    record_license = normalize_license(license_id or spec.license)
    return Record(
        id="",
        source=spec.name,
        license=record_license,
        task=task,
        prompt=prompt,
        response=response,
        url=url or spec.homepage,
        metadata=payload,
    )


def normalize_stix_attack(path: str | Path, spec: SourceSpec) -> list[Record]:
    """Convert a MITRE ATT&CK STIX 2.1 bundle into defensive QA records."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    objects = payload.get("objects", [])
    if not isinstance(objects, list):
        raise ValueError(f"{path}: STIX bundle has no objects list")
    records: list[Record] = []
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        obj_type = obj.get("type")
        if obj_type not in {"attack-pattern", "course-of-action"}:
            continue
        if obj.get("revoked") or obj.get("deprecated"):
            continue
        name = str(obj.get("name", "Unknown"))
        description = str(obj.get("description", ""))
        external_id = ""
        reference_url = ""
        for reference in obj.get("external_references", []):
            if not isinstance(reference, dict):
                continue
            if reference.get("source_name") == "mitre-attack":
                external_id = str(reference.get("external_id", ""))
                reference_url = str(reference.get("url", ""))
                break
        group_id = external_id or str(obj.get("id", name))
        if obj_type == "attack-pattern":
            detection = str(obj.get("x_mitre_detection", ""))
            platforms = ", ".join(str(item) for item in obj.get("x_mitre_platforms", []))
            phases = ", ".join(
                str(phase.get("phase_name", "")) for phase in obj.get("kill_chain_phases", [])
            )
            body = [description]
            if platforms:
                body.append(f"Platforms: {platforms}.")
            if phases:
                body.append(f"Kill-chain phases: {phases}.")
            if detection:
                body.append(f"Detection considerations: {detection}")
            prompt = (
                f"Explain the MITRE ATT&CK technique {external_id or name} ({name}) "
                "and summarize defensive detection considerations."
            )
            task = "attack-technique"
            url = reference_url or (
                f"https://attack.mitre.org/techniques/{external_id}/"
                if external_id
                else spec.homepage
            )
        else:
            body = [description]
            prompt = (
                f"Describe the defensive course of action {external_id or name} ({name}) "
                "from MITRE ATT&CK and when it is useful."
            )
            task = "defensive-control"
            url = reference_url or spec.homepage
        record = _record(
            spec,
            identifier=group_id,
            prompt=prompt,
            response="\n\n".join(part for part in body if part),
            task=task,
            metadata={
                "attack_id": external_id,
                "name": name,
                "object_type": obj_type,
                "platforms": platforms if obj_type == "attack-pattern" else "",
                "kill_chain_phases": phases if obj_type == "attack-pattern" else "",
                "group": f"{spec.name}:{group_id}",
                "revoked": bool(obj.get("revoked")),
                "deprecated": bool(obj.get("deprecated")),
                "attack_version": str(payload.get("spec_version", "")),
            },
            url=url,
        )
        if record:
            records.append(record)
    return _apply_limit(records, spec)


def _xml_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return strip_html("".join(element.itertext()))


def _related_cwes(weakness: ET.Element) -> list[str]:
    related: list[str] = []
    for element in weakness.iter():
        tag = element.tag.split("}")[-1]
        if tag != "Related_Weakness":
            continue
        cwe_id = element.attrib.get("CWE_ID", "")
        nature = element.attrib.get("Nature", "")
        if cwe_id:
            related.append(f"CWE-{cwe_id}" + (f" ({nature})" if nature else ""))
    return sorted(set(related))


def normalize_cwe_xml(path: str | Path, spec: SourceSpec) -> list[Record]:
    """Convert a CWE XML release into weakness and mitigation QA records."""

    tree = ET.parse(path)
    root = tree.getroot()
    records: list[Record] = []
    for weakness in root.iter():
        if not weakness.tag.endswith("Weakness"):
            continue
        cwe_id = weakness.attrib.get("ID", "")
        name = weakness.attrib.get("Name", "")
        status = weakness.attrib.get("Status", "")
        if not cwe_id:
            continue
        if status.lower() in {"deprecated", "obsolete"}:
            continue
        values: dict[str, str] = {}
        for child in weakness:
            tag = child.tag.split("}")[-1]
            if tag in {
                "Description",
                "Extended_Description",
                "Potential_Mitigations",
                "Detection_Methods",
                "Common_Consequences",
                "Likelihood_Of_Exploit",
            }:
                values[tag] = _xml_text(child)
        description = values.get("Extended_Description") or values.get("Description", "")
        if not description:
            continue
        mitigations = values.get("Potential_Mitigations", "")
        detection = values.get("Detection_Methods", "")
        consequences = values.get("Common_Consequences", "")
        likelihood = values.get("Likelihood_Of_Exploit", "")
        related = _related_cwes(weakness)
        body = [f"CWE-{cwe_id}: {name}.", description]
        if likelihood:
            body.append(f"Likelihood of exploit: {likelihood}")
        if consequences:
            body.append(f"Common consequences: {consequences}")
        if mitigations:
            body.append(f"Potential mitigations: {mitigations}")
        if detection:
            body.append(f"Detection methods: {detection}")
        if related:
            body.append("Related weaknesses: " + ", ".join(related))
        record = _record(
            spec,
            identifier=f"CWE-{cwe_id}",
            prompt=(
                f"Explain CWE-{cwe_id} ({name}), including its security impact, "
                "mitigation options, detection methods, and relevant relationships."
            ),
            response="\n\n".join(body),
            task="weakness",
            metadata={
                "cwe_id": f"CWE-{cwe_id}",
                "name": name,
                "status": status,
                "abstraction": weakness.attrib.get("Abstraction", ""),
                "related_weaknesses": related,
                "group": f"{spec.name}:CWE-{cwe_id}",
                "cwe_version": str(root.attrib.get("Version", "")),
            },
            url=f"https://cwe.mitre.org/data/definitions/{cwe_id}.html",
        )
        if record:
            records.append(record)
    return _apply_limit(records, spec)


def _english_description(descriptions: Iterable[dict[str, Any]]) -> str:
    for description in descriptions:
        if not isinstance(description, dict):
            continue
        if description.get("lang", "en") == "en":
            return str(description.get("value", ""))
    return ""


def _nvd_metrics(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    for key in ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        for metric in metrics.get(key, [])[:2]:
            if not isinstance(metric, dict):
                continue
            data = metric.get("cvssData", {}) or {}
            if not data:
                continue
            collected.append(
                {
                    "version": str(data.get("version", key.replace("cvssMetricV", ""))),
                    "severity": str(data.get("baseSeverity", "UNKNOWN")),
                    "score": data.get("baseScore"),
                    "vector": str(data.get("vectorString", "")),
                    "source": str(metric.get("source", "")),
                    "type": str(metric.get("type", "")),
                    "exploitability": metric.get("exploitabilityScore"),
                    "impact": metric.get("impactScore"),
                }
            )
    return collected


def _nvd_cpes(configurations: Any) -> list[str]:
    cpes: list[str] = []

    def walk(node: Any) -> None:
        if not isinstance(node, dict):
            return
        for match in node.get("cpeMatch", []) or []:
            if isinstance(match, dict) and match.get("vulnerable") and match.get("criteria"):
                cpes.append(str(match["criteria"]))
        for child in node.get("nodes", []) or []:
            walk(child)

    if isinstance(configurations, list):
        for item in configurations:
            walk(item)
    return sorted(set(cpes))


def _normalize_nvd_page(payload: Any, spec: SourceSpec) -> list[Record]:
    pages = payload if isinstance(payload, list) else [payload]
    records: list[Record] = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        for wrapper in page.get("vulnerabilities", []) or []:
            if not isinstance(wrapper, dict):
                continue
            cve = wrapper.get("cve", {})
            if not isinstance(cve, dict):
                continue
            cve_id = str(cve.get("id", ""))
            status = str(cve.get("vulnStatus", ""))
            description = _english_description(cve.get("descriptions", []) or [])
            if not cve_id or not description:
                continue
            if status.lower() == "rejected":
                continue
            scores = _nvd_metrics(cve.get("metrics", {}) or {})
            weaknesses: list[str] = []
            for weakness in cve.get("weaknesses", []) or []:
                for item in weakness.get("description", []) or []:
                    value = str(item.get("value", ""))
                    if value and value not in {"NVD-CWE-noinfo", "NVD-CWE-Other"}:
                        weaknesses.append(value)
            references = [
                str(reference.get("url", ""))
                for reference in cve.get("references", []) or []
                if isinstance(reference, dict) and reference.get("url")
            ][:5]
            cpes = _nvd_cpes(cve.get("configurations", []))
            published = str(cve.get("published", ""))
            modified = str(cve.get("lastModified", ""))
            body = [description]
            if published:
                body.append(f"Published: {published}.")
            if modified:
                body.append(f"Last modified: {modified}.")
            if status:
                body.append(f"NVD status: {status}.")
            if scores:
                score_lines = []
                for score in scores:
                    line = (
                        f"{score['severity']} CVSS {score['score']} ({score['vector']})"
                    ).strip()
                    if score.get("source"):
                        line += f"; source: {score['source']}"
                    score_lines.append(line)
                body.append("Severity: " + "; ".join(score_lines))
            if weaknesses:
                body.append("Weakness mapping: " + ", ".join(sorted(set(weaknesses))))
            if cpes:
                body.append(
                    "Recorded CPE configurations:\n" + "\n".join(f"- {cpe}" for cpe in cpes[:8])
                )
            if references:
                body.append("References:\n" + "\n".join(f"- {url}" for url in references))
            if not scores and not weaknesses and not references:
                body.append(
                    "The NVD record contains a description and status but no CVSS score, "
                    "CWE mapping, or reference in this page."
                )
            record = _record(
                spec,
                identifier=cve_id,
                prompt=(
                    f"Using only the NVD record, summarize {cve_id} for a defender: "
                    "affected product or configuration if recorded, severity, weakness "
                    "class, publication date, and verification references. Do not infer "
                    "remediation steps that NVD does not state."
                ),
                response="\n\n".join(body),
                task="vulnerability",
                metadata={
                    "cve_id": cve_id,
                    "published": published,
                    "last_modified": modified,
                    "vuln_status": status,
                    "cvss": scores,
                    "weaknesses": sorted(set(weaknesses)),
                    "references": references,
                    "cpe_count": len(cpes),
                    "cpe_configurations": cpes[:8],
                    "group": f"{spec.name}:{cve_id}",
                    "source_version": spec.revision or "nvd-api-2.0",
                },
                url=f"https://nvd.nist.gov/vuln/detail/{cve_id}",
            )
            if record:
                records.append(record)
    return records


def normalize_nvd_json(path: str | Path, spec: SourceSpec) -> list[Record]:
    """Convert NVD API 2.0 pages into factual vulnerability-summary records.

    The normalizer accepts a single API response object, a JSON array of
    responses, or a cached page. It skips rejected entries and does not add
    remediation claims that are absent from the NVD record.
    """

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return _apply_limit(_normalize_nvd_page(payload, spec), spec)


def normalize_nvd_pages(paths: Iterable[str | Path], spec: SourceSpec) -> list[Record]:
    records: list[Record] = []
    for path in paths:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        records.extend(_normalize_nvd_page(payload, spec))
    return _apply_limit(records, spec)


def normalize_jsonl(path: str | Path, spec: SourceSpec) -> list[Record]:
    """Load records in the CyberLite JSONL schema, overriding source/license."""

    records = load_records(path)
    for record in records:
        record.source = spec.name
        record.license = spec.license
        record.url = record.url or spec.homepage
        record.metadata.setdefault("source_url", record.url)
        record.metadata.setdefault("source_version", spec.revision or "unversioned")
        record.metadata.setdefault("transformation", TRANSFORMATION)
        record.metadata.setdefault("source_title", spec.title)
        record.metadata.setdefault("citation", spec.citation)
        record.metadata.setdefault("upstream_id", record.id)
        if spec.license_url:
            record.metadata.setdefault("license_url", spec.license_url)
        if "group" not in record.metadata:
            record.metadata["group"] = f"{spec.name}:{record.id}"
    return _apply_limit(records, spec)


def _markdown_task(spec: SourceSpec, heading: str, code_blocks: int) -> str:
    configured = str(spec.options.get("task") or "")
    if configured:
        return configured
    lowered = heading.lower()
    if any(
        keyword in lowered
        for keyword in (
            "injection",
            "xss",
            "cross-site",
            "sql",
            "authentication",
            "authorization",
            "cryptograph",
            "secure coding",
            "input validation",
        )
    ):
        return "secure-coding"
    if code_blocks:
        return "secure-coding"
    return "documentation"


def normalize_markdown(path: str | Path, spec: SourceSpec) -> list[Record]:
    """Convert a Markdown document into heading-aware, code-preserving records."""

    file_path = Path(path)
    revision = spec.revision
    document = file_path.name
    sections = load_markdown_sections(
        file_path,
        min_section_chars=int(spec.options.get("min_section_chars", 200)),
        max_section_chars=int(spec.options.get("max_section_chars", 6000)),
        max_heading_level=int(spec.options.get("max_heading_level", 3)),
    )
    records: list[Record] = []
    for section in sections:
        if len(section.body.strip()) < 120:
            continue
        task = _markdown_task(spec, section.heading, section.code_blocks)
        if spec.name == "owasp_cheatsheets" and revision:
            url = (
                f"https://github.com/OWASP/CheatSheetSeries/blob/{revision}/"
                f"cheatsheets/{document}#{section.anchor}"
            )
        else:
            url = spec.homepage
        prompt = (
            f"Explain the {spec.title} section '{section.heading}'. "
            "Provide accurate defensive guidance and preserve any relevant code examples."
        )
        if section.code_blocks:
            prompt = (
                f"Explain the {spec.title} section '{section.heading}', including the "
                "defensive pattern demonstrated by its code examples and the conditions "
                "under which it applies."
            )
        record = _record(
            spec,
            identifier=f"{document}#{section.anchor}",
            prompt=prompt,
            response=section.as_text(),
            task=task,
            metadata={
                "document": document,
                "heading": section.heading,
                "anchor": section.anchor,
                "level": section.level,
                "code_blocks": section.code_blocks,
                "group": f"{spec.name}:{document}",
                "source_version": revision or "unversioned",
                "navigation_line_ratio": section.metadata.get("navigation_line_ratio", 0.0),
            },
            url=url,
        )
        if record:
            records.append(record)
    return _apply_limit(records, spec)


def _manpage_task(title: str) -> str:
    lowered = title.lower()
    for words, task in _MANPAGE_TASK_HINTS:
        if any(word in lowered for word in words):
            return task
    return "system-administration"


def normalize_manpage(path: str | Path, spec: SourceSpec) -> list[Record]:
    """Convert a roff manual page into section-level operational records."""

    document = parse_roff(
        path,
        min_section_chars=int(spec.options.get("min_section_chars", 200)),
        max_section_chars=int(spec.options.get("max_section_chars", 6000)),
    )
    if not document.spdx_license and spec.license == "Mixed-SPDX":
        logger.warning(
            "manual page has no SPDX identifier; quarantining as unresolved licensing",
            extra={"path": str(path)},
        )
        return []
    page = Path(path).stem
    task = _manpage_task(page)
    records: list[Record] = []
    for section in document.sections:
        license_id = document.spdx_license or spec.license
        # Normalize trailing comment markers from SPDX lines such as "GPL-2.0-or-later */".
        license_id = normalize_license(license_id.split()[0] if license_id else spec.license)
        if spec.name == "linux_man_pages" and document.section:
            url = (
                f"https://man7.org/linux/man-pages/man{document.section}/"
                f"{page}.{document.section}.html"
            )
        else:
            url = spec.homepage
        record = _record(
            spec,
            identifier=f"{page}.{document.section}",
            prompt=(
                f"Explain the {page}({document.section or '?'}) manual page section "
                f"'{section.heading}' for a Linux administrator. Include the security "
                "implications and verification steps supported by the manual."
            ),
            response=section.as_text(),
            task=task,
            metadata={
                "manpage": f"{page}.{document.section}".strip("."),
                "page": page,
                "section": document.section,
                "heading": section.heading,
                "spdx_license": document.spdx_license,
                "group": f"{spec.name}:{page}.{document.section}",
                "source_version": spec.revision or document.source or "unversioned",
            },
            url=url,
            license_id=license_id,
        )
        if record:
            records.append(record)
    return _apply_limit(records, spec)


def _rfc_task(title: str) -> str:
    lowered = title.lower()
    for words, task in _RFC_TASK_HINTS:
        if any(word in lowered for word in words):
            return task
    return "networking"


def normalize_rfc(path: str | Path, spec: SourceSpec) -> list[Record]:
    """Convert an IETF RFC text document into section-level networking records."""

    document = parse_rfc(
        path,
        min_section_chars=int(spec.options.get("min_section_chars", 200)),
        max_section_chars=int(spec.options.get("max_section_chars", 6000)),
    )
    task = _rfc_task(document.title)
    number = document.number or Path(path).stem.upper()
    records: list[Record] = []
    for section in document.sections:
        record = _record(
            spec,
            identifier=f"RFC{number}:{section.heading}",
            prompt=(
                f"Explain {section.heading} from IETF RFC {number} for a defender or "
                "network administrator. Focus on operational security implications and "
                "do not add requirements the RFC does not state."
            ),
            response=section.as_text(),
            task=task,
            metadata={
                "rfc": f"RFC {number}",
                "title": document.title,
                "category": document.category,
                "date": document.date,
                "heading": section.heading,
                "group": f"{spec.name}:RFC{number}",
                "source_version": spec.revision or document.date or "unversioned",
            },
            url=f"https://www.rfc-editor.org/rfc/rfc{number}.txt",
        )
        if record:
            records.append(record)
    return _apply_limit(records, spec)


def _apply_limit(records: list[Record], spec: SourceSpec) -> list[Record]:
    if spec.max_records is not None:
        return records[: spec.max_records]
    return records


NORMALIZERS = {
    "stix_attack": normalize_stix_attack,
    "cwe_xml": normalize_cwe_xml,
    "nvd_json": normalize_nvd_json,
    "jsonl": normalize_jsonl,
    "markdown": normalize_markdown,
    "manpage": normalize_manpage,
    "roff": normalize_manpage,
    "rfc_text": normalize_rfc,
}


@dataclass
class NormalizationError:
    source: str
    path: str
    error: str

    def to_dict(self) -> dict[str, str]:
        return {"source": self.source, "path": self.path, "error": self.error}


@dataclass
class NormalizationOutcome:
    records: list[Record]
    errors: list[NormalizationError]
    files: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "records": len(self.records),
            "files": self.files,
            "errors": [error.to_dict() for error in self.errors],
        }


def normalize_source_outcome(
    path: str | Path,
    spec: SourceSpec,
    *,
    fail_fast: bool = False,
) -> NormalizationOutcome:
    """Normalize a file, ZIP archive, or directory, collecting per-file errors."""

    try:
        normalizer = NORMALIZERS[spec.kind]
    except KeyError as exc:
        raise ValueError(
            f"source {spec.name!r} has unsupported kind {spec.kind!r}; "
            f"supported: {', '.join(sorted(NORMALIZERS))}"
        ) from exc
    source_path = Path(path)
    errors: list[NormalizationError] = []
    files = 0
    records: list[Record] = []

    def process(item: Path) -> None:
        nonlocal files
        files += 1
        try:
            records.extend(normalizer(item, spec))
        except Exception as exc:
            if fail_fast:
                raise
            errors.append(
                NormalizationError(source=spec.name, path=str(item), error=str(exc)[:500])
            )
            logger.warning(
                "normalization failed",
                extra={"source": spec.name, "path": str(item), "error": str(exc)},
            )

    if source_path.is_dir():
        for item in _directory_files(source_path, spec):
            process(item)
        if not files:
            raise FileNotFoundError(
                f"no {spec.kind} files found for source {spec.name!r} under {source_path}"
            )
    elif source_path.suffix.lower() == ".zip":
        with tempfile.TemporaryDirectory(prefix="cyberlite-source-") as temporary:
            from cyberlite.data.acquire import extract_archive

            extract_archive(source_path, temporary)
            for item in _directory_files(Path(temporary), spec):
                process(item)
            if not files:
                raise FileNotFoundError(
                    f"no {spec.kind} files found for source {spec.name!r} in {source_path}"
                )
    else:
        process(source_path)
    return NormalizationOutcome(records=_apply_limit(records, spec), errors=errors, files=files)


def normalize_source(path: str | Path, spec: SourceSpec) -> list[Record]:
    """Normalize a file, ZIP archive, or directory according to its kind."""

    return normalize_source_outcome(path, spec).records


def _directory_files(path: Path, spec: SourceSpec) -> list[Path]:
    extensions = {
        "stix_attack": (".json",),
        "nvd_json": (".json",),
        "cwe_xml": (".xml",),
        "jsonl": (".jsonl",),
        "markdown": (".md", ".markdown", ".rst", ".txt"),
        "manpage": (*tuple(f".{index}" for index in range(1, 10)), ".man", ".txt"),
        "roff": (*tuple(f".{index}" for index in range(1, 10)), ".man", ".txt"),
        "rfc_text": (".txt",),
    }[spec.kind]
    files = [
        item
        for item in sorted(path.rglob("*"))
        if item.is_file() and item.suffix.lower() in extensions
    ]
    allowlist = spec.options.get("files") or []
    if allowlist:
        wanted = {str(item).lower() for item in allowlist}
        files = [
            item for item in files if item.name.lower() in wanted or str(item).lower() in wanted
        ]
    denylist = spec.options.get("exclude_files") or []
    if denylist:
        denied = {str(item).lower() for item in denylist}
        files = [
            item
            for item in files
            if item.name.lower() not in denied and str(item).lower() not in denied
        ]
    return files


# Kept for callers that imported the private helper in older code.
def _normalize_directory(path: Path, spec: SourceSpec, normalizer: Any) -> list[Record]:
    outcome = normalize_source_outcome(path, spec)
    return outcome.records


def collect_nvd(
    spec: SourceSpec,
    cache_dir: str | Path,
    *,
    date_start: str,
    date_end: str,
    max_records: int | None = None,
    offline: bool = False,
    force: bool = False,
    page_size: int = 2000,
    api_key: str | None = None,
    sleep: Any = None,
    opener: Any = None,
) -> tuple[list[Record], dict[str, Any]]:
    """Collect NVD pages through the cached client and normalize them."""

    client_kwargs: dict[str, Any] = {
        "api_key": api_key,
        "page_size": page_size,
        "offline": offline,
    }
    if sleep is not None:
        client_kwargs["sleep"] = sleep
    if opener is not None:
        client_kwargs["opener"] = opener
    client = NvdClient(cache_dir, **client_kwargs)
    try:
        collection = client.collect_range(
            date_start, date_end, max_records=max_records, force=force
        )
    except (NvdError, ValueError) as exc:
        raise NvdError(f"NVD collection failed for {spec.name}: {exc}") from exc
    records = normalize_nvd_pages(collection.pages, spec)
    if max_records is not None:
        records = records[:max_records]
    return records, collection.to_dict()

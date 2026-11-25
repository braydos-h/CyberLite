"""Source registry and source-specific normalizers.

No source is downloaded unless the caller explicitly requests it. Normalizers
operate on local files and preserve provenance in every generated record.
"""

from __future__ import annotations

import json
import re
import shutil
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from cyberlite.data.cleaning import normalize_text, strip_html
from cyberlite.data.schema import Record
from cyberlite.logging_utils import get_logger

logger = get_logger(__name__)

SOURCE_REGISTRY_SCHEMA = 1


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

    @classmethod
    def from_dict(cls, name: str, payload: dict[str, Any]) -> SourceSpec:
        allowed = {
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
        }
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"source {name!r} has unknown fields: {sorted(unknown)}")
        if not payload.get("license"):
            raise ValueError(f"source {name!r} is missing a license")
        if not payload.get("kind"):
            raise ValueError(f"source {name!r} is missing a kind")
        return cls(name=name, **payload)


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
    destination_dir.mkdir(parents=True, exist_ok=True)
    filename = spec.filename or Path(spec.url).name or f"{spec.name}.json"
    destination = destination_dir / filename
    if destination.exists() and not force:
        logger.info("source already present", extra={"source": spec.name, "path": str(destination)})
        return destination
    request = urllib.request.Request(
        spec.url,
        headers={"User-Agent": "CyberLite/0.1 (research; +https://github.com/braydos-h/CyberLite)"},
    )
    logger.info("downloading source", extra={"source": spec.name, "url": spec.url})
    with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as handle:
        shutil.copyfileobj(response, handle)
    return destination


def _record(
    spec: SourceSpec,
    *,
    identifier: str,
    prompt: str,
    response: str,
    task: str,
    metadata: dict[str, Any] | None = None,
    url: str = "",
) -> Record | None:
    response = normalize_text(response, max_chars=20_000)
    prompt = normalize_text(prompt, max_chars=4_000)
    if len(response) < 120:
        return None
    return Record(
        id="",
        source=spec.name,
        license=spec.license,
        task=task,
        prompt=prompt,
        response=response,
        url=url or spec.homepage,
        metadata=metadata or {},
    )


def normalize_stix_attack(path: str | Path, spec: SourceSpec) -> list[Record]:
    """Convert a MITRE ATT&CK STIX 2.1 bundle into defensive QA records."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    objects = payload.get("objects", [])
    records: list[Record] = []
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        obj_type = obj.get("type")
        if obj_type not in {"attack-pattern", "course-of-action"}:
            continue
        name = obj.get("name", "Unknown")
        description = obj.get("description", "")
        external_id = ""
        for reference in obj.get("external_references", []):
            if reference.get("source_name") == "mitre-attack":
                external_id = reference.get("external_id", "")
                break
        if obj_type == "attack-pattern":
            detection = obj.get("x_mitre_detection", "")
            platforms = ", ".join(obj.get("x_mitre_platforms", []))
            phases = ", ".join(
                phase.get("phase_name", "") for phase in obj.get("kill_chain_phases", [])
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
        else:
            body = [description]
            prompt = (
                f"Describe the defensive course of action {external_id or name} ({name}) "
                "from MITRE ATT&CK and when it is useful."
            )
            task = "defensive-control"
        record = _record(
            spec,
            identifier=external_id or name,
            prompt=prompt,
            response="\n\n".join(part for part in body if part),
            task=task,
            metadata={"attack_id": external_id, "name": name, "object_type": obj_type},
            url=f"https://attack.mitre.org/techniques/{external_id}/"
            if external_id
            else spec.homepage,
        )
        if record:
            records.append(record)
    return _apply_limit(records, spec)


def _xml_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return strip_html("".join(element.itertext()))


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
        if not cwe_id:
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
        mitigations = values.get("Potential_Mitigations", "")
        detection = values.get("Detection_Methods", "")
        if not description:
            continue
        body = [f"CWE-{cwe_id}: {name}.", description]
        if mitigations:
            body.append(f"Potential mitigations: {mitigations}")
        if detection:
            body.append(f"Detection methods: {detection}")
        record = _record(
            spec,
            identifier=cwe_id,
            prompt=(
                f"Explain CWE-{cwe_id} ({name}), including its security impact, "
                "mitigation options, and detection methods."
            ),
            response="\n\n".join(body),
            task="weakness",
            metadata={"cwe_id": f"CWE-{cwe_id}", "name": name},
            url=f"https://cwe.mitre.org/data/definitions/{cwe_id}.html",
        )
        if record:
            records.append(record)
    return _apply_limit(records, spec)


def _english_description(descriptions: Iterable[dict[str, Any]]) -> str:
    for description in descriptions:
        if description.get("lang", "en") == "en":
            return description.get("value", "")
    return ""


def normalize_nvd_json(path: str | Path, spec: SourceSpec) -> list[Record]:
    """Convert NVD API 2.0 JSON pages into vulnerability-summary records.

    The normalizer accepts a single API response object or a JSON array of
    responses. It does not add remediation claims that are absent from NVD.
    """

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    pages = payload if isinstance(payload, list) else [payload]
    records: list[Record] = []
    for page in pages:
        for wrapper in page.get("vulnerabilities", []):
            cve = wrapper.get("cve", {})
            cve_id = cve.get("id", "")
            description = _english_description(cve.get("descriptions", []))
            if not cve_id or not description:
                continue
            metrics = cve.get("metrics", {})
            scores: list[str] = []
            for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
                for metric in metrics.get(key, [])[:1]:
                    data = metric.get("cvssData", {})
                    if data:
                        scores.append(
                            f"{data.get('baseSeverity', 'UNKNOWN')} "
                            f"CVSS {data.get('baseScore', 'n/a')} ({data.get('vectorString', '')})"
                        )
            weaknesses = []
            for weakness in cve.get("weaknesses", []):
                for item in weakness.get("description", []):
                    if item.get("lang") == "en":
                        weaknesses.append(item.get("value", ""))
            references = [
                ref.get("url", "") for ref in cve.get("references", []) if ref.get("url")
            ][:5]
            body = [description]
            if scores:
                body.append("Severity: " + "; ".join(scores))
            if weaknesses:
                body.append("Weakness mapping: " + ", ".join(sorted(set(weaknesses))))
            if references:
                body.append("References:\n" + "\n".join(f"- {url}" for url in references))
            record = _record(
                spec,
                identifier=cve_id,
                prompt=(
                    f"Summarize {cve_id} for a defender, including affected software, "
                    "severity, weakness class, and verification references."
                ),
                response="\n\n".join(body),
                task="vulnerability",
                metadata={"cve_id": cve_id, "weaknesses": sorted(set(weaknesses))},
                url=f"https://nvd.nist.gov/vuln/detail/{cve_id}",
            )
            if record:
                records.append(record)
    return _apply_limit(records, spec)


def normalize_jsonl(path: str | Path, spec: SourceSpec) -> list[Record]:
    """Load records in the CyberLite JSONL schema, overriding source/license."""

    from cyberlite.data.schema import load_records

    records = load_records(path)
    for record in records:
        record.source = spec.name
        record.license = spec.license
        record.url = record.url or spec.homepage
    return _apply_limit(records, spec)


_HEADING_RE = re.compile(r"^#{1,3}\s+(.+)$", re.MULTILINE)


def normalize_markdown(path: str | Path, spec: SourceSpec) -> list[Record]:
    """Convert a Markdown document into section-level explanatory records."""

    text = Path(path).read_text(encoding="utf-8", errors="replace")
    text = strip_html(text)
    if len(text) < 400:
        return []
    title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else Path(path).stem
    sections = _HEADING_RE.split(text)
    records: list[Record] = []
    chunks: list[tuple[str, str]] = []
    if len(sections) <= 1:
        chunks.append((title, text))
    else:
        # re.split with a capturing group yields [preamble, heading, body, ...]
        for index in range(1, len(sections) - 1, 2):
            heading = sections[index].strip()
            body = sections[index + 1].strip()
            if body:
                chunks.append((heading, f"# {heading}\n\n{body}"))
    for heading, chunk in chunks:
        record = _record(
            spec,
            identifier=heading,
            prompt=(
                f"Explain the following topic from {spec.title}: {heading}. "
                "Provide accurate technical detail and note defensive implications."
            ),
            response=chunk,
            task="documentation",
            metadata={"document": Path(path).name, "heading": heading},
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
}


def normalize_source(path: str | Path, spec: SourceSpec) -> list[Record]:
    """Normalize a file, ZIP archive, or directory according to the source kind."""

    try:
        normalizer = NORMALIZERS[spec.kind]
    except KeyError as exc:
        raise ValueError(
            f"source {spec.name!r} has unsupported kind {spec.kind!r}; "
            f"supported: {', '.join(sorted(NORMALIZERS))}"
        ) from exc
    source_path = Path(path)
    if source_path.is_dir():
        return _normalize_directory(source_path, spec, normalizer)
    if source_path.suffix.lower() == ".zip":
        import tempfile

        with tempfile.TemporaryDirectory(prefix="cyberlite-source-") as temporary:
            shutil.unpack_archive(source_path, temporary)
            extracted = Path(temporary)
            return _normalize_directory(extracted, spec, normalizer)
    return normalizer(source_path, spec)


def _normalize_directory(path: Path, spec: SourceSpec, normalizer: Any) -> list[Record]:
    extensions = {
        "stix_attack": (".json",),
        "nvd_json": (".json",),
        "cwe_xml": (".xml",),
        "jsonl": (".jsonl",),
        "markdown": (".md", ".markdown", ".rst", ".txt"),
    }[spec.kind]
    files = [
        item
        for item in sorted(path.rglob("*"))
        if item.is_file() and item.suffix.lower() in extensions
    ]
    if not files:
        raise FileNotFoundError(
            f"no {extensions} files found for source {spec.name!r} under {path}"
        )
    records: list[Record] = []
    for item in files:
        records.extend(normalizer(item, spec))
    return records

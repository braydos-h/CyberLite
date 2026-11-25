"""Machine-readable and human-readable dataset audit reports.

Reports deliberately contain identifiers, counts, hashes, and source metadata,
never restricted source text. A reader can verify a build without the corpus
being redistributed.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from cyberlite.data.cleaning import normalize_license
from cyberlite.data.schema import Record

LICENSE_GUIDANCE: dict[str, dict[str, Any]] = {
    "MITRE-ATTACK": {
        "permitted_uses": ["training", "research", "commercial-use"],
        "attribution_required": True,
        "redistribution": "Raw STIX is not redistributed; derived records remain subject to MITRE terms.",
        "restrictions": "Preserve MITRE copyright and attribution. Review current terms before publishing derived text.",
        "unresolved": ["Derived-text redistribution requires a terms review."],
    },
    "MITRE-CWE": {
        "permitted_uses": ["training", "research", "commercial-use"],
        "attribution_required": True,
        "redistribution": "Raw CWE XML is not redistributed; derived records preserve CWE identifiers.",
        "restrictions": "Preserve the MITRE copyright designation and CWE terms.",
        "unresolved": ["Derived-text redistribution requires a terms review."],
    },
    "Public-Domain": {
        "permitted_uses": ["training", "research", "commercial-use", "redistribution"],
        "attribution_required": False,
        "redistribution": "Generally permitted for U.S. Government works; NVD requests attribution.",
        "restrictions": "Attribute NIST NVD. Do not imply NIST endorsement.",
        "unresolved": [],
    },
    "CC-BY-SA-4.0": {
        "permitted_uses": ["training", "research"],
        "attribution_required": True,
        "redistribution": "Share-alike; redistribution of derived text must satisfy CC BY-SA 4.0.",
        "restrictions": "Attribute OWASP and the Cheat Sheet Series authors; indicate changes.",
        "unresolved": [
            "Whether a trained model or derived training corpus is a derivative work is unsettled.",
            "CyberLite does not redistribute OWASP text.",
        ],
    },
    "GPL-2.0-only": {
        "permitted_uses": ["training", "research"],
        "attribution_required": True,
        "redistribution": "Copyleft; redistribution of derived text may trigger GPL obligations.",
        "restrictions": "Retain notices; do not redistribute derived text without a license review.",
        "unresolved": ["Derived-corpus and model-output licensing is unsettled."],
    },
    "GPL-2.0-or-later": {
        "permitted_uses": ["training", "research"],
        "attribution_required": True,
        "redistribution": "Copyleft; redistribution of derived text may trigger GPL obligations.",
        "restrictions": "Retain notices; do not redistribute derived text without a license review.",
        "unresolved": ["Derived-corpus and model-output licensing is unsettled."],
    },
    "GPL-1.0-or-later": {
        "permitted_uses": ["training", "research"],
        "attribution_required": True,
        "redistribution": "Copyleft; redistribute only with the license text and notices.",
        "restrictions": "Review before redistributing derived text.",
        "unresolved": ["Derived-corpus licensing is unsettled."],
    },
    "GPL-3.0-or-later": {
        "permitted_uses": ["training", "research"],
        "attribution_required": True,
        "redistribution": "Copyleft; redistribution of derived text may trigger GPL obligations.",
        "restrictions": "Retain notices; review before redistributing derived text.",
        "unresolved": ["Derived-corpus and model-output licensing is unsettled."],
    },
    "IETF-Trust": {
        "permitted_uses": ["training", "research"],
        "attribution_required": True,
        "redistribution": "Subject to the IETF Trust legal provisions; retain copyright notices.",
        "restrictions": "Do not redistribute modified RFC text without reviewing BCP 78.",
        "unresolved": ["Derived-text redistribution requires a terms review."],
    },
    "OpenSSH": {
        "permitted_uses": ["training", "research"],
        "attribution_required": True,
        "redistribution": "BSD-style OpenSSH licence; retain the copyright and permission notice.",
        "restrictions": "Do not use the OpenSSH name to endorse derived material.",
        "unresolved": [],
    },
    "Linux-man-pages-copyleft": {
        "permitted_uses": ["training", "research"],
        "attribution_required": True,
        "redistribution": "Permission to copy and distribute verbatim or modified versions with the notice preserved.",
        "restrictions": "Preserve the copyright and permission notice; acknowledge authors.",
        "unresolved": [
            "Training use is not explicitly addressed; no derived text is redistributed."
        ],
    },
    "Linux-man-pages-1-para": {
        "permitted_uses": ["training", "research"],
        "attribution_required": True,
        "redistribution": "One-paragraph permission notice; preserve it with copies.",
        "restrictions": "Preserve the notice.",
        "unresolved": ["Training use is not explicitly addressed."],
    },
    "Mixed-SPDX": {
        "permitted_uses": ["training", "research"],
        "attribution_required": True,
        "redistribution": "Per-document SPDX licenses; see each record's license field.",
        "restrictions": "Do not assume a single license for the collection.",
        "unresolved": ["Documents without an explicit SPDX line are quarantined."],
    },
    "Synthetic": {
        "permitted_uses": ["training", "research", "redistribution"],
        "attribution_required": False,
        "redistribution": "Project-authored content; repository code is Apache-2.0.",
        "restrictions": "AI-assisted drafts are not manually reviewed unless the record says so.",
        "unresolved": ["No human quality review has been completed."],
    },
    "CC-BY-4.0": {
        "permitted_uses": ["training", "research", "redistribution"],
        "attribution_required": True,
        "redistribution": "Permitted with attribution.",
        "restrictions": "Attribute the source and indicate changes.",
        "unresolved": [],
    },
    "CC0-1.0": {
        "permitted_uses": ["training", "research", "commercial-use", "redistribution"],
        "attribution_required": False,
        "redistribution": "Dedicated to the public domain.",
        "restrictions": "None known.",
        "unresolved": [],
    },
    "Apache-2.0": {
        "permitted_uses": ["training", "research", "commercial-use", "redistribution"],
        "attribution_required": True,
        "redistribution": "Permitted with notices and license text.",
        "restrictions": "Retain notices; state changes.",
        "unresolved": [],
    },
    "MIT": {
        "permitted_uses": ["training", "research", "commercial-use", "redistribution"],
        "attribution_required": True,
        "redistribution": "Permitted with the copyright and permission notice.",
        "restrictions": "Retain the notice.",
        "unresolved": [],
    },
    "BSD-2-Clause": {
        "permitted_uses": ["training", "research", "commercial-use", "redistribution"],
        "attribution_required": True,
        "redistribution": "Permitted with the copyright and permission notice.",
        "restrictions": "Retain the notice; no endorsement.",
        "unresolved": [],
    },
    "BSD-3-Clause": {
        "permitted_uses": ["training", "research", "commercial-use", "redistribution"],
        "attribution_required": True,
        "redistribution": "Permitted with the copyright and permission notice.",
        "restrictions": "Retain the notice; no endorsement.",
        "unresolved": [],
    },
    "BSD-4-Clause-UC": {
        "permitted_uses": ["training", "research"],
        "attribution_required": True,
        "redistribution": "Historical advertising clause; review before redistribution.",
        "restrictions": "Retain the notice.",
        "unresolved": ["Redistribution obligations require review."],
    },
    "See-source": {
        "permitted_uses": [],
        "attribution_required": True,
        "redistribution": "Quarantined: no explicit license.",
        "restrictions": "Do not ingest until an explicit license is recorded.",
        "unresolved": ["Source license is unknown."],
    },
}

DEFAULT_GUIDANCE = {
    "permitted_uses": [],
    "attribution_required": True,
    "redistribution": "Unknown; quarantine and review before use.",
    "restrictions": "Do not redistribute without a verified license.",
    "unresolved": ["License is not in the reviewed guidance map."],
}


def _license_guidance(license_id: str) -> dict[str, Any]:
    return LICENSE_GUIDANCE.get(normalize_license(license_id), DEFAULT_GUIDANCE)


def build_license_report(
    *,
    registry_sources: Iterable[Any],
    records: Iterable[Record],
    source_records: dict[str, int] | None = None,
    allowed_licenses: Iterable[str] | None = None,
) -> dict[str, Any]:
    source_records = source_records or {}
    allowed = {normalize_license(item) for item in (allowed_licenses or [])}
    licenses: dict[str, dict[str, Any]] = {}
    for record in records:
        license_id = normalize_license(record.license)
        entry = licenses.setdefault(
            license_id,
            {
                "identifier": license_id,
                "records": 0,
                "sources": set(),
                "allowed_by_config": license_id in allowed if allowed else None,
                **_license_guidance(license_id),
            },
        )
        entry["records"] += 1
        entry["sources"].add(record.source)
    for source in registry_sources:
        license_id = normalize_license(str(getattr(source, "license", "")))
        if not license_id:
            continue
        entry = licenses.setdefault(
            license_id,
            {
                "identifier": license_id,
                "records": 0,
                "sources": set(),
                "allowed_by_config": license_id in allowed if allowed else None,
                **_license_guidance(license_id),
            },
        )
        if not entry["sources"]:
            entry["sources"].add(getattr(source, "name", "unknown"))
        if getattr(source, "license_url", ""):
            entry["license_url"] = source.license_url
        if getattr(source, "terms_url", ""):
            entry["terms_url"] = source.terms_url
        if getattr(source, "redistribution_notes", ""):
            entry["source_redistribution_notes"] = source.redistribution_notes
        if getattr(source, "unresolved", None):
            entry["unresolved"] = sorted(set(entry.get("unresolved", [])) | set(source.unresolved))
        entry.setdefault("source_records", {})
        entry["source_records"][str(getattr(source, "name", "unknown"))] = source_records.get(
            str(getattr(source, "name", "")), 0
        )
    serializable: list[dict[str, Any]] = []
    for _license_id, entry in sorted(licenses.items()):
        entry = dict(entry)
        entry["sources"] = sorted(entry["sources"])
        serializable.append(entry)
    unknown = [entry["identifier"] for entry in serializable if not entry.get("permitted_uses")]
    unresolved_questions = [
        {"license": entry["identifier"], "questions": entry.get("unresolved", [])}
        for entry in serializable
        if entry.get("unresolved")
    ]
    return {
        "report": "source-license",
        "schema_version": 1,
        "disclaimer": (
            "This report is a research aid, not legal advice. Public accessibility "
            "does not imply permission for unrestricted use. Verify upstream terms "
            "before redistributing derived text or a trained model."
        ),
        "licenses": serializable,
        "unresolved_or_quarantined": unknown,
        "unresolved_questions": unresolved_questions,
        "redistribution_policy": (
            "CyberLite commits manifests and reports only. Raw downloads, derived "
            "splits, and restricted benchmark items remain outside Git."
        ),
    }


def render_license_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Source and license report",
        "",
        report["disclaimer"],
        "",
        "| License | Records | Sources | Attribution | Permitted uses | Redistribution |",
        "|---|---:|---|---|---|---|",
    ]
    for entry in report["licenses"]:
        lines.append(
            "| {id} | {records} | {sources} | {attr} | {uses} | {redistribution} |".format(
                id=entry["identifier"],
                records=entry.get("records", 0),
                sources=", ".join(entry.get("sources", [])) or "—",
                attr="required" if entry.get("attribution_required") else "not required",
                uses=", ".join(entry.get("permitted_uses", [])) or "**unresolved**",
                redistribution=entry.get("redistribution", "").replace("|", "/"),
            )
        )
    lines.extend(
        [
            "",
            "## Unresolved licensing questions",
            "",
            "The following identifiers have no positively reviewed permitted-use set and "
            "must not be treated as cleared for redistribution:",
            "",
        ]
    )
    unresolved = report.get("unresolved_or_quarantined") or []
    if unresolved:
        lines.extend(f"- Quarantined or unclear permitted use: `{item}`" for item in unresolved)
    questions = report.get("unresolved_questions") or []
    if questions:
        lines.append("")
        for item in questions:
            lines.append(f"- `{item['license']}`:")
            lines.extend(f"  - {question}" for question in item["questions"])
    if not unresolved and not questions:
        lines.append("- None recorded.")
    lines.extend(
        [
            "",
            "## Redistribution policy",
            "",
            report["redistribution_policy"],
            "",
            "Restricted benchmark content (for example SecEval) is evaluation-only and is "
            "never committed or ingested. See `data/evaluation/README.md`.",
            "",
        ]
    )
    return "\n".join(lines)


def write_json_and_markdown(
    payload: dict[str, Any], directory: str | Path, stem: str, *, markdown: str | None = None
) -> tuple[Path, Path | None]:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / f"{stem}.json"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path = None
    if markdown is not None:
        markdown_path = directory / f"{stem}.md"
        markdown_path.write_text(markdown, encoding="utf-8")
    return json_path, markdown_path


def render_manifest_readme(manifest: dict[str, Any], reports: dict[str, Any]) -> str:
    """Render a committed, text-free README for a frozen dataset build."""

    def table(rows: list[tuple[str, Any]]) -> list[str]:
        return [f"| {key} | {value} |" for key, value in rows]

    source_rows = [
        (
            entry.get("name", "unknown"),
            f"{entry.get('records', 0)}",
            entry.get("license", ""),
            entry.get("revision", "") or "—",
        )
        for entry in manifest.get("sources", [])
    ]
    lines = [
        f"# {manifest.get('dataset_name', 'CyberLite dataset')} — frozen manifest",
        "",
        "Generated by the CyberLite preparation pipeline. This directory contains "
        "counts, hashes, and source metadata only; it contains no source text.",
        "",
        "## Build",
        "",
        "| Field | Value |",
        "|---|---|",
    ]
    lines.extend(
        table(
            [
                ("Dataset version", f"`{manifest.get('dataset_version', '')}`"),
                ("Pipeline version", manifest.get("pipeline_version", "")),
                ("Dataset schema", manifest.get("dataset_schema", "")),
                ("Configuration SHA-256", f"`{manifest.get('config_sha256', '')}`"),
                ("Source registry SHA-256", f"`{manifest.get('source_registry_sha256', '')}`"),
                ("Processing seed", manifest.get("seed", "")),
                ("Input records", manifest.get("input_records", "")),
                ("Accepted records", manifest.get("output_records", "")),
                ("Rejected / quarantined", len(manifest.get("rejections", []))),
            ]
        )
    )
    lines.extend(
        [
            "",
            "## Sources (normalized records before global deduplication)",
            "",
            "| Source | Records | License | Revision |",
            "|---|---:|---|---|",
        ]
    )
    lines.extend(
        f"| {name} | {records} | {license} | {revision} |"
        for name, records, license, revision in source_rows
    )
    lines.extend(
        ["", "## Splits", "", "| Split | Records | Bytes | SHA-256 |", "|---|---:|---:|---|"]
    )
    for name in ("train", "validation", "test", "quarantine"):
        item = manifest.get("files", {}).get(name, {})
        lines.append(
            f"| {name} | {item.get('records', 0)} | {item.get('bytes', '—')} | "
            f"`{item.get('sha256', '')}` |"
        )
    lines.extend(["", "## Composition", "", "| Source | Records |", "|---|---:|"])
    for source, count in manifest.get("source_counts", {}).items():
        lines.append(f"| {source} | {count} |")
    lines.extend(["", "| Task | Records |", "|---|---:|"])
    for task, count in manifest.get("task_counts", {}).items():
        lines.append(f"| {task} | {count} |")
    lines.extend(["", "| License | Records |", "|---|---:|"])
    for license_id, count in manifest.get("license_counts", {}).items():
        lines.append(f"| {license_id} | {count} |")
    quality = reports.get("quality", {})
    contamination = reports.get("contamination", {})
    lines.extend(
        [
            "",
            "## Quality and leakage controls",
            "",
            "| Check | Result |",
            "|---|---|",
            f"| Secret redaction | {'enabled' if manifest.get('options', {}).get('redact') else 'disabled'} |",
            f"| Dedup threshold | {manifest.get('options', {}).get('dedup_threshold')} SimHash bits |",
            f"| Quality rejections | {quality.get('quality_rejections', 0)} |",
            f"| Contamination n-gram | {contamination.get('ngram', '')} |",
            f"| Contamination threshold | {contamination.get('threshold', '')} |",
            f"| Evaluation n-grams indexed | {contamination.get('total_indexed_ngrams', 0)} |",
            f"| Contamination removals | {contamination.get('removed', 0)} |",
            f"| Group split violations | {len(manifest.get('group_split_violations', []))} |",
            f"| Cross-split leakage findings | {len(manifest.get('cross_split_leakage', []))} |",
        ]
    )
    lines.extend(
        [
            "",
            "Per-benchmark contamination details are in `contamination_report.json`; "
            "licenses and unresolved questions are in `license_report.json`; audit "
            "metrics and the manual-review plan are in `quality_report.json`.",
            "",
            "## Audit",
            "",
            "| Audit artifact | Value |",
            "|---|---|",
            f"| Audit report | {manifest.get('audit', {}).get('report', 'not run')} |",
            f"| Review sample | {manifest.get('audit', {}).get('review_sample_size', 0)} records |",
            f"| Manual review complete | {manifest.get('audit', {}).get('manual_review_completed', False)} |",
            f"| Verified contamination removals | {manifest.get('audit', {}).get('verified_contamination_removals', 'not verified')} |",
            "",
            "## Manual review",
            "",
            "**Not completed.** The audit script can generate a deterministic stratified "
            "sample and a review template, but no human review has been recorded for this "
            "build. Do not describe these records as manually verified.",
            "",
            "## Reproduction",
            "",
            "```bash",
            manifest.get("reproduction", {}).get("command", ""),
            "```",
            "",
            "Pinned inputs are identified by URL/revision and SHA-256 in `manifest.json`. "
            "An offline rebuild uses the same cache and `--offline`; see "
            "`docs/reproducibility.md`.",
            "",
            "## Limitations",
            "",
            "- The 13-gram screen catches verbatim and near-verbatim overlap only. "
            "Paraphrase, translation, and conceptual contamination are not detected.",
            "- Manual review is pending; quality gates are heuristics, not ground truth.",
            "- Upstream documentation can be outdated or incorrect. Records preserve "
            "upstream claims without independently verifying them.",
            "",
        ]
    )
    return "\n".join(lines)

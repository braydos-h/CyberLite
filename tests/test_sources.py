from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
from cyberlite.data.sources import SourceRegistry, normalize_source


@pytest.fixture
def registry(repo_root: Path) -> SourceRegistry:
    return SourceRegistry.load(repo_root / "data" / "sources.yaml")


def test_registry_requires_license(repo_root: Path, tmp_path: Path) -> None:
    path = tmp_path / "sources.yaml"
    path.write_text(
        "schema_version: 1\nsources:\n  bad:\n    title: Bad\n    kind: jsonl\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="license"):
        SourceRegistry.load(path)


def test_registry_unknown_source(registry: SourceRegistry) -> None:
    with pytest.raises(KeyError):
        registry.get("does-not-exist")


def test_stix_attack_normalization(tmp_path: Path, registry: SourceRegistry) -> None:
    bundle = {
        "type": "bundle",
        "objects": [
            {
                "type": "attack-pattern",
                "name": "Command and Scripting Interpreter",
                "description": (
                    "Adversaries may abuse command and script interpreters to execute "
                    "commands, scripts, or binaries. Detection should correlate parent "
                    "process, user context, and command-line content."
                ),
                "external_references": [{"source_name": "mitre-attack", "external_id": "T1059"}],
                "x_mitre_platforms": ["Linux", "Windows"],
                "kill_chain_phases": [{"phase_name": "execution"}],
                "x_mitre_detection": (
                    "Monitor process creation and correlate unusual shell invocations with "
                    "service accounts and network activity."
                ),
            }
        ],
    }
    path = tmp_path / "attack.json"
    path.write_text(json.dumps(bundle), encoding="utf-8")
    records = normalize_source(path, registry.get("mitre_attack"))
    assert len(records) == 1
    assert records[0].task == "attack-technique"
    assert records[0].license == "MITRE-ATTACK"
    assert "T1059" in records[0].prompt
    assert records[0].metadata["attack_id"] == "T1059"


def test_cwe_zip_normalization(tmp_path: Path, registry: SourceRegistry) -> None:
    xml = """<?xml version="1.0"?>
    <Weaknesses>
      <Weakness ID="79" Name="Improper Neutralization of Input During Web Page Generation">
        <Description>User-controlled input is placed into HTML output without encoding.</Description>
        <Extended_Description>Reflected and stored cross-site scripting can execute script in a victim browser.</Extended_Description>
        <Potential_Mitigations><Mitigation>Use context-aware output encoding.</Mitigation></Potential_Mitigations>
        <Detection_Methods><Method>Inspect rendering sinks and run authorized tests.</Method></Detection_Methods>
      </Weakness>
    </Weaknesses>"""
    xml_path = tmp_path / "cwe.xml"
    xml_path.write_text(xml, encoding="utf-8")
    archive = tmp_path / "cwe.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.write(xml_path, arcname="cwe.xml")
    records = normalize_source(archive, registry.get("mitre_cwe"))
    assert len(records) == 1
    assert records[0].metadata["cwe_id"] == "CWE-79"
    assert "output encoding" in records[0].response


def test_nvd_normalization(tmp_path: Path, registry: SourceRegistry) -> None:
    page = {
        "vulnerabilities": [
            {
                "cve": {
                    "id": "CVE-2021-0001",
                    "descriptions": [
                        {
                            "lang": "en",
                            "value": (
                                "A synthetic vulnerability description long enough to pass "
                                "the minimum response length. It affects a network service "
                                "and permits denial of service."
                            ),
                        }
                    ],
                    "metrics": {
                        "cvssMetricV31": [
                            {
                                "cvssData": {
                                    "baseSeverity": "HIGH",
                                    "baseScore": 7.5,
                                    "vectorString": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H",
                                }
                            }
                        ]
                    },
                    "weaknesses": [{"description": [{"lang": "en", "value": "CWE-400"}]}],
                    "references": [{"url": "https://example.invalid/advisory"}],
                }
            }
        ]
    }
    path = tmp_path / "nvd.json"
    path.write_text(json.dumps(page), encoding="utf-8")
    records = normalize_source(path, registry.get("nist_nvd"))
    assert len(records) == 1
    assert records[0].metadata["cve_id"] == "CVE-2021-0001"
    assert "CVSS 7.5" in records[0].response
    assert "CWE-400" in records[0].response


def test_markdown_directory_normalization(tmp_path: Path, registry: SourceRegistry) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ssh.md").write_text(
        "# SSH hardening\n\n"
        + "Disable password authentication and use short-lived certificates. " * 10
        + "\n\n## Logging\n\n"
        + "Forward authentication events to a central collector and alert on repeated failures. "
        * 10,
        encoding="utf-8",
    )
    spec = registry.get("owasp_cheatsheets")
    records = normalize_source(docs, spec)
    assert records
    assert all(record.source == "owasp_cheatsheets" for record in records)
    assert all(record.license == "CC-BY-SA-4.0" for record in records)


def test_manpage_without_spdx_is_quarantined(tmp_path: Path, registry: SourceRegistry) -> None:
    page = tmp_path / "unknown.5"
    page.write_text(
        ".TH unknown 5\n.SH DESCRIPTION\n"
        + "An operational description without an explicit license. " * 8
        + "\n",
        encoding="utf-8",
    )
    from dataclasses import replace

    spec = replace(
        registry.get("linux_man_pages"),
        options={"min_section_chars": 20},
    )
    from cyberlite.data.sources import normalize_source_outcome

    outcome = normalize_source_outcome(page, spec)
    assert outcome.records == []

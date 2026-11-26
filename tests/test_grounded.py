from __future__ import annotations

from cyberlite.data.grounded import generate_grounded
from cyberlite.data.schema import Record


def _nvd_record() -> Record:
    return Record(
        id="nist_nvd-test-8",
        source="nist_nvd",
        license="Public-Domain",
        task="vulnerability",
        prompt="summarise",
        response=(
            "A web application allows an unauthenticated attacker to upload a file "
            "that is later executed by the server. The vendor has released a patch."
        ),
        url="https://nvd.nist.gov/vuln/detail/CVE-2024-0001",
        metadata={
            "cve_id": "CVE-2024-0001",
            "group": "nist_nvd:CVE-2024-0001",
            "weaknesses": ["CWE-434"],
            "cvss": [
                {
                    "vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
                    "score": 9.8,
                    "severity": "CRITICAL",
                    "version": "3.1",
                }
            ],
            "cpe_configurations": ["cpe:2.3:a:example:uploader:*:*:*:*:*:*:*:*"],
            "source_version": "nvd-api-2.0",
        },
    )


def test_nvd_views_are_grounded_and_caveated() -> None:
    result = generate_grounded([_nvd_record()], max_per_record=4)
    assert result.stats["generated_records"] >= 3
    tasks = {record.task for record in result.records}
    assert "vulnerability" in tasks
    assert "uncertainty" in tasks
    assert "structured-extraction" in tasks
    triage = next(record for record in result.records if record.metadata["variant"] == "nvd-triage")
    assert "9.8" in triage.response
    assert "does not establish" in triage.response
    assert triage.metadata["origin"] == "source-derived"
    assert triage.metadata["group"] == "nist_nvd:CVE-2024-0001"
    assert triage.license == "Public-Domain"


def test_grounded_json_extraction_is_valid_json() -> None:
    result = generate_grounded([_nvd_record()], max_per_record=4)
    extraction = next(
        record for record in result.records if record.metadata["variant"] == "nvd-extraction"
    )
    payload = __import__("json").loads(extraction.response)
    assert payload["cve_id"] == "CVE-2024-0001"
    assert payload["severity"] == "critical"
    assert payload["base_score"] == 9.8
    assert payload["weaknesses"] == ["CWE-434"]


def test_unsupported_source_is_skipped() -> None:
    record = Record(
        id="project-test",
        source="project_examples",
        license="Synthetic",
        task="incident-response",
        messages=[
            {"role": "user", "content": "What now?"},
            {"role": "assistant", "content": "Preserve evidence first."},
        ],
        metadata={"group": "project:test"},
    )
    result = generate_grounded([record])
    assert result.records == []

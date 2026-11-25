from __future__ import annotations

import json
from pathlib import Path

import pytest
from cyberlite.data.synthesis import (
    PackValidationError,
    generate_fact_records,
    load_pack,
    synthesize,
)


def _fact(identifier: str = "lnx-test-001") -> dict:
    return {
        "id": identifier,
        "subtopic": "permissions",
        "difficulty": "intermediate",
        "title": "Directory execute permission controls traversal",
        "fact": (
            "On Linux, the execute bit on a directory grants the ability to traverse it "
            "and to access entries by name. Read permission alone lists names but does "
            "not allow opening a listed file."
        ),
        "details": [
            "Read on a directory permits listing names.",
            "Execute permits lookup and traversal.",
        ],
        "pitfalls": ["Assuming read permission allows opening a known filename."],
        "code": [
            {
                "language": "python",
                "vulnerable": "def run(name):\n    return eval(name)\n",
                "secure": "import ast\n\ndef parse(name):\n    value = ast.literal_eval(name)\n    if not validate(value):\n        raise ValueError('invalid')\n    return sanitize(value)\n",
                "issue": "Evaluating untrusted input as Python code allows arbitrary execution.",
            }
        ],
        "commands": [
            {
                "language": "bash",
                "code": "namei -l /var/log/app",
                "purpose": "Show effective permissions on each path component.",
            }
        ],
        "logs": [
            {
                "context": "Linux auditd",
                "text": "type=SYSCALL msg=audit(1700000000.123:42): syscall=257 success=no exit=-13",
                "reading": "The failure is a permission denial, but the line does not identify the component.",
            }
        ],
        "mcqs": [
            {
                "question": "Which directory permission allows opening a file by name?",
                "options": ["Read", "Execute", "Write", "Read and write"],
                "answer": [1],
                "rationale": "Execute controls traversal and name lookup.",
            }
        ],
        "misconceptions": [
            {
                "claim": "Mode 0444 on a directory lets a user open a known file.",
                "correction": "Without execute, path traversal fails with EACCES for non-root users.",
            }
        ],
        "references": [
            {
                "title": "path_resolution(7)",
                "publisher": "Linux man-pages project",
                "url": "https://man7.org/linux/man-pages/man7/path_resolution.7.html",
                "license": "Linux-man-pages-copyleft",
            }
        ],
        "tags": ["permissions"],
    }


def _pack(tmp_path: Path, facts=None) -> Path:
    payload = {
        "schema_version": 1,
        "domain": "fundamentals-linux-networking",
        "display_name": "Test",
        "author": "worker:test",
        "facts": facts or [_fact()],
    }
    path = tmp_path / "c1-test.json"
    path.write_text(json.dumps(payload))
    return path


def test_load_pack_and_generate(tmp_path: Path) -> None:
    pack = load_pack(_pack(tmp_path))
    assert len(pack.facts) == 1
    records, preferences = generate_fact_records(pack.facts[0])
    assert len(records) >= 6
    assert len({record.id for record in records}) == len(records)
    assert all(record.metadata["group"] == pack.facts[0].group for record in records)
    assert all(record.metadata["synthetic"] is True for record in records)
    assert any(record.kind == "fim" for record in records)
    for record in records:
        if record.kind == "fim":
            assert record.middle
            assert record.prefix is not None
    assert preferences
    assert preferences[0]["rejected"] != preferences[0]["chosen"]


def test_fim_reconstructs_secure_code(tmp_path: Path) -> None:
    fact = _fact()
    fact["code"] = [
        {
            "language": "python",
            "vulnerable": "def run(name):\n    return eval(name)\n",
            "secure": "import ast\n\ndef parse(name):\n    value = ast.literal_eval(name)\n    if not validate(value):\n        raise ValueError('invalid')\n    return sanitize(value)\n",
            "issue": "Evaluating untrusted input as Python code allows arbitrary execution.",
        }
    ]
    pack = load_pack(_pack(tmp_path, [fact]))
    records, _ = generate_fact_records(pack.facts[0])
    fim = [record for record in records if record.kind == "fim"]
    assert fim
    joined = fim[0].prefix + fim[0].middle + fim[0].suffix
    assert "literal_eval" in joined


def test_duplicate_fact_id_rejected(tmp_path: Path) -> None:
    path = _pack(tmp_path, [_fact(), _fact()])
    with pytest.raises(PackValidationError):
        load_pack(path)


def test_missing_reference_rejected(tmp_path: Path) -> None:
    fact = _fact()
    fact["references"] = []
    with pytest.raises(PackValidationError):
        load_pack(_pack(tmp_path, [fact]))


def test_synthesize_collects_stats(tmp_path: Path) -> None:
    _pack(tmp_path)
    result = synthesize(tmp_path)
    assert result.stats["facts"] == 1
    assert result.stats["records"] == len(result.records)
    assert result.stats["packs"] == 1
    assert result.records

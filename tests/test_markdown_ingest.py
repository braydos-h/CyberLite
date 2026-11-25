from __future__ import annotations

from pathlib import Path

from cyberlite.data.markdown import segment_markdown
from cyberlite.data.sources import SourceRegistry, normalize_source


def test_heading_segmentation_preserves_code_and_removes_nav(
    tmp_path: Path, repo_root: Path
) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text(
        """# Secure configuration

[Home](../index.md) | [Next](next.md)

## SSH

Use key-based authentication and restrict source addresses.Use key-based authentication and restrict source addresses.Use key-based authentication and restrict source addresses.Use key-based authentication and restrict source addresses.

```bash
# This is a code comment, not a heading
PermitRootLogin no
AllowUsers deploy
```

[Back to top](#top)

## Logging

Forward authentication events to a central collector and alert on repeated failures.Forward authentication events to a central collector and alert on repeated failures.Forward authentication events to a central collector and alert on repeated failures.Forward authentication events to a central collector and alert on repeated failures.
"""
        * 3,
        encoding="utf-8",
    )
    from dataclasses import replace

    spec = replace(
        SourceRegistry.load(repo_root / "data" / "sources.yaml").get("owasp_cheatsheets"),
        options={"min_section_chars": 50},
    )
    records = normalize_source(docs, spec)
    assert records
    assert all(record.license == "CC-BY-SA-4.0" for record in records)
    ssh = [record for record in records if "SSH" in record.metadata["heading"]]
    assert ssh
    assert "```bash" in ssh[0].response
    assert "PermitRootLogin no" in ssh[0].response
    assert "[Back to top]" not in ssh[0].response
    assert "code comment, not a heading" in ssh[0].response
    assert ssh[0].metadata["code_blocks"] >= 1
    # Sections from one document share a leakage-control group.
    assert len({record.metadata["group"] for record in records}) == 1


def test_directory_ingestion_is_recursive_and_deterministic(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    (root / "nested").mkdir(parents=True)
    body = "A precise defensive explanation with verification steps and conditions. " * 8
    (root / "a.md").write_text(f"# A\n\n{body}", encoding="utf-8")
    (root / "nested" / "b.md").write_text(f"# B\n\n{body}", encoding="utf-8")
    from dataclasses import replace

    from cyberlite.data.sources import SourceRegistry

    spec = SourceRegistry.load(Path(__file__).resolve().parents[1] / "data" / "sources.yaml").get(
        "owasp_cheatsheets"
    )
    spec = replace(spec, options={"min_section_chars": 100})
    first = normalize_source(root, spec)
    second = normalize_source(root, spec)
    assert {record.metadata["document"] for record in first} == {"a.md", "b.md"}
    assert [record.id for record in first] == [record.id for record in second]


def test_long_section_splits_outside_code_fences() -> None:
    code = "```python\n" + "\n".join(f"print({index})" for index in range(100)) + "\n```"
    paragraph = "A long paragraph about defensive verification. " * 30
    text = f"# Topic\n\n{paragraph}\n\n{code}\n\n{paragraph}"
    sections = segment_markdown(text, min_section_chars=50, max_section_chars=300)
    assert len(sections) > 1
    combined = "\n".join(section.body for section in sections)
    assert combined.count("```") % 2 == 0
    assert "print(99)" in combined

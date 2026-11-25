from __future__ import annotations

from cyberlite.data.cleaning import (
    Deduplicator,
    find_secrets,
    hamming_distance,
    license_allowed,
    normalize_license,
    normalize_text,
    redact_secrets,
    simhash64,
    strip_html,
)


def test_normalize_preserves_code_indentation() -> None:
    text = "def f():\r\n    return 1   \r\n\r\n\r\n"
    normalized = normalize_text(text)
    assert normalized == "def f():\n    return 1"


def test_strip_html_removes_scripts_and_entities() -> None:
    text = "<p>Use &lt;code&gt; safely</p><script>alert(1)</script>"
    assert strip_html(text) == "Use <code> safely"


def test_find_and_redact_aws_key() -> None:
    text = "key = AKIAIOSFODNN7EXAMPLE and nothing else"
    findings = find_secrets(text)
    assert any(finding.kind == "aws_access_key" for finding in findings)
    redacted, _ = redact_secrets(text)
    assert "AKIA" not in redacted
    assert "[REDACTED_SECRET]" in redacted


def test_private_key_block_detected() -> None:
    text = "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBg\n-----END PRIVATE KEY-----"
    assert any(finding.kind == "private_key" for finding in find_secrets(text))


def test_sha_like_hash_is_not_automatically_a_secret() -> None:
    text = "sha256: " + "a" * 64
    assert find_secrets(text) == []


def test_simhash_stability_and_distance() -> None:
    a = simhash64("the quick brown fox jumps over the lazy dog")
    b = simhash64("the quick brown fox jumps over the lazy dog")
    c = simhash64("a completely different sentence about network security")
    assert a == b
    assert hamming_distance(a, c) > 3


def test_deduplicator_detects_exact_and_near_duplicates() -> None:
    dedup = Deduplicator(threshold=12)
    base = "Detect failed SSH logins by counting authentication failures per source address."
    assert dedup.is_duplicate(base) == (False, "unique")
    assert dedup.is_duplicate(base) == (True, "exact")
    near = base.replace("address", "IP address")
    duplicate, reason = dedup.is_duplicate(near)
    assert duplicate is True
    assert reason in {"exact", "near:1"} or reason.startswith("near")
    assert dedup.stats["kept"] == 1


def test_license_normalization_and_allowlist() -> None:
    assert normalize_license("apache 2.0") == "Apache-2.0"
    assert license_allowed("MIT", ["Apache-2.0", "MIT"])
    assert not license_allowed("Proprietary", ["Apache-2.0"])

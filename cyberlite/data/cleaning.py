"""Text cleaning, secret detection, deduplication, and license checks."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

# Deliberately conservative patterns. The goal is to stop obvious credentials
# from entering a training corpus, not to be a complete DLP product.
_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,255}\b")),
    ("github_pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{60,255}\b")),
    ("openai_key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}\b")),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    (
        "connection_string_password",
        re.compile(r"(?i)\b(?:password|passwd|pwd)\s*=\s*[^\s;'\"]{6,}"),
    ),
    (
        "generic_api_key",
        re.compile(
            r"(?i)\b(?:api[_-]?key|secret[_-]?key|access[_-]?token)\s*[:=]\s*['\"]?"
            r"[A-Za-z0-9/+_-]{20,}['\"]?"
        ),
    ),
)

_BASE64_CANDIDATE = re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b")
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

_TAG_RE = re.compile(r"<[^>]+>")
_MULTISPACE_RE = re.compile(r"[ \t\f\v]+")
_BLANKLINES_RE = re.compile(r"\n{3,}")


@dataclass(frozen=True)
class SecretFinding:
    kind: str
    start: int
    end: int
    preview: str


def normalize_text(text: str, *, max_chars: int = 200_000) -> str:
    """Normalize whitespace and Unicode without changing technical meaning."""

    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\x00", " ").replace("\r\n", "\n").replace("\r", "\n")
    # Preserve interior and leading whitespace: code, YARA, and Sigma rules
    # depend on indentation. Only trailing whitespace and blank-line runs are
    # normalized.
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = _BLANKLINES_RE.sub("\n\n", text).strip()
    return text[:max_chars]


def strip_html(text: str) -> str:
    """Remove tags and unescape common entities for HTML-derived sources."""

    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text)
    text = _TAG_RE.sub(" ", text)
    replacements = {
        "&nbsp;": " ",
        "&amp;": "&",
        "&lt;": "<",
        "&gt;": ">",
        "&quot;": '"',
        "&#39;": "'",
        "&apos;": "'",
    }
    for entity, value in replacements.items():
        text = text.replace(entity, value)
    return normalize_text(text)


def _shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    frequencies: dict[str, int] = {}
    for char in value:
        frequencies[char] = frequencies.get(char, 0) + 1
    import math

    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in frequencies.values())


def find_secrets(text: str) -> list[SecretFinding]:
    """Return detected credential-like spans.

    High-entropy base64 strings are only flagged when they appear near a
    credential keyword, which keeps hashes and encoded test vectors usable.
    """

    findings: list[SecretFinding] = []
    for kind, pattern in _SECRET_PATTERNS:
        for match in pattern.finditer(text):
            preview = text[match.start() : match.start() + 12]
            findings.append(SecretFinding(kind, match.start(), match.end(), preview))
    for match in _BASE64_CANDIDATE.finditer(text):
        candidate = match.group(0)
        context = text[max(0, match.start() - 40) : match.start()].lower()
        if _shannon_entropy(candidate) >= 4.5 and any(
            keyword in context for keyword in ("key", "secret", "token", "password", "auth")
        ):
            findings.append(
                SecretFinding("high_entropy_blob", match.start(), match.end(), candidate[:12])
            )
    findings.sort(key=lambda finding: finding.start)
    return findings


def redact_secrets(
    text: str, replacement: str = "[REDACTED_SECRET]"
) -> tuple[str, list[SecretFinding]]:
    """Replace detected secrets and return the redacted text and findings."""

    findings = find_secrets(text)
    if not findings:
        return text, []
    pieces: list[str] = []
    cursor = 0
    for finding in findings:
        pieces.append(text[cursor : finding.start])
        pieces.append(replacement)
        cursor = finding.end
    pieces.append(text[cursor:])
    return "".join(pieces), findings


def contains_pii_like(text: str) -> bool:
    """Best-effort email presence check used for optional review queues."""

    return bool(_EMAIL.search(text))


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]{2,}", text.lower())


def simhash64(text: str) -> int:
    """Compute a 64-bit SimHash over normalized word tokens."""

    tokens = _tokens(text)
    if not tokens:
        return 0
    vector = [0] * 64
    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        for bit in range(64):
            vector[bit] += 1 if (value >> bit) & 1 else -1
    result = 0
    for bit, weight in enumerate(vector):
        if weight > 0:
            result |= 1 << bit
    return result


def hamming_distance(left: int, right: int) -> int:
    return (left ^ right).bit_count()


class Deduplicator:
    """Exact-hash plus banded SimHash near-duplicate detection.

    Four 16-bit bands make candidate lookup practical on corpora with hundreds
    of thousands of records. The default threshold of 3 bits is conservative:
    submissions should be near-identical before one is dropped.
    """

    def __init__(self, *, threshold: int = 3) -> None:
        if not 0 <= threshold <= 16:
            raise ValueError("threshold must be between 0 and 16")
        self.threshold = threshold
        self._exact: set[str] = set()
        self._bands: dict[tuple[int, int], list[tuple[int, int]]] = {}
        self.exact_duplicates = 0
        self.near_duplicates = 0
        self.kept = 0

    @staticmethod
    def _exact_key(text: str) -> str:
        normalized = " ".join(_tokens(text))
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def is_duplicate(self, text: str) -> tuple[bool, str]:
        """Return ``(duplicate, reason)`` and register the text if new."""

        exact_key = self._exact_key(text)
        if exact_key in self._exact:
            self.exact_duplicates += 1
            return True, "exact"
        if self.threshold == 0:
            self._exact.add(exact_key)
            self.kept += 1
            return False, "unique"
        fingerprint = simhash64(text)
        for band in range(4):
            key = (band, (fingerprint >> (band * 16)) & 0xFFFF)
            for other, other_fingerprint in self._bands.get(key, []):
                if hamming_distance(fingerprint, other_fingerprint) <= self.threshold:
                    self.near_duplicates += 1
                    return True, f"near:{other}"
        self._exact.add(exact_key)
        for band in range(4):
            key = (band, (fingerprint >> (band * 16)) & 0xFFFF)
            self._bands.setdefault(key, []).append((len(self._exact), fingerprint))
        self.kept += 1
        return False, "unique"

    @property
    def stats(self) -> dict[str, int]:
        return {
            "kept": self.kept,
            "exact_duplicates": self.exact_duplicates,
            "near_duplicates": self.near_duplicates,
        }


def normalize_license(value: str) -> str:
    aliases = {
        "apache 2.0": "Apache-2.0",
        "apache-2.0": "Apache-2.0",
        "apache2": "Apache-2.0",
        "mit": "MIT",
        "cc0": "CC0-1.0",
        "cc-by-4.0": "CC-BY-4.0",
        "cc by 4.0": "CC-BY-4.0",
        "cc-by-sa-4.0": "CC-BY-SA-4.0",
        "public domain": "Public-Domain",
        "public-domain": "Public-Domain",
        "synthetic": "Synthetic",
        "mitre-attack": "MITRE-ATTACK",
        "mitre-cwe": "MITRE-CWE",
        "gpl-2.0": "GPL-2.0-only",
        "gpl-2.0-only": "GPL-2.0-only",
        "gpl-2.0-or-later": "GPL-2.0-or-later",
        "ietf": "IETF-Trust",
        "ietf-trust": "IETF-Trust",
    }
    cleaned = value.strip()
    return aliases.get(cleaned.lower(), cleaned)


def license_allowed(license_id: str, allowed: Iterable[str]) -> bool:
    normalized = normalize_license(license_id)
    return normalized in {normalize_license(item) for item in allowed}

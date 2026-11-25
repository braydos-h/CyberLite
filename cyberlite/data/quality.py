"""Dataset quality gates and Qwen sequence-length reporting.

The gates are intentionally conservative and explainable: each rejection carries
a stable reason code so the audit report can distinguish, say, boilerplate from
a credential leak. Token counting uses the real Qwen tokenizer when it is
available locally and labels a documented character-based estimate otherwise.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from cyberlite.data.cleaning import find_secrets
from cyberlite.data.config import QualityThresholds
from cyberlite.data.markdown import _is_navigation_line
from cyberlite.data.schema import Record

_URL_RE = re.compile(r"https?://\S+")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_ORGANIZATIONAL_CONTACTS = {"nvd@nist.gov", "cve@mitre.org"}
_ORGANIZATIONAL_LOCAL_RE = re.compile(
    r"^(?:security|secure|psirt|secalert|cna|audit|cert|sirt|disclosures|"
    r"product-security|productcert|cve-coordination|ics-cert|package-announce|"
    r"help|info|support|contact|abuse|report|vuln|vulnerability|security-advisories|cve|nvd)"
)
_SSN_RE = re.compile(r"\b(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b")
_CREDIT_CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
_ABSOLUTE_CLAIM_RE = re.compile(
    r"\b(?:always|never|guaranteed|100\s*%\s*(?:safe|secure|effective)|"
    r"completely\s+secure|impossible\s+to\s+(?:bypass|exploit|break))\b",
    re.IGNORECASE,
)
_BOILERPLATE_LINE_RE = re.compile(
    r"^\s*(?:copyright\s+(?:©|\(c\)|\d{4})|licensed under|all rights reserved|"
    r"this (?:page|document) (?:was|is) (?:last )?(?:updated|generated)|"
    r"last updated:|page generated|powered by|skip to content|"
    r"cookie (?:policy|settings)|privacy policy|terms of service)\b",
    re.IGNORECASE,
)
_REPEATED_DISCLAIMER_RE = re.compile(
    r"^\s*(?:disclaimer|note|warning):\s*(?:this|the) (?:information|content|document)",
    re.IGNORECASE,
)


@dataclass
class QualityIssue:
    code: str
    severity: str = "reject"
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "severity": self.severity, "detail": self.detail}


@dataclass
class QualityAssessment:
    accepted: bool
    issues: list[QualityIssue] = field(default_factory=list)
    metrics: dict[str, float | int | bool | str] = field(default_factory=dict)

    @property
    def rejection_reasons(self) -> list[str]:
        return [issue.code for issue in self.issues if issue.severity == "reject"]

    @property
    def warnings(self) -> list[str]:
        return [issue.code for issue in self.issues if issue.severity == "warning"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "issues": [issue.to_dict() for issue in self.issues],
            "metrics": self.metrics,
        }


def _luhn_valid(value: str) -> bool:
    digits = [int(char) for char in value if char.isdigit()]
    if len(digits) < 13:
        return False
    checksum = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def _response_text(record: Record) -> str:
    if record.messages:
        assistant = [
            message["content"] for message in record.messages if message["role"] == "assistant"
        ]
        return assistant[-1] if assistant else ""
    if record.kind == "fim":
        return record.middle or ""
    return record.response or ""


def _prompt_text(record: Record) -> str:
    if record.messages:
        return "\n".join(
            message["content"] for message in record.messages if message["role"] == "user"
        )
    return record.prompt or ""


def _line_metrics(text: str) -> tuple[float, float]:
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if not lines:
        return 0.0, 0.0
    repeated = len(lines) - len(set(lines))
    repeated_ratio = repeated / len(lines)
    boilerplate = sum(
        1
        for line in lines
        if _is_navigation_line(line)
        or _BOILERPLATE_LINE_RE.match(line)
        or _REPEATED_DISCLAIMER_RE.match(line)
    )
    return repeated_ratio, boilerplate / len(lines)


def _unique_token_ratio(text: str) -> float:
    tokens = re.findall(r"[A-Za-z0-9_]{2,}", text.lower())
    if not tokens:
        return 0.0
    return len(set(tokens)) / len(tokens)


def _url_ratio(text: str) -> float:
    if not text:
        return 0.0
    url_chars = sum(len(match.group(0)) for match in _URL_RE.finditer(text))
    return min(1.0, url_chars / max(1, len(text)))


def assess_record(
    record: Record,
    thresholds: QualityThresholds | None = None,
    *,
    required_metadata: tuple[str, ...] = (),
) -> QualityAssessment:
    """Apply structural, length, boilerplate, secret, PII, and metadata gates."""

    thresholds = thresholds or QualityThresholds()
    response = _response_text(record)
    prompt = _prompt_text(record)
    total = record.text_for_dedup()
    issues: list[QualityIssue] = []
    metrics: dict[str, float | int | bool | str] = {
        "response_chars": len(response),
        "prompt_chars": len(prompt),
        "total_chars": len(total),
    }

    if not response.strip():
        issues.append(QualityIssue("empty_response"))
    if record.kind != "fim" and len(response) < thresholds.min_response_chars:
        issues.append(
            QualityIssue(
                "response_too_short",
                detail=f"{len(response)} < {thresholds.min_response_chars}",
            )
        )
    if len(response) > thresholds.max_response_chars:
        issues.append(
            QualityIssue(
                "response_too_long",
                detail=f"{len(response)} > {thresholds.max_response_chars}",
            )
        )
    if len(total) < thresholds.min_total_chars:
        issues.append(QualityIssue("record_too_short"))
    if len(total) > thresholds.max_total_chars:
        issues.append(QualityIssue("record_too_long"))
    if record.kind != "fim" and len(prompt) < thresholds.min_prompt_chars:
        issues.append(QualityIssue("prompt_too_short"))

    repeated_ratio, boilerplate_ratio = _line_metrics(response)
    unique_ratio = _unique_token_ratio(response)
    url_ratio = _url_ratio(response)
    metrics.update(
        {
            "repeated_line_ratio": round(repeated_ratio, 4),
            "boilerplate_ratio": round(boilerplate_ratio, 4),
            "unique_token_ratio": round(unique_ratio, 4),
            "url_char_ratio": round(url_ratio, 4),
        }
    )
    if repeated_ratio > thresholds.max_repeated_line_ratio:
        issues.append(
            QualityIssue(
                "excessive_repeated_lines",
                detail=f"{repeated_ratio:.2f} > {thresholds.max_repeated_line_ratio}",
            )
        )
    if boilerplate_ratio > thresholds.max_boilerplate_ratio:
        issues.append(
            QualityIssue(
                "boilerplate_heavy",
                detail=f"{boilerplate_ratio:.2f} > {thresholds.max_boilerplate_ratio}",
            )
        )
    if unique_ratio < thresholds.min_unique_token_ratio and len(response) > 80:
        issues.append(
            QualityIssue(
                "low_information",
                detail=f"unique token ratio {unique_ratio:.2f}",
            )
        )
    if url_ratio > thresholds.max_url_ratio:
        issues.append(QualityIssue("link_heavy", detail=f"url char ratio {url_ratio:.2f}"))

    secrets = find_secrets(response)
    high_confidence = [
        finding
        for finding in secrets
        if finding.kind
        in {
            "private_key",
            "aws_access_key",
            "github_token",
            "github_pat",
            "openai_key",
            "jwt",
            "connection_string_password",
        }
    ]
    metrics["secret_findings"] = len(secrets)
    if high_confidence:
        issues.append(
            QualityIssue(
                "secret_not_redacted",
                detail=", ".join(sorted({finding.kind for finding in high_confidence})),
            )
        )

    pii_kinds: list[str] = []
    emails = {
        match.group(0).lower()
        for match in _EMAIL_RE.finditer(response)
        if match.group(0).lower() not in _ORGANIZATIONAL_CONTACTS
        and not _ORGANIZATIONAL_LOCAL_RE.match(match.group(0).split("@", 1)[0].lower())
    }
    if emails:
        pii_kinds.append("email")
    if _SSN_RE.search(response):
        pii_kinds.append("ssn")
    for match in _CREDIT_CARD_RE.finditer(response):
        candidate = match.group(0)
        if _luhn_valid(candidate):
            pii_kinds.append("payment_card")
            break
    metrics["pii_kinds"] = ",".join(sorted(set(pii_kinds)))
    if pii_kinds:
        severity = (
            "reject"
            if thresholds.reject_pii and ({"ssn", "payment_card"} & set(pii_kinds))
            else "warning"
        )
        issues.append(QualityIssue("pii_detected", severity, ",".join(sorted(set(pii_kinds)))))

    missing = [key for key in required_metadata if not record.metadata.get(key)]
    if missing:
        issues.append(QualityIssue("broken_source_metadata", detail=",".join(missing)))
    if not record.url:
        issues.append(QualityIssue("missing_source_url", "warning"))
    if not record.metadata.get("source_version") and record.source not in {
        "cyberlite_smoke",
        "project_examples",
    }:
        issues.append(QualityIssue("missing_source_version", "warning"))

    absolute_claims = _ABSOLUTE_CLAIM_RE.findall(response)
    if absolute_claims:
        severity = "reject" if thresholds.reject_unsupported_absolute_claims else "warning"
        issues.append(
            QualityIssue(
                "unsupported_absolute_claim",
                severity,
                ", ".join(sorted({claim.lower() for claim in absolute_claims}))[:200],
            )
        )

    accepted = not any(issue.severity == "reject" for issue in issues)
    return QualityAssessment(accepted=accepted, issues=issues, metrics=metrics)


class TokenCounter(Protocol):
    name: str

    def count(self, text: str) -> int: ...


class HeuristicTokenCounter:
    """Documented fallback: four characters per token, labeled as an estimate."""

    name = "heuristic(chars/4)"

    def count(self, text: str) -> int:
        return max(1, math.ceil(len(text) / 4))


class TransformersTokenCounter:
    def __init__(self, tokenizer: Any, name: str) -> None:
        self.tokenizer = tokenizer
        self.name = name

    def count(self, text: str) -> int:
        try:
            encoded = self.tokenizer(text, add_special_tokens=False)
            if isinstance(encoded, dict):
                ids = encoded.get("input_ids", [])
            else:
                ids = getattr(encoded, "input_ids", [])
            return len(ids)
        except Exception:
            return HeuristicTokenCounter().count(text)


def load_token_counter(
    model_or_path: str,
    *,
    local_only: bool = True,
) -> tuple[TokenCounter, dict[str, Any]]:
    """Load only the tokenizer, never model weights.

    If the tokenizer is unavailable, return the heuristic counter and record
    ``estimated: true`` so reports cannot present the estimate as measured.
    """

    try:
        from transformers import AutoTokenizer  # local import keeps CPU-only paths light

        tokenizer = AutoTokenizer.from_pretrained(
            model_or_path,
            local_files_only=local_only,
            trust_remote_code=False,
        )
        revision = ""
        init_kwargs = getattr(tokenizer, "init_kwargs", {}) or {}
        revision = str(init_kwargs.get("_commit_hash") or init_kwargs.get("revision") or "")
        return TransformersTokenCounter(tokenizer, model_or_path), {
            "name": model_or_path,
            "kind": "transformers",
            "estimated": False,
            "revision": revision,
            "local_only": local_only,
        }
    except Exception as exc:
        return HeuristicTokenCounter(), {
            "name": "heuristic(chars/4)",
            "kind": "heuristic",
            "estimated": True,
            "error": str(exc)[:300],
            "local_only": local_only,
        }


def _percentile(values: list[int], fraction: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


def token_length_report(
    records: list[Record],
    counter: TokenCounter,
    *,
    max_sequence_tokens: int = 2048,
) -> dict[str, Any]:
    """Report token-length percentiles and truncation risk for Qwen3.5-0.8B."""

    lengths: list[int] = []
    over_limit = 0
    for record in records:
        text = record.text_for_dedup()
        tokenizer = getattr(counter, "tokenizer", None)
        if record.messages and tokenizer is not None:
            try:
                rendered = tokenizer.apply_chat_template(
                    record.messages, tokenize=False, add_generation_prompt=False
                )
                if isinstance(rendered, str):
                    text = rendered
            except Exception:
                pass
        count = counter.count(text)
        lengths.append(count)
        if count > max_sequence_tokens:
            over_limit += 1
    total = len(lengths)
    limits = sorted({512, 1024, 2048, 4096, 8192, max_sequence_tokens})
    by_limit = {
        str(limit): {
            "over_limit": sum(1 for length in lengths if length > limit),
            "ratio": round(sum(1 for length in lengths if length > limit) / total, 4)
            if total
            else 0.0,
        }
        for limit in limits
    }
    return {
        "tokenizer": counter.name,
        "records": total,
        "max_sequence_tokens": max_sequence_tokens,
        "truncation_by_limit": by_limit,
        "tokens": {
            "min": min(lengths) if lengths else 0,
            "p50": _percentile(lengths, 0.50),
            "p90": _percentile(lengths, 0.90),
            "p95": _percentile(lengths, 0.95),
            "p99": _percentile(lengths, 0.99),
            "max": max(lengths) if lengths else 0,
            "mean": round(sum(lengths) / total, 2) if total else 0.0,
        },
        "truncation": {
            "over_limit": over_limit,
            "ratio": round(over_limit / total, 4) if total else 0.0,
            "risk": "high" if total and over_limit / total > 0.05 else "low",
        },
        "limitations": (
            "Token counts are a length signal, not a quality measure. "
            "Truncation risk assumes the configured maximum sequence length and "
            "does not model the training collator or packing."
        ),
    }


def quality_summary(assessments: list[QualityAssessment]) -> dict[str, Any]:
    reasons: dict[str, int] = {}
    warnings: dict[str, int] = {}
    for assessment in assessments:
        for reason in assessment.rejection_reasons:
            reasons[reason] = reasons.get(reason, 0) + 1
        for warning in assessment.warnings:
            warnings[warning] = warnings.get(warning, 0) + 1
    return {
        "assessed": len(assessments),
        "accepted": sum(1 for item in assessments if item.accepted),
        "rejected": sum(1 for item in assessments if not item.accepted),
        "rejection_reasons": dict(sorted(reasons.items())),
        "warning_counts": dict(sorted(warnings.items())),
    }

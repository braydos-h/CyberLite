"""Shared evaluation-only guards used by ingestion, integrity, and training."""

from __future__ import annotations

from typing import Any

from cyberlite.data.cleaning import normalize_license

# Licenses that are non-commercial, no-derivatives, or otherwise reserved for
# evaluation. They must never reach a training split, even if a config lists
# them by mistake.
EVALUATION_ONLY_LICENSES = {
    "CC-BY-NC-4.0",
    "CC-BY-NC-SA-4.0",
    "CC-BY-NC-ND-4.0",
    "CC-BY-ND-4.0",
    "CC-BY-NC-SA-3.0",
    "Research-Only",
    "Evaluation-Only",
}

# Source identifiers used by local benchmark conversions. These are a safety
# net around schema mistakes; the primary signal is the record metadata and
# license.
EVALUATION_ONLY_SOURCES = {
    "seceval",
    "cyberseceval",
    "baseline-probe-v1",
    "smoke-eval",
}


def is_evaluation_only(record: Any) -> tuple[bool, str]:
    """Return ``(is_evaluation_only, reason)`` for a record-like object."""

    metadata = getattr(record, "metadata", {}) or {}
    normalized_license = normalize_license(str(getattr(record, "license", "")))
    if normalized_license in EVALUATION_ONLY_LICENSES:
        return True, f"evaluation-only license {normalized_license}"
    if metadata.get("evaluation_only") is True:
        return True, "record metadata marks it evaluation-only"
    source = str(getattr(record, "source", "")).strip().lower()
    if source in EVALUATION_ONLY_SOURCES:
        return True, f"evaluation source {source!r}"
    benchmark = str(metadata.get("benchmark") or "").strip().lower()
    if benchmark and metadata.get("evaluation_only") is not False:
        # A benchmark tag on a training record is ambiguous; fail closed.
        return True, f"record carries benchmark metadata {benchmark!r}"
    return False, ""

"""Offline summarization of opt-in autocomplete acceptance feedback."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any


def _wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total == 0:
        return (0.0, 0.0)
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def summarize_feedback(path: str | Path) -> dict[str, Any]:
    """Read hash-only feedback records and compute acceptance/latency summaries."""

    records: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
            if not isinstance(payload.get("accepted"), bool):
                raise ValueError(f"{path}:{line_number}: accepted must be boolean")
            records.append(payload)
    if not records:
        raise ValueError(f"no feedback records found in {path}")

    accepted = sum(1 for record in records if record["accepted"])
    latencies = [
        float(record["latency_seconds"])
        for record in records
        if isinstance(record.get("latency_seconds"), (int, float))
    ]
    by_language: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[str(record.get("language", "unknown"))].append(record)
    for language, items in sorted(grouped.items()):
        successes = sum(1 for item in items if item["accepted"])
        by_language[language] = {
            "suggestions": len(items),
            "accepted": successes,
            "acceptance_rate": successes / len(items),
        }
    low, high = _wilson_interval(accepted, len(records))
    return {
        "records": len(records),
        "accepted": accepted,
        "acceptance_rate": accepted / len(records),
        "acceptance_rate_95ci_wilson": [low, high],
        "latency_seconds": {
            "count": len(latencies),
            "mean": sum(latencies) / len(latencies) if latencies else None,
            "max": max(latencies) if latencies else None,
        },
        "by_language": by_language,
        "note": (
            "Acceptance is self-selected and UI-dependent; it is not a correctness metric. "
            "Completion text is not stored by the feedback endpoint."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Summarize autocomplete acceptance feedback.")
    parser.add_argument("feedback_file")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        summary = summarize_feedback(args.feedback_file)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

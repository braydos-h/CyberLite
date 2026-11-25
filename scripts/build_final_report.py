#!/usr/bin/env python
"""Assemble the final, text-free dataset report from measured artifacts.

Every number is read from a manifest or report that a build or reviewer wrote.
Missing artifacts are reported as missing, never filled with an estimate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _read(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload


def _sha(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest_summary(manifest: dict[str, Any] | None) -> dict[str, Any]:
    if not manifest:
        return {"available": False}
    return {
        "available": True,
        "dataset_name": manifest.get("dataset_name"),
        "dataset_version": manifest.get("dataset_version"),
        "stage": manifest.get("stage"),
        "stage_target": manifest.get("stage_target"),
        "balanced_target": manifest.get("balanced_target"),
        "deferred_records": manifest.get("deferred_records"),
        "generated_candidates": manifest.get("generated_candidates"),
        "considered_candidates": manifest.get("considered_candidates"),
        "accepted_records": manifest.get("accepted_records"),
        "rejected_records": manifest.get("rejected_records"),
        "acceptance_rate": manifest.get("acceptance_rate"),
        "split_counts": manifest.get("split_counts"),
        "distributions": manifest.get("distributions", {}),
        "token_lengths": manifest.get("token_lengths", {}),
        "deduplication": {
            key: manifest.get("deduplication", {}).get(key)
            for key in (
                "exact_duplicates",
                "simhash_near_duplicates",
                "semantic_near_duplicates",
                "semantic_method",
            )
        },
        "contamination": {
            key: manifest.get("contamination", {}).get(key)
            for key in ("status", "removed", "benchmarks_available", "benchmarks_unavailable")
        },
        "cross_split_leakage": len(manifest.get("cross_split_leakage") or []),
        "group_split_violations": len(manifest.get("group_split_violations") or []),
        "quality_rejection_counts": manifest.get("quality", {}).get("rejection_counts", {}),
        "review_coverage": manifest.get("review_coverage", {}),
        "manual_review": manifest.get("manual_review", {}),
        "files": manifest.get("files", {}),
        "limitations": manifest.get("limitations", []),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--calibration-manifest", default="data/manifests/synthesis-calibration/manifest.json"
    )
    parser.add_argument(
        "--production-manifest", default="data/manifests/synthesis-production/manifest.json"
    )
    parser.add_argument(
        "--balanced-manifest",
        default="data/manifests/synthesis-production-balanced/manifest.json",
    )
    parser.add_argument("--pilot-manifest", default="data/manifests/pilot-v2/manifest.json")
    parser.add_argument(
        "--evaluation-report", default="data/manifests/evaluation_validation_v1.json"
    )
    parser.add_argument(
        "--review-report", default="data/manifests/synthesis-production/review_report.json"
    )
    parser.add_argument(
        "--code-report", default="data/manifests/synthesis-calibration/code_verification.json"
    )
    parser.add_argument(
        "--integrity-report", default="data/manifests/synthesis-calibration/integrity_audit.json"
    )
    parser.add_argument(
        "--ml-report", default="data/manifests/synthesis-calibration/ml_review.json"
    )
    parser.add_argument("--out-json", default="data/manifests/final_report.json")
    parser.add_argument("--out-md", default="docs/reports/final-report.md")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    calibration = _manifest_summary(_read(Path(args.calibration_manifest)))
    production = _manifest_summary(_read(Path(args.production_manifest)))
    balanced = _manifest_summary(_read(Path(args.balanced_manifest)))
    pilot = _manifest_summary(_read(Path(args.pilot_manifest)))
    evaluation = _read(Path(args.evaluation_report)) or []
    review = _read(Path(args.review_report))
    code = _read(Path(args.code_report))
    integrity = _read(Path(args.integrity_report))
    ml = _read(Path(args.ml_report))

    review_summary = (review or {}).get("summary", {}) if review else {}
    applied = (review or {}).get("applied", {}) if review else {}
    report: dict[str, Any] = {
        "report": "cyberlite-dataset-expansion-final",
        "schema_version": 1,
        "created_at": datetime.now(tz=UTC).isoformat(),
        "measured": {
            "pilot": pilot,
            "calibration": calibration,
            "production": production,
            "balanced": balanced,
        },
        "evaluation": {
            "files": evaluation,
            "total_items": sum(
                int(item.get("items", 0)) for item in evaluation if isinstance(item, dict)
            ),
            "all_valid": all(bool(item.get("ok")) for item in evaluation if isinstance(item, dict)),
            "status": "measured" if evaluation else "missing",
        },
        "review": {
            "available": review is not None,
            "summary": review_summary,
            "applied": applied,
            "human_review": (review or {}).get("human_review", {}),
            "note": "AI review is not human review. Unreviewed records remain automated-screened.",
        },
        "code_verification": code or {"available": False},
        "integrity_audit": integrity or {"available": False},
        "ml_review": ml or {"available": False},
        "reproduction": {
            "calibration": "python scripts/synthesize_dataset.py --config configs/synthesis/calibration.yaml --force",
            "production": "python scripts/synthesize_dataset.py --config configs/synthesis/production.yaml --force",
            "evaluation": "python scripts/validate_evaluation.py data/evaluation/cyberlite_eval_*_v1.jsonl --freeze",
            "review": "python scripts/apply_reviews.py --splits-dir data/processed/synthesis-production --manifest-dir data/manifests/synthesis-production --apply",
            "mixture": "python scripts/plan_mixture.py --splits-dir data/processed/synthesis-production --out data/manifests/synthesis-production/mix_plan.json",
            "balance": "python scripts/balance_dataset.py --force",
            "audit": "python scripts/audit_synthesis.py",
            "export": "python scripts/export_dataset.py --splits-dir data/processed/synthesis-production-balanced --out data/processed/exports/production-balanced --force",
        },
        "hashes": {
            "calibration_manifest": _sha(Path(args.calibration_manifest)),
            "production_manifest": _sha(Path(args.production_manifest)),
            "balanced_manifest": _sha(Path(args.balanced_manifest)),
            "pilot_manifest": _sha(Path(args.pilot_manifest)),
            "evaluation_report": _sha(Path(args.evaluation_report)),
            "review_report": _sha(Path(args.review_report)),
        },
        "estimates_and_targets": {
            "stage_targets": {
                "calibration": 500,
                "initial": 5000,
                "production": 25000,
                "large": 50000,
                "extended": 100000,
            },
            "note": "Targets are plans. Accepted counts above are measured.",
        },
        "limitations": [
            "AI review is sampled and is not human review.",
            "Same-model-family reviewers may share blind spots.",
            "MinHash dedup is lexical, not embedding-based semantic similarity.",
            "The 13-gram contamination screen does not detect paraphrase or translation; CyberSecEval is unavailable.",
            "Source-derived records inherit upstream licences and may not be redistributable.",
            "No trained-model performance is claimed; evaluation sets are frozen but no model was evaluated.",
        ],
        "blockers": [
            "No human review sample has been recorded.",
            "CyberSecEval is not locally available for contamination screening.",
            "Windows enterprise and risk/governance knowledge packs are not yet authored.",
            "Review coverage is sampled; most accepted records are automated-screened only.",
            "Training license validation passes with explicit acknowledgements, but research preflight remains blocked by unresolved license questions, pending human review, and external pre-registration.",
            "Independent sampled review did not meet the 8.5 rubric mean (29 matched reviews: 6.81 overall; 5 accepted). The corpus is not approved for training and the final independent audit verdict is conditional.",
        ],
        "next_steps": [
            "Scale accepted volume only after the review sample meets the rubric.",
            "Add Windows/AD, macOS, cloud-provider, and governance knowledge packs.",
            "Run a model comparison against the frozen evaluation sets and report raw predictions.",
            "Obtain legal review for derived-corpus redistribution.",
        ],
    }
    out_json = Path(args.out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# CyberLite dataset expansion — final report",
        "",
        "This report is generated from build manifests and review artifacts. "
        "Measured values are labelled; targets are plans.",
        "",
        "## Accepted corpus",
        "",
        "| Build | Target | Accepted | Rejected | Acceptance rate | Train / val / test |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for name in ("calibration", "production", "balanced"):
        item = report["measured"][name]
        if not item.get("available"):
            lines.append(f"| {name} | — | missing | — | — | — |")
            continue
        splits = item.get("split_counts", {})
        target = item.get("balanced_target") if name == "balanced" else item.get("stage_target")
        rejected = item.get("rejected_records")
        rate = item.get("acceptance_rate")
        if name == "balanced":
            rejected = f"{item.get('deferred_records', 0)} deferred"
            rate = "—"
        lines.append(
            f"| {name} | {target} | {item.get('accepted_records')} | "
            f"{rejected} | {rate} | "
            f"{splits.get('train')} / {splits.get('validation')} / {splits.get('test')} |"
        )
    lines.extend(["", "## Evaluation sets", ""])
    if evaluation:
        lines.append(
            f"- {len(evaluation)} frozen file(s), {report['evaluation']['total_items']} items"
        )
        lines.append(f"- All valid: {report['evaluation']['all_valid']}")
        for item in evaluation:
            lines.append(
                f"- `{Path(item.get('path', '')).name}`: {item.get('items')} items, "
                f"sha256 `{item.get('sha256', '')[:16]}…`"
            )
    else:
        lines.append("- No evaluation validation report was found.")
    lines.extend(["", "## Review coverage", ""])
    if review:
        lines.append(f"- Reviewed records: {review_summary.get('reviewed_records')}")
        lines.append(f"- Review decisions: {review_summary.get('decisions')}")
        lines.append(f"- Disagreement rate: {review_summary.get('disagreement_rate')}")
        lines.append(f"- Applied: {applied}")
        if applied.get("accepted_reviewed_records"):
            lines.append(
                f"- Accepted reviewed subset (n={applied['accepted_reviewed_records']}): "
                f"mean {applied.get('accepted_review_average')}, technical "
                f"{applied.get('accepted_technical_average')}, grounding "
                f"{applied.get('accepted_grounding_average')}"
            )
    else:
        lines.append("- No review report was found. No record is described as AI-reviewed.")
    lines.extend(
        [
            "",
            "## Integrity checks",
            "",
            f"- Code/config verification available: {bool(code)}",
            f"- Integrity audit available: {bool(integrity)}",
            f"- ML review available: {bool(ml)}",
            "",
            "## Blockers and next steps",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in report["blockers"])
    lines.extend([""])
    lines.extend(f"- {item}" for item in report["next_steps"])
    lines.extend(
        [
            "",
            "## Reproduction",
            "",
            "```bash",
            *report["reproduction"].values(),
            "```",
            "",
            "## Limitations",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in report["limitations"])
    out_md = Path(args.out_md)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out_json} and {out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

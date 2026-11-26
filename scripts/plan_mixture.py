#!/usr/bin/env python
"""Compare an accepted corpus to the declared mixture policy."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml
from cyberlite.data.schema import load_records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--splits-dir", default="data/processed/synthesis-calibration")
    parser.add_argument("--config", default="configs/synthesis/mix.yaml")
    parser.add_argument("--out", default="data/manifests/synthesis-calibration/mix_plan.json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = yaml.safe_load(Path(args.config).read_text())
    records = []
    for name in ("train", "validation", "test"):
        path = Path(args.splits_dir) / f"{name}.jsonl"
        if path.exists():
            records.extend(load_records(path))
    if not records:
        raise SystemExit(f"no records in {args.splits_dir}")
    total = len(records)
    by_family: dict[str, int] = defaultdict(int)
    by_domain: dict[str, int] = defaultdict(int)
    tokens_by_family: dict[str, int] = defaultdict(int)
    for record in records:
        metadata = record.metadata or {}
        family = str(metadata.get("task_family") or record.task)
        domain = str(metadata.get("domain") or record.source)
        by_family[family] += 1
        by_domain[domain] += 1
        tokens_by_family[family] += int(metadata.get("token_count") or 0)

    family_caps = config.get("max_share_by_task_family", {})
    domain_caps = config.get("max_share_by_domain", {})
    minimums = config.get("min_share", {})
    violations = []
    for family, count in sorted(by_family.items()):
        share = count / total
        cap = family_caps.get(family)
        if cap is not None and share > cap:
            violations.append(
                {
                    "kind": "family_over_cap",
                    "name": family,
                    "share": round(share, 4),
                    "cap": cap,
                    "excess_records": max(0, count - int(cap * total)),
                }
            )
    for domain, count in sorted(by_domain.items()):
        share = count / total
        cap = domain_caps.get(domain)
        if cap is not None and share > cap:
            violations.append(
                {
                    "kind": "domain_over_cap",
                    "name": domain,
                    "share": round(share, 4),
                    "cap": cap,
                    "excess_records": max(0, count - int(cap * total)),
                }
            )
    for family, minimum in sorted(minimums.items()):
        if by_family.get(family, 0) / total < minimum:
            violations.append(
                {
                    "kind": "family_below_minimum",
                    "name": family,
                    "share": round(by_family.get(family, 0) / total, 4),
                    "minimum": minimum,
                }
            )
    plan: dict[str, Any] = {
        "config": args.config,
        "splits_dir": args.splits_dir,
        "records": total,
        "unique_domains": len(by_domain),
        "unique_task_families": len(by_family),
        "family_counts": dict(sorted(by_family.items())),
        "family_shares": {
            family: round(count / total, 4) for family, count in sorted(by_family.items())
        },
        "domain_shares": {
            domain: round(count / total, 4) for domain, count in sorted(by_domain.items())
        },
        "estimated_tokens_by_family": dict(sorted(tokens_by_family.items())),
        "violations": violations,
        "policy_compliant": not violations,
        "curriculum": config.get("curriculum", {}),
        "note": "Shares are record shares; caps are policy, not measured quality.",
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"{total} records, {len(by_family)} families, {len(by_domain)} domains, "
        f"{len(violations)} policy violations"
    )
    print(f"plan: {out}")
    return 0 if not violations else 1


if __name__ == "__main__":
    raise SystemExit(main())

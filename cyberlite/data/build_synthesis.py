"""Build a screened, split, and reported synthesis corpus.

The build is deterministic for a fixed knowledge-pack set, pilot input, seed,
and configuration. It writes bulk splits outside Git (the repository ignores
``data/processed``) and a text-free manifest plus reports under
``data/manifests``.
"""

from __future__ import annotations

import hashlib
import json
import platform
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from cyberlite import __version__
from cyberlite.data.cleaning import Deduplicator
from cyberlite.data.config import PIPELINE_VERSION, QualityThresholds
from cyberlite.data.contamination import (
    build_benchmark_index,
    check_contamination_v2,
    cross_split_leakage,
)
from cyberlite.data.detection import generate_detection_records
from cyberlite.data.grounded import generate_grounded
from cyberlite.data.quality import (
    QualityAssessment,
    assess_record,
    load_token_counter,
    quality_summary,
    token_length_report,
)
from cyberlite.data.schema import Record, load_records, sha256_file, write_jsonl
from cyberlite.data.semantic import deduplicate_near, template_skeletons
from cyberlite.data.splits import SplitRatios, group_split_violations, split_records
from cyberlite.data.synthesis import SynthesisResult, synthesize

STAGE_TARGETS = {
    "calibration": 500,
    "initial": 5_000,
    "production": 25_000,
    "large": 50_000,
    "extended": 100_000,
}
BUILD_SCHEMA_VERSION = 1
DEFAULT_ALLOWED_LICENSES = {
    "Synthetic",
    "Public-Domain",
    "MITRE-ATTACK",
    "MITRE-CWE",
    "IETF-Trust",
    "CC-BY-SA-4.0",
    "CC-BY-4.0",
    "Linux-man-pages-copyleft",
    "Linux-man-pages-1-para",
    "OpenSSH",
    "GPL-1.0-or-later",
    "GPL-2.0-only",
    "GPL-2.0-or-later",
    "GPL-3.0-or-later",
    "Mixed-SPDX",
}


@dataclass
class BuildOptions:
    packs_dir: Path
    out_dir: Path
    manifest_dir: Path
    stage: str = "calibration"
    limit: int | None = None
    seed: int = 42
    split_seed: int = 1337
    ratios: SplitRatios = field(default_factory=lambda: SplitRatios(0.9, 0.05, 0.05))
    pilot_dir: Path | None = None
    include_pilot: bool = False
    evaluation_dir: Path = Path("data/evaluation")
    tokenizer: str = "Qwen/Qwen3.5-0.8B"
    tokenizer_local_only: bool = True
    max_sequence_tokens: int = 1024
    dedup_threshold: int = 3
    semantic_threshold: float = 0.88
    contamination_n: int = 13
    contamination_threshold: float = 0.20
    min_response_chars: int = 60
    mix_policy: Path | None = Path("configs/synthesis/mix.yaml")
    quarantine_file: Path | None = Path("data/synthesis/quarantine.json")
    force: bool = False

    @property
    def target(self) -> int:
        return self.limit if self.limit is not None else STAGE_TARGETS[self.stage]

    def validate(self) -> None:
        if self.stage not in STAGE_TARGETS:
            raise ValueError(f"stage must be one of {sorted(STAGE_TARGETS)}")
        if self.target <= 0:
            raise ValueError("limit must be positive")
        if self.include_pilot and self.pilot_dir is None:
            raise ValueError("include_pilot requires pilot_dir")
        if not 0.0 <= self.semantic_threshold <= 1.0:
            raise ValueError("semantic_threshold must be between 0 and 1")


@dataclass
class BuildResult:
    records: list[Record]
    splits: dict[str, list[Record]]
    manifest: dict[str, Any]
    rejected: list[dict[str, Any]]
    preferences: list[dict[str, Any]] = field(default_factory=list)
    reports: dict[str, Any] = field(default_factory=dict)


def _stratified_sample(records: list[Record], limit: int) -> list[Record]:
    """Deterministic round-robin across domain/family/difficulty strata."""

    if limit >= len(records):
        return sorted(records, key=lambda item: item.id)
    strata: dict[tuple[str, str, str], list[Record]] = defaultdict(list)
    for record in sorted(records, key=lambda item: item.id):
        metadata = record.metadata or {}
        key = (
            str(metadata.get("domain") or record.source),
            str(metadata.get("task_family") or record.task),
            str(metadata.get("difficulty") or "unset"),
        )
        strata[key].append(record)
    ordered_keys = sorted(strata)
    selected: list[Record] = []
    cursor = 0
    while len(selected) < limit:
        added = False
        for key in ordered_keys:
            bucket = strata[key]
            if cursor < len(bucket):
                selected.append(bucket[cursor])
                added = True
                if len(selected) >= limit:
                    break
        if not added:
            break
        cursor += 1
    return selected


PILOT_DIFFICULTY = {
    "nist_nvd": "intermediate",
    "mitre_cwe": "intermediate",
    "mitre_attack": "intermediate",
    "owasp_cheatsheets": "intermediate",
    "linux_man_pages": "advanced",
    "openssh_docs": "advanced",
    "netfilter_nftables": "advanced",
    "ietf_rfcs": "advanced",
    "project_examples": "intermediate",
}
PILOT_TASK_FAMILY = {
    "vulnerability": "vulnerability-classification",
    "weakness": "vulnerability-classification",
    "attack-technique": "attack-technique-recognition",
    "defensive-control": "defensive-control",
    "documentation": "instruction-response",
    "secure-coding": "secure-code-review",
    "incident-response": "incident-investigation",
    "log-analysis": "log-interpretation",
    "detection-engineering": "detection-rule-interpretation",
}


def _enrich_pilot_metadata(records: list[Record]) -> None:
    """Add the expansion metadata that the frozen pilot predates."""

    for record in records:
        metadata = record.metadata
        metadata.setdefault("difficulty", PILOT_DIFFICULTY.get(record.source, "intermediate"))
        metadata.setdefault(
            "task_family", PILOT_TASK_FAMILY.get(record.task, "instruction-response")
        )
        metadata.setdefault("domain", record.source)
        metadata.setdefault("origin", "source-derived")
        metadata.setdefault("synthetic", False)
        metadata.setdefault("review_status", "automated-screened")
        metadata.setdefault("human_reviewed", False)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _load_quarantine(path: Path | None) -> set[str]:
    if path is None or not path.is_file():
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    facts = payload.get("facts", [])
    return {
        str(item.get("id"))
        for item in facts
        if isinstance(item, dict) and item.get("id") and item.get("status") != "cleared"
    }


def _load_mix_policy(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _quota_sample(
    records: list[Record],
    target: int,
    policy: dict[str, Any],
    *,
    strict_mix: bool = False,
) -> tuple[list[Record], dict[str, Any]]:
    """Select records under difficulty and mixture caps.

    The first pass enforces the declared caps. A second pass relaxes mixture
    caps only, never the expert ceiling, if the corpus cannot fill the target.
    Records deferred by a cap are reported, not described as defective.
    """

    difficulty_quota = {
        "foundational": int(target * 0.30),
        "intermediate": int(target * 0.40),
        "advanced": int(target * 0.25),
        "expert": max(1, int(target * 0.05)),
    }
    family_caps = policy.get("max_share_by_task_family", {}) or {}
    domain_caps = policy.get("max_share_by_domain", {}) or {}
    family_limit = {
        str(name): max(1, int(target * float(share))) for name, share in family_caps.items()
    }
    domain_limit = {
        str(name): max(1, int(target * float(share))) for name, share in domain_caps.items()
    }
    ordered = sorted(records, key=lambda item: _digest(item.id))
    selected: list[Record] = []
    selected_ids: set[str] = set()
    difficulty_counts: Counter[str] = Counter()
    family_counts: Counter[str] = Counter()
    domain_counts: Counter[str] = Counter()

    def family(record: Record) -> str:
        return str((record.metadata or {}).get("task_family") or record.task)

    def domain(record: Record) -> str:
        return str((record.metadata or {}).get("domain") or record.source)

    def difficulty(record: Record) -> str:
        return str((record.metadata or {}).get("difficulty") or "intermediate")

    def fits(record: Record, *, enforce_mix: bool) -> bool:
        if record.id in selected_ids:
            return False
        diff = difficulty(record)
        if difficulty_counts[diff] >= difficulty_quota.get(diff, target):
            return False
        if enforce_mix:
            fam = family(record)
            dom = domain(record)
            if fam in family_limit and family_counts[fam] >= family_limit[fam]:
                return False
            if dom in domain_limit and domain_counts[dom] >= domain_limit[dom]:
                return False
        return True

    def take(record: Record) -> None:
        selected.append(record)
        selected_ids.add(record.id)
        difficulty_counts[difficulty(record)] += 1
        family_counts[family(record)] += 1
        domain_counts[domain(record)] += 1

    minimums = policy.get("min_share", {}) or {}
    for family_name, share in sorted(minimums.items()):
        needed = max(1, int(target * float(share)))
        have = family_counts[str(family_name)]
        if have >= needed:
            continue
        for record in ordered:
            if family_counts[str(family_name)] >= needed:
                break
            if family(record) != str(family_name):
                continue
            if fits(record, enforce_mix=True):
                take(record)

    for enforce_mix in (True,) if strict_mix else (True, False):
        for record in ordered:
            if len(selected) >= target:
                break
            if fits(record, enforce_mix=enforce_mix):
                take(record)
        if len(selected) >= target:
            break
    # If the expert ceiling blocked the target, spend the remaining slots on
    # non-expert records before leaving the build short.
    if len(selected) < target and not strict_mix:
        for record in ordered:
            if len(selected) >= target:
                break
            if record.id in selected_ids:
                continue
            if (
                difficulty(record) == "expert"
                and difficulty_counts["expert"] >= difficulty_quota["expert"]
            ):
                continue
            take(record)
    stats = {
        "target": target,
        "selected": len(selected),
        "deferred": max(0, len(records) - len(selected)),
        "difficulty_counts": dict(sorted(difficulty_counts.items())),
        "difficulty_quota": difficulty_quota,
        "family_cap_violations": {
            name: count
            for name, count in family_counts.items()
            if name in family_limit and count > family_limit[name]
        },
        "domain_cap_violations": {
            name: count
            for name, count in domain_counts.items()
            if name in domain_limit and count > domain_limit[name]
        },
    }
    return selected, stats


def _license_allowed(license_id: str, allowed: set[str]) -> bool:
    return license_id in allowed


def _assess(
    records: list[Record], options: BuildOptions
) -> tuple[list[Record], list[dict[str, Any]], list[QualityAssessment]]:
    thresholds = QualityThresholds(
        min_prompt_chars=8,
        min_response_chars=options.min_response_chars,
        max_response_chars=12_000,
        min_total_chars=80,
        max_total_chars=20_000,
        max_repeated_line_ratio=0.35,
        min_unique_token_ratio=0.18,
        max_url_ratio=0.45,
        max_boilerplate_ratio=0.50,
        max_navigation_line_ratio=0.25,
        reject_pii=True,
        reject_unsupported_absolute_claims=False,
        max_sequence_tokens=options.max_sequence_tokens,
    )
    kept: list[Record] = []
    rejected: list[dict[str, Any]] = []
    assessments: list[QualityAssessment] = []
    for record in records:
        if not _license_allowed(record.license, DEFAULT_ALLOWED_LICENSES):
            rejected.append(
                {
                    "reason": "license_not_allowed",
                    "id": record.id,
                    "source": record.source,
                    "license": record.license,
                }
            )
            continue
        assessment = assess_record(record, thresholds)
        assessments.append(assessment)
        if not assessment.accepted:
            rejected.append(
                {
                    "reason": "quality:"
                    + (
                        assessment.rejection_reasons[0]
                        if assessment.rejection_reasons
                        else "unknown"
                    ),
                    "id": record.id,
                    "source": record.source,
                    "issues": assessment.rejection_reasons,
                }
            )
            continue
        kept.append(record)
    return kept, rejected, assessments


def _response_key(record: Record) -> str:
    """Normalized supervised answer, used to remove generic duplicate responses."""

    if record.kind == "fim":
        return ""
    if record.messages:
        assistant = [
            message["content"] for message in record.messages if message["role"] == "assistant"
        ]
        text = assistant[-1] if assistant else ""
    else:
        text = record.response or ""
    normalized = " ".join(re.findall(r"[a-z0-9_]+", text.lower()))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else ""


def _dedup(
    records: list[Record], options: BuildOptions
) -> tuple[list[Record], list[dict[str, Any]], dict[str, Any]]:
    deduplicator = Deduplicator(threshold=options.dedup_threshold)
    kept: list[Record] = []
    rejected: list[dict[str, Any]] = []
    seen_responses: dict[str, str] = {}
    for record in sorted(records, key=lambda item: item.id):
        response_key = _response_key(record)
        if response_key and response_key in seen_responses:
            rejected.append(
                {
                    "reason": "duplicate:response",
                    "id": record.id,
                    "source": record.source,
                    "other_id": seen_responses[response_key],
                }
            )
            continue
        duplicate, reason = deduplicator.is_duplicate(record.text_for_dedup())
        if duplicate:
            rejected.append(
                {
                    "reason": f"duplicate:{reason.split(':', 1)[0]}",
                    "id": record.id,
                    "source": record.source,
                    "detail": reason,
                }
            )
        else:
            if response_key:
                seen_responses[response_key] = record.id
            kept.append(record)
    semantic_kept, semantic_pairs = deduplicate_near(kept, threshold=options.semantic_threshold)
    semantic_removed = {pair.right_id for pair in semantic_pairs}
    for pair in semantic_pairs:
        rejected.append(
            {
                "reason": "near_duplicate:minhash",
                "id": pair.right_id,
                "source": next(
                    (item.source for item in kept if item.id == pair.right_id), "unknown"
                ),
                "other_id": pair.left_id,
                "similarity": pair.similarity,
            }
        )
    stats = {
        "exact_duplicates": deduplicator.exact_duplicates,
        "simhash_near_duplicates": deduplicator.near_duplicates,
        "semantic_near_duplicates": len(semantic_removed),
        "semantic_threshold": options.semantic_threshold,
        "semantic_method": "word 5-shingle MinHash/LSH (lexical approximation)",
        "semantic_pairs": [pair.__dict__ for pair in semantic_pairs[:50]],
        "input": len(records),
        "kept": len(semantic_kept),
    }
    return semantic_kept, rejected, stats


def _distribution(records: Iterable[Record], key: str) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for record in records:
        metadata = record.metadata or {}
        if key == "task_family":
            value = str(metadata.get("task_family") or record.task)
        elif key == "source":
            value = record.source
        elif key == "license":
            value = record.license
        elif key == "difficulty":
            value = str(metadata.get("difficulty") or "unset")
        elif key == "kind":
            value = record.kind
        elif key == "domain":
            value = str(metadata.get("domain") or record.source)
        else:
            value = str(metadata.get(key) or "unset")
        counts[value] += 1
    return dict(sorted(counts.items()))


def _token_report(
    records: list[Record], options: BuildOptions
) -> tuple[dict[str, Any], dict[str, int]]:
    counter, info = load_token_counter(options.tokenizer, local_only=options.tokenizer_local_only)
    report = token_length_report(records, counter, max_sequence_tokens=options.max_sequence_tokens)
    report["tokenizer_info"] = info
    lengths: dict[str, int] = {}
    for record in records:
        lengths[record.id] = counter.count(record.text_for_dedup())
    return report, lengths


def _eval_files(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(
        path for path in directory.glob("*.jsonl") if path.is_file() and path.name != "README.md"
    )


def _contamination(
    records: list[Record], options: BuildOptions
) -> tuple[list[Record], list[dict[str, Any]], dict[str, Any]]:
    files = _eval_files(options.evaluation_dir)
    if not files:
        return (
            records,
            [],
            {
                "status": "not_screened",
                "reason": "no evaluation files found",
                "limitations": "This is not evidence of absence.",
            },
        )
    index = build_benchmark_index(files, n=options.contamination_n)
    kept, findings, report = check_contamination_v2(
        records,
        index,
        threshold=options.contamination_threshold,
        group_quarantine=True,
    )
    rejected = [
        {
            "reason": "benchmark_contamination",
            "id": finding.id,
            "source": finding.source,
            "benchmark": finding.benchmark,
            "overlap": round(finding.overlap, 4),
            "group": finding.group,
        }
        for finding in findings
    ]
    direct = {finding.id for finding in findings}
    for record_id in report.get("group_removed_ids", []):
        if record_id in direct:
            continue
        rejected.append(
            {"reason": "benchmark_contamination_group", "id": record_id, "source": "unknown"}
        )
    report["status"] = "screened"
    report["files"] = [str(path) for path in files]
    report["benchmarks_available"] = [path.stem for path in files]
    report["benchmarks_unavailable"] = ["CyberSecEval (not present locally)"]
    report["limitations"] = (
        "13-gram lexical overlap only. Paraphrase, translation, and conceptual "
        "overlap are not detected. An unavailable benchmark is not a pass."
    )
    return kept, rejected, report


def _load_pilot(options: BuildOptions) -> tuple[list[Record], list[Record], dict[str, Any]]:
    assert options.pilot_dir is not None
    pilot_dir = options.pilot_dir
    info: dict[str, Any] = {"dir": str(pilot_dir), "splits": {}}
    all_records: list[Record] = []
    train_records: list[Record] = []
    for name in ("train", "validation", "test"):
        path = pilot_dir / f"{name}.jsonl"
        if not path.is_file():
            continue
        records = load_records(path)
        info["splits"][name] = {
            "records": len(records),
            "sha256": sha256_file(path),
        }
        if name == "train":
            train_records = records
        if options.include_pilot:
            all_records.extend(records)
    return all_records, train_records, info


def build(options: BuildOptions) -> BuildResult:
    options.validate()
    synthesis: SynthesisResult = synthesize(options.packs_dir)
    pilot_records, pilot_train, pilot_info = (
        _load_pilot(options) if options.pilot_dir else ([], [], {})
    )

    cwe_names: dict[str, str] = {}
    for record in pilot_train:
        metadata = record.metadata or {}
        if record.source == "mitre_cwe" and metadata.get("cwe_id") and metadata.get("name"):
            cwe_names[str(metadata["cwe_id"])] = str(metadata["name"])

    grounded = generate_grounded(pilot_train, cwe_names=cwe_names, max_per_record=6)
    detection = generate_detection_records()
    generated = synthesis.records + grounded.records + detection
    if options.include_pilot:
        _enrich_pilot_metadata(pilot_records)
        generated = pilot_records + generated

    considered = _stratified_sample(generated, max(options.target * 4, options.target))
    quality_kept, quality_rejected, assessments = _assess(considered, options)
    dedup_kept, dedup_rejected, dedup_stats = _dedup(quality_kept, options)
    screened, contamination_rejected, contamination_report = _contamination(dedup_kept, options)
    quota_stats: dict[str, Any] = {}
    if len(screened) > options.target:
        screened, quota_stats = _quota_sample(
            screened, options.target, _load_mix_policy(options.mix_policy)
        )
        deferred = quota_stats["deferred"]
    else:
        deferred = 0

    token_report, token_lengths = _token_report(screened, options)
    over_limit = [
        record
        for record in screened
        if token_lengths.get(record.id, 0) > options.max_sequence_tokens
    ]
    over_limit_ids = {record.id for record in over_limit}
    if over_limit_ids:
        screened = [record for record in screened if record.id not in over_limit_ids]
        for record in over_limit:
            contamination_rejected.append(
                {
                    "reason": "token_length_over_limit",
                    "id": record.id,
                    "source": record.source,
                    "tokens": token_lengths.get(record.id, 0),
                    "max_sequence_tokens": options.max_sequence_tokens,
                }
            )

    splits = split_records(screened, options.ratios, options.split_seed)
    leak_findings = cross_split_leakage(splits, threshold=options.dedup_threshold)
    removed_ids: set[str] = set()
    for finding in leak_findings:
        removed_ids.add(finding.right_id)
        contamination_rejected.append(
            {
                "reason": "cross_split_leakage",
                "id": finding.right_id,
                "source": finding.right_split,
                "other_id": finding.left_id,
                "kind": finding.kind,
            }
        )
    if removed_ids:
        for name in splits:
            splits[name] = [item for item in splits[name] if item.id not in removed_ids]
    group_violations = group_split_violations(splits)

    final_records = [record for name in ("train", "validation", "test") for record in splits[name]]
    token_report["removed_over_limit"] = len(over_limit)
    token_report["truncation"]["removed_over_limit"] = len(over_limit)
    for record in final_records:
        record.metadata["token_count"] = token_lengths.get(record.id, 0)
        if "content_hash" not in record.metadata:
            record.metadata["content_hash"] = hashlib.sha256(
                record.text_for_dedup().encode("utf-8")
            ).hexdigest()
        record.metadata["dataset_stage"] = options.stage
        record.metadata["build_id"] = ""  # filled after hashing

    version_hash = hashlib.sha256()
    for record in sorted(final_records, key=lambda item: item.id):
        version_hash.update(record.id.encode())
        version_hash.update(b"\x00")
        version_hash.update(record.text_for_dedup().encode())
        version_hash.update(b"\x00")
    version_hash.update(str(options.seed).encode())
    dataset_version = f"cyberlite-syn-{PIPELINE_VERSION}-{version_hash.hexdigest()[:12]}"
    build_id = dataset_version
    for record in final_records:
        record.metadata["build_id"] = build_id
        record.metadata["dataset_version"] = dataset_version

    rejected = quality_rejected + dedup_rejected + contamination_rejected
    rejection_counts = Counter(item["reason"] for item in rejected)
    distributions = {
        "source": _distribution(final_records, "source"),
        "license": _distribution(final_records, "license"),
        "domain": _distribution(final_records, "domain"),
        "task_family": _distribution(final_records, "task_family"),
        "task": _distribution(final_records, "task"),
        "difficulty": _distribution(final_records, "difficulty"),
        "kind": _distribution(final_records, "kind"),
        "origin": _distribution(final_records, "origin"),
        "review_status": _distribution(final_records, "review_status"),
    }
    source_text_derived = sum(
        1 for record in final_records if (record.metadata or {}).get("origin") == "source-derived"
    )
    manifest: dict[str, Any] = {
        "dataset_schema": BUILD_SCHEMA_VERSION,
        "dataset_name": f"cyberlite-{options.stage}",
        "dataset_version": dataset_version,
        "build_id": build_id,
        "pipeline_version": PIPELINE_VERSION,
        "cyberlite_version": __version__,
        "created_at": datetime.now(tz=UTC).isoformat(),
        "stage": options.stage,
        "stage_target": options.target,
        "seed": options.seed,
        "split_seed": options.split_seed,
        "options": {
            "packs_dir": str(options.packs_dir),
            "out_dir": str(options.out_dir),
            "manifest_dir": str(options.manifest_dir),
            "include_pilot": options.include_pilot,
            "pilot_dir": str(options.pilot_dir) if options.pilot_dir else None,
            "split": {
                "train": options.ratios.train,
                "validation": options.ratios.validation,
                "test": options.ratios.test,
            },
            "dedup_threshold": options.dedup_threshold,
            "split_seed": options.split_seed,
            "semantic_threshold": options.semantic_threshold,
            "contamination_n": options.contamination_n,
            "contamination_threshold": options.contamination_threshold,
            "tokenizer": options.tokenizer,
            "tokenizer_local_only": options.tokenizer_local_only,
            "max_sequence_tokens": options.max_sequence_tokens,
        },
        "inputs": {
            "packs": synthesis.stats,
            "grounded": grounded.stats,
            "detection": {
                "records": len(detection),
                "task_family": "detection-rule-interpretation",
            },
            "pilot": pilot_info,
            "evaluation_files": [str(path) for path in _eval_files(options.evaluation_dir)],
        },
        "generated_candidates": len(synthesis.records)
        + len(grounded.records)
        + len(detection)
        + (len(pilot_records) if options.include_pilot else 0),
        "considered_candidates": len(considered),
        "deferred_for_target": deferred,
        "quota_selection": quota_stats,
        "accepted_records": len(final_records),
        "rejected_records": len(rejected),
        "acceptance_rate": round(
            len(final_records) / max(1, len(final_records) + len(rejected)), 4
        ),
        "split_counts": {name: len(items) for name, items in splits.items()},
        "distributions": distributions,
        "source_derived_records": source_text_derived,
        "authored_synthetic_records": len(final_records) - source_text_derived,
        "quality": {
            "assessed": len(assessments),
            "summary": quality_summary(assessments),
            "rejection_counts": dict(sorted(rejection_counts.items())),
            "thresholds": {
                "min_response_chars": options.min_response_chars,
                "max_sequence_tokens": options.max_sequence_tokens,
            },
            "limitations": "Heuristic gates; not a substitute for technical review.",
        },
        "deduplication": dedup_stats,
        "contamination": contamination_report,
        "cross_split_leakage": [finding.to_dict() for finding in leak_findings[:100]],
        "group_split_violations": group_violations,
        "token_lengths": token_report,
        "review_coverage": {
            "automated_screening": len(final_records),
            "ai_independent_review": 0,
            "human_review": 0,
            "note": "Review coverage is updated by scripts/apply_reviews.py from an actual review ledger.",
        },
        "manual_review": {
            "completed": False,
            "human_reviewed_records": 0,
            "note": "No human review has been recorded. AI review is not human review.",
        },
        "template_concentration": template_skeletons(final_records, limit=15),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "limitations": [
            "The corpus is English-language and biased toward public documentation.",
            "Source-derived task views inherit the upstream licence and may not be redistributable.",
            "MinHash near-duplicate detection is lexical; it does not detect semantic paraphrase.",
            "The contamination screen is n-gram based; CyberSecEval is not locally available.",
            "AI review is not human review and may miss plausible-sounding errors.",
            "Token counts assume the configured tokenizer and do not model packing.",
        ],
    }
    return BuildResult(
        records=final_records,
        splits=splits,
        manifest=manifest,
        rejected=rejected,
        preferences=_filter_preferences(synthesis.preferences),
        reports={
            "quality": manifest["quality"],
            "contamination": contamination_report,
            "deduplication": dedup_stats,
            "token_lengths": token_report,
            "coverage": {
                "domain": distributions["domain"],
                "task_family": distributions["task_family"],
                "difficulty": distributions["difficulty"],
            },
        },
    )


def _filter_preferences(preferences: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    seen_prompts: set[str] = set()
    for item in preferences:
        prompt = str(item.get("prompt", "")).strip()
        chosen = str(item.get("chosen", "")).strip()
        rejected = str(item.get("rejected", "")).strip()
        if len(prompt) < 12 or len(chosen) < 60 or len(rejected) < 20:
            continue
        key = hashlib.sha256(prompt.lower().encode()).hexdigest()
        if key in seen_prompts:
            continue
        seen_prompts.add(key)
        kept.append(item)
    return kept


def write_build(result: BuildResult, options: BuildOptions) -> dict[str, Any]:
    options.out_dir.mkdir(parents=True, exist_ok=True)
    options.manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest = result.manifest
    paths: dict[str, Path] = {}
    for name in ("train", "validation", "test"):
        path = options.out_dir / f"{name}.jsonl"
        if path.exists() and not options.force:
            raise FileExistsError(f"{path} exists; pass force=True to replace")
        write_jsonl(result.splits[name], path)
        paths[name] = path
        manifest["files"] = manifest.get("files", {})
        manifest["files"][name] = {
            "path": str(path),
            "records": len(result.splits[name]),
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
    quarantine = options.out_dir / "quarantine.jsonl"
    with quarantine.open("w", encoding="utf-8") as handle:
        for item in result.rejected:
            handle.write(json.dumps(item, sort_keys=True) + "\n")
    manifest["files"]["quarantine"] = {
        "path": str(quarantine),
        "records": len(result.rejected),
        "sha256": sha256_file(quarantine),
        "bytes": quarantine.stat().st_size,
    }
    preferences_path = options.out_dir / "preferences.jsonl"
    with preferences_path.open("w", encoding="utf-8") as handle:
        for item in result.preferences:
            handle.write(json.dumps(item, sort_keys=True) + "\n")
    manifest["preference_pairs"] = len(result.preferences)
    manifest["files"]["preferences"] = {
        "path": str(preferences_path),
        "records": len(result.preferences),
        "sha256": sha256_file(preferences_path),
        "bytes": preferences_path.stat().st_size,
    }
    manifest["config_sha256"] = hashlib.sha256(
        json.dumps(manifest["options"], sort_keys=True).encode()
    ).hexdigest()
    (options.manifest_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    for name, payload in result.reports.items():
        (options.manifest_dir / f"{name}_report.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return manifest

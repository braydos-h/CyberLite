"""Reproducible dataset preparation pipeline.

The pipeline is intentionally offline-first: it operates on local files and
never downloads a source unless the user passes ``--download``. Every output
split is accompanied by a manifest containing input/output hashes, license
counts, cleaning statistics, and the effective options.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cyberlite import __version__
from cyberlite.data.cleaning import (
    Deduplicator,
    license_allowed,
    normalize_license,
    normalize_text,
    redact_secrets,
)
from cyberlite.data.contamination import check_contamination
from cyberlite.data.schema import Record, load_records, sha256_file, write_jsonl
from cyberlite.data.sources import (
    SourceRegistry,
    SourceSpec,
    download_source,
    normalize_source,
)
from cyberlite.data.splits import SplitRatios, split_records
from cyberlite.logging_utils import configure_logging, get_logger, log_event

logger = get_logger(__name__)

# Licenses that the default pipeline accepts. Some are copyleft or require
# attribution; the dataset card records those obligations. Unknown licenses
# are quarantined rather than silently accepted.
DEFAULT_ALLOWED_LICENSES = [
    "Apache-2.0",
    "MIT",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "CC-BY-4.0",
    "CC-BY-SA-4.0",
    "CC0-1.0",
    "Public-Domain",
    "Synthetic",
    "MITRE-ATTACK",
    "MITRE-CWE",
    "GPL-2.0-only",
    "GPL-2.0-or-later",
    "IETF-Trust",
]


@dataclass
class PrepareOptions:
    out_dir: Path
    seed: int = 42
    ratios: SplitRatios = field(default_factory=lambda: SplitRatios(0.9, 0.05, 0.05))
    allowed_licenses: list[str] = field(default_factory=lambda: list(DEFAULT_ALLOWED_LICENSES))
    redact: bool = True
    min_chars: int = 80
    max_chars: int = 200_000
    dedup_threshold: int = 3
    contamination_n: int = 13
    contamination_threshold: float = 0.2
    force: bool = False
    smoke: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["out_dir"] = str(self.out_dir)
        payload["ratios"] = asdict(self.ratios)
        return payload


@dataclass
class PreparedDataset:
    splits: dict[str, list[Record]]
    rejected: list[dict[str, Any]]
    manifest: dict[str, Any]


def _clean_text_fields(record: Record, options: PrepareOptions) -> tuple[Record, dict[str, Any]]:
    """Normalize and redact all text fields, returning a new validated record."""

    stats: dict[str, Any] = {"secret_kinds": [], "redactions": 0}

    def clean(value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = normalize_text(value, max_chars=options.max_chars)
        if options.redact:
            cleaned, findings = redact_secrets(cleaned)
            stats["redactions"] += len(findings)
            stats["secret_kinds"].extend(finding.kind for finding in findings)
        return cleaned

    messages = None
    if record.messages:
        messages = [
            {"role": message["role"], "content": clean(message["content"]) or ""}
            for message in record.messages
        ]
    metadata = dict(record.metadata)
    metadata["prepared_by"] = f"cyberlite-{__version__}"
    if stats["redactions"]:
        metadata["secrets_redacted"] = stats["redactions"]
        metadata["secret_kinds"] = sorted(set(stats["secret_kinds"]))
    cleaned_record = Record(
        id=record.id,
        source=record.source,
        license=normalize_license(record.license),
        task=record.task,
        messages=messages,
        prompt=clean(record.prompt),
        response=clean(record.response),
        prefix=clean(record.prefix),
        suffix=clean(record.suffix),
        middle=clean(record.middle),
        url=record.url,
        split=record.split,
        metadata=metadata,
    )
    return cleaned_record, stats


def _char_count(record: Record) -> int:
    return len(record.text_for_dedup())


def prepare_records(
    records: list[Record],
    options: PrepareOptions,
    *,
    eval_files: list[str] | None = None,
    source_registry_hash: str = "",
) -> PreparedDataset:
    """Clean, filter, deduplicate, contaminate-check, and split records."""

    rejected: list[dict[str, Any]] = []
    cleaned: list[Record] = []
    license_counts: dict[str, int] = {}
    redaction_count = 0

    for record in records:
        if not license_allowed(record.license, options.allowed_licenses):
            rejected.append(
                {
                    "reason": "license_not_allowed",
                    "license": record.license,
                    "source": record.source,
                    "id": record.id,
                }
            )
            continue
        try:
            record, stats = _clean_text_fields(record, options)
        except ValueError as exc:
            rejected.append(
                {"reason": f"invalid_record:{exc}", "source": record.source, "id": record.id}
            )
            continue
        redaction_count += stats["redactions"]
        if _char_count(record) < options.min_chars:
            rejected.append({"reason": "too_short", "source": record.source, "id": record.id})
            continue
        cleaned.append(record)
        license_counts[record.license] = license_counts.get(record.license, 0) + 1

    deduplicator = Deduplicator(threshold=options.dedup_threshold)
    unique: list[Record] = []
    for record in cleaned:
        duplicate, reason = deduplicator.is_duplicate(record.text_for_dedup())
        if duplicate:
            rejected.append(
                {"reason": f"duplicate:{reason}", "source": record.source, "id": record.id}
            )
        else:
            unique.append(record)

    contamination_findings: list[dict[str, Any]] = []
    eval_files = eval_files or []
    if eval_files:
        unique, contamination_findings = check_contamination(
            unique,
            eval_files,
            n=options.contamination_n,
            threshold=options.contamination_threshold,
        )
        for finding in contamination_findings:
            rejected.append(
                {
                    "reason": "benchmark_contamination",
                    "source": finding["source"],
                    "id": finding["id"],
                    "overlap": finding["overlap"],
                }
            )

    splits = split_records(unique, options.ratios, options.seed)
    if options.smoke:
        # Guarantee non-empty evaluation splits for pipeline validation only.
        for name in ("validation", "test"):
            if not splits[name] and len(splits["train"]) > 2:
                splits[name].append(splits["train"].pop())

    source_counts: dict[str, int] = {}
    task_counts: dict[str, int] = {}
    for split_records_list in splits.values():
        for record in split_records_list:
            source_counts[record.source] = source_counts.get(record.source, 0) + 1
            task_counts[record.task] = task_counts.get(record.task, 0) + 1

    split_counts = {name: len(items) for name, items in splits.items()}
    manifest: dict[str, Any] = {
        "dataset_schema": 1,
        "cyberlite_version": __version__,
        "created_at": datetime.now(tz=UTC).isoformat(),
        "seed": options.seed,
        "options": options.to_dict(),
        "source_registry_sha256": source_registry_hash,
        "input_records": len(records),
        "output_records": sum(split_counts.values()),
        "split_counts": split_counts,
        "source_counts": dict(sorted(source_counts.items())),
        "task_counts": dict(sorted(task_counts.items())),
        "license_counts": dict(sorted(license_counts.items())),
        "cleaning": {
            "redacted_secrets": redaction_count,
            "dedup": deduplicator.stats,
            "duplicates": deduplicator.exact_duplicates + deduplicator.near_duplicates,
        },
        "contamination": {
            "evaluation_files": [Path(path).name for path in eval_files],
            "removed": len(contamination_findings),
            "findings": contamination_findings[:100],
            "ngram": options.contamination_n,
            "threshold": options.contamination_threshold,
        },
        "rejected_counts": _rejection_counts(rejected),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "files": {},
    }

    # A dataset version is derived from the content of all splits, never from
    # timestamps, so identical inputs and options produce identical versions.
    version_hash = hashlib.sha256()
    for split_name in ("train", "validation", "test"):
        for record in sorted(splits[split_name], key=lambda item: item.id):
            version_hash.update(record.id.encode())
            version_hash.update(b"\x00")
            version_hash.update(record.text_for_dedup().encode())
    manifest["dataset_version"] = f"cyberlite-data-0.1.0-{version_hash.hexdigest()[:12]}"
    return PreparedDataset(splits=splits, rejected=rejected, manifest=manifest)


def _rejection_counts(rejected: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in rejected:
        reason = str(item["reason"]).split(":", 1)[0]
        counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items()))


def write_prepared_dataset(dataset: PreparedDataset, options: PrepareOptions) -> dict[str, Any]:
    """Write splits, quarantine, and manifest; return the completed manifest."""

    out_dir = options.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "train": out_dir / "train.jsonl",
        "validation": out_dir / "validation.jsonl",
        "test": out_dir / "test.jsonl",
    }
    if not options.force and any(path.exists() for path in paths.values()):
        raise FileExistsError(
            f"output splits already exist in {out_dir}; pass --force to replace them"
        )
    for name, path in paths.items():
        write_jsonl(dataset.splits[name], path)
        dataset.manifest["files"][name] = {
            "path": str(path),
            "records": len(dataset.splits[name]),
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
    quarantine_path = out_dir / "quarantine.jsonl"
    with quarantine_path.open("w", encoding="utf-8") as handle:
        for item in dataset.rejected:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    dataset.manifest["files"]["quarantine"] = {
        "path": str(quarantine_path),
        "records": len(dataset.rejected),
        "sha256": sha256_file(quarantine_path),
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(dataset.manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    dataset.manifest["manifest_path"] = str(manifest_path)
    return dataset.manifest


def collect_local_inputs(
    registry: SourceRegistry, raw_dir: Path, names: list[str] | None = None
) -> list[tuple[Path, SourceSpec]]:
    """Find already-downloaded local inputs for enabled sources."""

    inputs: list[tuple[Path, SourceSpec]] = []
    candidates = [registry.get(name) for name in names] if names else registry.enabled()
    for spec in candidates:
        if spec.kind == "jsonl" and not spec.filename:
            continue
        filename = spec.filename or Path(spec.url).name
        if not filename:
            continue
        path = raw_dir / spec.name / filename
        if path.is_file():
            inputs.append((path, spec))
    return inputs


def _load_eval_files(eval_dir: Path) -> list[str]:
    if not eval_dir.is_dir():
        return []
    return sorted(str(path) for path in eval_dir.glob("*.jsonl"))


def run_prepare(
    *,
    registry_path: Path,
    raw_dir: Path,
    eval_dir: Path,
    options: PrepareOptions,
    smoke_file: Path | None = None,
    input_paths: list[tuple[Path, SourceSpec]] | None = None,
) -> dict[str, Any]:
    """Execute the full preparation pipeline and write artifacts."""

    registry = SourceRegistry.load(registry_path)
    registry_hash = sha256_file(registry_path)
    records: list[Record] = []
    if options.smoke:
        if smoke_file is None or not smoke_file.is_file():
            raise FileNotFoundError(f"smoke dataset not found: {smoke_file}")
        records.extend(load_records(smoke_file))
    else:
        inputs = input_paths if input_paths is not None else collect_local_inputs(registry, raw_dir)
        if not inputs:
            raise FileNotFoundError(
                "no local raw inputs found. Download explicitly with --download SOURCE, "
                "or pass --input PATH --source NAME. Use --smoke for the tiny test dataset."
            )
        for path, spec in inputs:
            log_event(logger, "normalizing_source", source=spec.name, path=str(path))
            records.extend(normalize_source(path, spec))

    if not records:
        raise ValueError("no records were produced from the selected inputs")

    dataset = prepare_records(
        records,
        options,
        eval_files=_load_eval_files(eval_dir),
        source_registry_hash=registry_hash,
    )
    manifest = write_prepared_dataset(dataset, options)
    log_event(
        logger,
        "dataset_prepared",
        version=manifest["dataset_version"],
        train=manifest["split_counts"]["train"],
        validation=manifest["split_counts"]["validation"],
        test=manifest["split_counts"]["test"],
        rejected=len(dataset.rejected),
    )
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare a reproducible CyberLite dataset from local sources."
    )
    parser.add_argument("--sources", default="data/sources.yaml", help="source registry YAML")
    parser.add_argument("--out", default=None, help="output directory for splits")
    parser.add_argument("--raw-dir", default="data/raw", help="directory containing raw inputs")
    parser.add_argument("--eval-dir", default="data/evaluation", help="held-out evaluation JSONL")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--train-ratio", type=float, default=0.9)
    parser.add_argument("--validation-ratio", type=float, default=0.05)
    parser.add_argument("--test-ratio", type=float, default=0.05)
    parser.add_argument("--min-chars", type=int, default=80)
    parser.add_argument("--max-chars", type=int, default=200_000)
    parser.add_argument("--dedup-threshold", type=int, default=3)
    parser.add_argument("--contamination-threshold", type=float, default=0.2)
    parser.add_argument(
        "--allow-license",
        action="append",
        default=[],
        help="additional license identifier to accept (repeatable)",
    )
    parser.add_argument("--no-redact", action="store_true", help="disable secret redaction")
    parser.add_argument("--smoke", action="store_true", help="use the tiny bundled smoke dataset")
    parser.add_argument("--smoke-file", default="data/seed/smoke.jsonl")
    parser.add_argument(
        "--input",
        action="append",
        default=[],
        help="local input path (repeatable; requires --source)",
    )
    parser.add_argument("--source", default=None, help="registered source name for --input")
    parser.add_argument(
        "--download",
        action="append",
        default=[],
        help="explicitly download a registered source (repeatable)",
    )
    parser.add_argument("--force", action="store_true", help="replace existing output splits")
    parser.add_argument("--list-sources", action="store_true")
    parser.add_argument("--json-logs", action="store_true")
    parser.add_argument("--json", action="store_true", help="print manifest JSON to stdout")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(json_logs=args.json_logs)
    try:
        registry = SourceRegistry.load(args.sources)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.list_sources:
        for spec in registry.sources.values():
            flag = "enabled" if spec.enabled else "disabled"
            print(f"{spec.name:24s} {spec.kind:10s} {spec.license:18s} {flag:8s} {spec.title}")
        return 0

    if args.input and not args.source:
        print("error: --input requires --source", file=sys.stderr)
        return 2
    if len(args.download) > 1:
        print("error: pass at most one --download per invocation", file=sys.stderr)
        return 2

    raw_dir = Path(args.raw_dir)
    downloaded: list[tuple[Path, SourceSpec]] = []
    for name in args.download:
        try:
            spec = registry.get(name)
            path = download_source(spec, raw_dir / name)
        except (KeyError, OSError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        downloaded.append((path, spec))

    input_paths: list[tuple[Path, SourceSpec]] | None = None
    if args.input:
        try:
            spec = registry.get(args.source)
        except KeyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        input_paths = [(Path(path), spec) for path in args.input]
    elif downloaded:
        input_paths = downloaded

    out_dir = (
        Path(args.out)
        if args.out
        else Path("data/processed/smoke" if args.smoke else "data/processed")
    )
    try:
        if args.smoke and (args.train_ratio, args.validation_ratio, args.test_ratio) == (
            0.9,
            0.05,
            0.05,
        ):
            # A 34-example smoke corpus cannot populate 5% evaluation splits.
            ratios = SplitRatios(0.75, 0.125, 0.125)
        else:
            ratios = SplitRatios(args.train_ratio, args.validation_ratio, args.test_ratio)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    allowed = list(DEFAULT_ALLOWED_LICENSES) + args.allow_license
    options = PrepareOptions(
        out_dir=out_dir,
        seed=args.seed,
        ratios=ratios,
        allowed_licenses=allowed,
        redact=not args.no_redact,
        min_chars=args.min_chars,
        max_chars=args.max_chars,
        dedup_threshold=args.dedup_threshold,
        contamination_threshold=args.contamination_threshold,
        force=args.force,
        smoke=args.smoke,
    )
    try:
        manifest = run_prepare(
            registry_path=Path(args.sources),
            raw_dir=raw_dir,
            eval_dir=Path(args.eval_dir),
            options=options,
            smoke_file=Path(args.smoke_file),
            input_paths=input_paths,
        )
    except (FileExistsError, FileNotFoundError, KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(manifest, indent=2))
    else:
        counts = manifest["split_counts"]
        print(f"dataset version : {manifest['dataset_version']}")
        print(f"output          : {out_dir}")
        print(
            f"records         : train={counts['train']} "
            f"validation={counts['validation']} test={counts['test']}"
        )
        print(
            f"rejected        : {sum(manifest['rejected_counts'].values())} (see quarantine.jsonl)"
        )
        print(f"manifest        : {out_dir / 'manifest.json'}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

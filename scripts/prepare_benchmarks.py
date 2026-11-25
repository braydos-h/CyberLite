#!/usr/bin/env python3
"""Convert a locally obtained benchmark into the CyberLite evaluation schema.

CyberLite never bundles third-party benchmark items. This script performs the
explicit, license-aware conversion step and refuses to overwrite existing output
unless ``--force`` is passed. Benchmark items are written under ``data/evaluation``
which is ignored by Git and screened for training contamination.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cyberlite.evaluation.seceval import convert_records, validate_converted  # noqa: E402

SECEVAL_REVISION = "205dab7b0888a06f4b53ca7d9c7093e1326683e1"
SECEVAL_URL = "https://huggingface.co/datasets/XuanwuAI/SecEval/resolve/{revision}/questions.json"
SECEVAL_SOURCE = ROOT / "benchmarks" / "seceval" / "questions.json"
SECEVAL_OUT = ROOT / "data" / "evaluation" / "seceval_v1.jsonl"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    with urllib.request.urlopen(url, timeout=60) as response, temporary.open("wb") as handle:
        while chunk := response.read(1024 * 1024):
            handle.write(chunk)
    temporary.replace(destination)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--benchmark", choices=["seceval"], default="seceval", help="benchmark adapter to use"
    )
    parser.add_argument(
        "--input",
        default=str(SECEVAL_SOURCE.relative_to(ROOT)),
        help="upstream questions.json (ignored by Git)",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="explicitly fetch the pinned upstream SecEval questions.json",
    )
    parser.add_argument(
        "--revision",
        default=SECEVAL_REVISION,
        help="upstream Hugging Face revision/commit to download",
    )
    parser.add_argument(
        "--out",
        default=str(SECEVAL_OUT.relative_to(ROOT)),
        help="converted JSONL path (ignored by Git)",
    )
    parser.add_argument("--force", action="store_true", help="overwrite an existing output file")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    input_path = Path(args.input)
    output_path = Path(args.out)
    if not input_path.is_absolute():
        input_path = ROOT / input_path
    if not output_path.is_absolute():
        output_path = ROOT / output_path

    if args.download:
        url = SECEVAL_URL.format(revision=args.revision)
        print(f"downloading {url}")
        try:
            _download(url, input_path)
        except OSError as exc:
            print(f"error: download failed: {exc}", file=sys.stderr)
            return 2
        fetched_at = datetime.now(tz=UTC).isoformat()
    else:
        fetched_at = None

    if not input_path.is_file():
        print(
            f"error: {input_path} does not exist; download it explicitly with --download",
            file=sys.stderr,
        )
        return 2
    if output_path.exists() and not args.force:
        print(f"error: {output_path} exists; pass --force to overwrite", file=sys.stderr)
        return 2

    try:
        upstream = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: could not read {input_path}: {exc}", file=sys.stderr)
        return 2
    if not isinstance(upstream, list):
        print("error: upstream file must contain a JSON list", file=sys.stderr)
        return 2

    converted, report = convert_records(upstream)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for item in converted:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    validate_converted(str(output_path))

    metadata = {
        "benchmark": "seceval",
        "license": "CC-BY-NC-SA-4.0",
        "evaluation_only": True,
        "redistribution": "not permitted",
        "upstream_url": "https://huggingface.co/datasets/XuanwuAI/SecEval",
        "upstream_revision": args.revision,
        "upstream_sha256": _sha256(input_path),
        "converted_sha256": _sha256(output_path),
        "downloaded_at": fetched_at,
        **report,
    }
    metadata_path = output_path.with_suffix(".meta.json")
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(metadata, indent=2))
    print(f"wrote {len(converted)} records to {output_path}")
    print(f"metadata written to {metadata_path}")
    print("SecEval is CC BY-NC-SA 4.0: evaluation only, no redistribution, no training use.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

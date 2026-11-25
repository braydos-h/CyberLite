from __future__ import annotations

import json
from pathlib import Path

from cyberlite.data.build_synthesis import BuildOptions, build, write_build
from cyberlite.data.schema import load_records

from test_synthesis import _fact, _pack


def _options(tmp_path: Path, **overrides) -> BuildOptions:
    options = BuildOptions(
        packs_dir=tmp_path,
        out_dir=tmp_path / "out",
        manifest_dir=tmp_path / "manifest",
        stage="calibration",
        limit=20,
        pilot_dir=None,
        include_pilot=False,
        evaluation_dir=tmp_path / "eval",
        tokenizer="missing/tokenizer",
        tokenizer_local_only=True,
        semantic_threshold=0.95,
    )
    for key, value in overrides.items():
        setattr(options, key, value)
    return options


def test_build_is_deterministic_and_splits(tmp_path: Path) -> None:
    _pack(tmp_path, [_fact("lnx-test-001"), _fact("lnx-test-002")])
    first = build(_options(tmp_path))
    second = build(_options(tmp_path))
    first_ids = [record.id for record in first.records]
    second_ids = [record.id for record in second.records]
    assert first_ids == second_ids
    assert first.manifest["accepted_records"] == len(first.records)
    assert set(first.splits) == {"train", "validation", "test"}
    assert first.preferences
    assert all(record.metadata["token_count"] >= 0 for record in first.records)
    assert first.manifest["contamination"]["status"] == "not_screened"


def test_write_and_reload(tmp_path: Path) -> None:
    _pack(tmp_path)
    options = _options(tmp_path)
    result = build(options)
    manifest = write_build(result, options)
    reloaded = load_records(options.out_dir / "train.jsonl")
    assert len(reloaded) == manifest["split_counts"]["train"]
    preferences = (options.out_dir / "preferences.jsonl").read_text().strip().splitlines()
    assert preferences
    assert json.loads(preferences[0])["chosen"] != json.loads(preferences[0])["rejected"]


def test_limit_is_respected(tmp_path: Path) -> None:
    _pack(tmp_path)
    result = build(_options(tmp_path, limit=5))
    assert len(result.records) <= 5

"""Tests for the live progress generator."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "update_progress", ROOT / "scripts" / "update_progress.py"
)
assert spec is not None and spec.loader is not None
progress = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = progress
spec.loader.exec_module(progress)


def test_repository_readme_progress_is_current() -> None:
    assert progress.main(["--check"]) == 0


def test_parse_tracks_counts_only_checkboxes_in_matching_sections(tmp_path: Path) -> None:
    goals = tmp_path / "GOALS.md"
    goals.write_text(
        "# Goals\n\n- [x] ignored outside a goal section\n\n"
        "## G1 — Data\n\n- [x] done\n- [ ] todo\n\n## Notes\n\n- [x] ignored\n",
        encoding="utf-8",
    )
    tracks = progress.parse_tracks(goals, progress.GOAL_HEADING)
    assert [(track.id, track.done, track.total, track.percent) for track in tracks] == [
        ("G1", 1, 2, 50)
    ]


def test_render_block_includes_overall_and_phase_rows() -> None:
    goals = [progress.Track("G1", "Data", 1, 4)]
    phases = [progress.Track("Phase 0", "Foundation", 2, 2)]
    block = progress.render_block(goals, phases)
    assert "| **Overall** |" in block
    assert "25%" in block
    assert "Phase 0 — Foundation" in block
    assert "GOALS.md#g1--data" in block


def test_replace_block_preserves_markers() -> None:
    text = f"a\n{progress.START}\nold\n{progress.END}\nb\n"
    updated = progress.replace_block(text, "new")
    assert updated == f"a\n{progress.START}\nnew\n{progress.END}\nb\n"

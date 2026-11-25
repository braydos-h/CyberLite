#!/usr/bin/env python3
"""Summarize opt-in autocomplete acceptance feedback."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cyberlite.autocomplete.metrics import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())

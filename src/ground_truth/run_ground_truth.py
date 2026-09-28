"""Run the ground-truth scoring module.

Phase: ground-truth evaluation.
Input: hand-typed ground-truth JSON and matching extraction records.
Output: Gate 1 accuracy tables and a JSON evaluation report.
Commands:
  ``uv run python -m src.ground_truth.run_ground_truth --help``
  ``uv run python -m src.ground_truth.run_ground_truth --tag baseline``
"""
from __future__ import annotations

from src.ground_truth.scorer import main


if __name__ == "__main__":
    raise SystemExit(main())

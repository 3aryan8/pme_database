import sys
"""Compatibility entrypoint for the central pipeline.

Phase: compatibility orchestration.
Input: the arguments accepted by ``pipelines.run_all``.
Output: the selected module pipeline outputs.
Command: ``uv run python run_all.py [--skip-gpu|--dry-run]``.
"""

from pipelines.run_all import main


if __name__ == "__main__":
    sys.exit(main())

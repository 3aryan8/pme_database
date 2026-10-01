# Phase: compatibility orchestration | Input: central pipeline CLI arguments | Output: complete module pipeline | Command: ``uv run python main.py --dry-run``.
# Phase: compatibility orchestration | Input: central pipeline CLI arguments | Output: complete module pipeline | Command: ``uv run python main.py --dry-run``.
"""Project entrypoint: `python main.py` runs the entire pipeline.

Thin alias for the central orchestrator — all stages, flags, and
documentation live in run_all.py (and its pyproject entry points).
"""
import sys

from pipelines.run_all import main

if __name__ == "__main__":
    sys.exit(main())

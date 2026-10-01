"""Compatibility wrapper for the database module runner.

Phase: database import.
Input: canonical extraction records and ``--directory``.
Output: validated records imported into the normalized database.
Command: ``uv run python scripts/import_extractions.py --directory data/processed/extractions``.
"""
import sys

from src.database.run_database import main


if __name__ == "__main__":
	sys.exit(main())

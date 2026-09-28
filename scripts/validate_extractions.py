# Phase: database validation | Input: canonical record.json files | Output: validation summary and process status | Command: ``uv run python scripts/validate_extractions.py --directory data/processed/extractions``.
import argparse
from pathlib import Path

from src.database.schemas import PMEExtraction


def canonical_records(directory: Path) -> list[Path]:
    """Return only the validated record files produced by extraction."""
    return sorted(directory.rglob("record.json"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--directory",
        type=Path,
        default=Path("data/processed/extractions"),
    )
    args = parser.parse_args()

    files = canonical_records(args.directory)
    bad = 0
    for file_path in files:
        try:
            extraction = PMEExtraction.from_file(file_path)
            print(
                f"[OK] {file_path.name} | {extraction.document_id} | "
                f"roll={extraction.page1.narrative_details.roll_number}"
            )
        except Exception as error:
            bad += 1
            print(f"[ERROR] {file_path.name}: {error}")

    print(f"Valid: {len(files) - bad}\nInvalid: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())

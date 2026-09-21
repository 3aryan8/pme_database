"""Zero-touch extraction pipeline: text -> LLM -> validated schema -> DB.

Adding, removing, or modifying a field = editing pme/extraction_schema.py.
The extractor (prompt + validation), the store, and this runner never
change — the whole contract is derived from the schema class at runtime.

Usage:
    uv run python scripts/run_pipeline.py --text samples/sample_report.txt
    uv run python scripts/run_pipeline.py --text-dir samples/
    uv run python scripts/run_pipeline.py --dry-run     # print prompt only
    PME_TEXT_DIR=/reports uv run python scripts/run_pipeline.py

LLM env: PME_LLM_BASE_URL / PME_LLM_MODEL / PME_LLM_API_KEY /
PME_LLM_MAX_TOKENS / PME_LLM_TIMEOUT (see pme/extractor.py).
"""
import argparse
import importlib
import os
from pathlib import Path

from src.database.config import PROJECT_ROOT
from src.database.extractor import ExtractionError, LLMExtractor, build_prompt
from src.database.store import create_all, save

DEFAULT_SCHEMA = "src.database.extraction_schema.MedicalExaminationRecord"
DEFAULT_TEXT_DIR = PROJECT_ROOT / "samples"


def load_schema(dotted: str):
    """Import any Pydantic/SQLModel class by dotted path."""
    module_name, class_name = dotted.rsplit(".", 1)
    return getattr(importlib.import_module(module_name), class_name)


def find_texts(text: str | None, text_dir: str | None) -> list[Path]:
    if text:
        path = Path(text)
        if not path.is_file():
            raise SystemExit(f"no such text file: {path}")
        return [path]
    directory = Path(
        text_dir or os.getenv("PME_TEXT_DIR") or DEFAULT_TEXT_DIR
    )
    files = sorted(directory.glob("*.txt"))
    if not files:
        raise SystemExit(
            f"no .txt files in {directory} — use --text or --text-dir"
        )
    return files


def main() -> int:
    ap = argparse.ArgumentParser(
        description="text -> LLM -> validated schema -> database"
    )
    ap.add_argument("--text", help="single .txt report to process")
    ap.add_argument("--text-dir", help="directory of .txt reports")
    ap.add_argument(
        "--schema", default=DEFAULT_SCHEMA,
        help=f"dotted path to any Pydantic/SQLModel class ({DEFAULT_SCHEMA})",
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help="print the LLM prompt for the first file, then stop",
    )
    args = ap.parse_args()

    schema_cls = load_schema(args.schema)
    texts = find_texts(args.text, args.text_dir)
    extractor = LLMExtractor()

    if args.dry_run:
        print(f"# dry run — schema: {schema_cls.__name__}, text: {texts[0]}")
        print(build_prompt(schema_cls, texts[0].read_text(encoding="utf-8")))
        return 0

    create_all()
    ok = failed = 0
    for path in texts:
        text = path.read_text(encoding="utf-8")
        try:
            instance = extractor.extract(text, schema_cls)
        except ExtractionError as exc:
            failed += 1
            print(f"FAILED {path.name}: {exc}")
            continue
        record_id = save(instance)
        ok += 1
        print(f"saved {schema_cls.__name__} record_id={record_id}  (from {path.name})")

    print(f"\nProcessed: {ok}   Failed: {failed}")
    if ok:
        print(f"Retrieve: from src.database.store import get; "
              f"get({schema_cls.__name__}, <record_id>)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

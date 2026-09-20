"""No holdout document_id may appear in any tracked text file
(configs/, src/, scripts/, tests/). Exit 0 = clean, 1 = leakage/missing setup.

Usage: uv run python scripts/check_holdout_leakage.py
"""
import sys
from pathlib import Path

from src.utils.config_loader import config

IDS_FILE = config.root_dir / "configs/holdout_ids.txt"
SCAN_DIRS = ("configs", "src", "scripts", "tests")
SCAN_SUFFIXES = (".py", ".yaml", ".md", ".txt", ".json")


def main() -> int:
    if not IDS_FILE.exists():
        IDS_FILE.write_text("# one holdout document_id per line\n")
        print("created empty configs/holdout_ids.txt — add your 2 holdout IDs")
        return 1
    ids = [l.strip() for l in IDS_FILE.read_text().splitlines()
           if l.strip() and not l.startswith("#")]
    if not ids:
        print("configs/holdout_ids.txt is empty — set up your holdout docs")
        return 1

    leaks = []
    files = [p for d in SCAN_DIRS for p in (config.root_dir / d).rglob("*")
             if p.is_file() and p.suffix in SCAN_SUFFIXES and p != IDS_FILE]
    for p in files:
        text = p.read_text(errors="ignore")
        for hid in ids:
            if hid in text:
                leaks.append((str(p.relative_to(config.root_dir)), hid))
    if leaks:
        print("LEAKAGE FOUND:")
        for p, hid in leaks:
            print(f"  {hid[:12]}... appears in {p}")
        return 1
    print(f"clean: {len(ids)} holdout ID(s) absent from {len(files)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
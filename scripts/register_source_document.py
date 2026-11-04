"""Register an encrypted original PDF and its reviewed source-page manifest."""
from __future__ import annotations

import argparse
from pathlib import Path

from src.database.database import SessionLocal
from src.database.security import register_source_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--split-config", type=Path, required=True)
    args = parser.parse_args()
    with SessionLocal() as session:
        with session.begin():
            source = register_source_manifest(
                session, args.source, args.split_config
            )
            page_count = len(source.pages)
            source_id = source.id
    print(f"Registered source document {source_id} with {page_count} page records.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
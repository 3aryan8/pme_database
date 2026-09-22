from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"


def get_database_url() -> str:
    value = os.getenv("DATABASE_URL")
    if value:
        return value
    return f"sqlite:///{(DATA_DIR / 'pme.db').as_posix()}"


def get_extraction_dir() -> Path:
    value = os.getenv("EXTRACTION_DIR")
    if value:
        return Path(value)
    return DATA_DIR / "processed" / "extractions"


def get_interim_dir() -> Path:
    value = os.getenv("INTERIM_DIR")
    if value:
        return Path(value)
    return DATA_DIR / "interim"

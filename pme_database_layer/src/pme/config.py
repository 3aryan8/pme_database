from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(PROJECT_ROOT / ".env")


DEFAULT_EXTRACTION_DIR = (
    PROJECT_ROOT / "data" / "processed" / "extractions"
)


def get_database_url() -> str:
    return os.getenv(
        "DATABASE_URL",
        "sqlite:///./data/pme.db",
    )


def get_extraction_dir() -> Path:
    value = os.getenv("EXTRACTION_DIR")

    if value:
        return Path(value)

    return DEFAULT_EXTRACTION_DIR

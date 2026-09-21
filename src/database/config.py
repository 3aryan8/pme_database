from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]

# This package now lives INSIDE the pipeline project (src/database), so
# the project root IS the main project root (data/, configs/ live there).
MAIN_PROJECT_ROOT = PROJECT_ROOT

load_dotenv(PROJECT_ROOT / ".env")


DEFAULT_EXTRACTION_DIR = (
    PROJECT_ROOT / "data" / "processed" / "extractions"
)


def get_database_url() -> str:
    # Absolute, CWD-independent default: a relative sqlite path used to
    # silently create new empty DBs in whatever directory you ran from.
    return os.getenv(
        "DATABASE_URL",
        f"sqlite:///{PROJECT_ROOT / 'data' / 'pme.db'}",
    )


def get_extraction_dir() -> Path:
    value = os.getenv("EXTRACTION_DIR")

    if value:
        return Path(value)

    return DEFAULT_EXTRACTION_DIR


def get_report_images_dir() -> Path:
    """Root of rendered report pages (assembly output, one PNG per page).

    Default: <pipeline project>/data/interim/high_res/<document_id>/page_XXXX.png
    Override with REPORT_IMAGES_DIR.
    """
    value = os.getenv("REPORT_IMAGES_DIR")

    if value:
        return Path(value)

    return MAIN_PROJECT_ROOT / "data" / "interim" / "high_res"

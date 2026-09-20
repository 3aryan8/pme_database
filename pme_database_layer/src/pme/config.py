from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]

# The pipeline project (one level up): data/, configs/, src/ live there.
MAIN_PROJECT_ROOT = PROJECT_ROOT.parent

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


def get_report_images_dir() -> Path:
    """Root of rendered report pages (assembly output, one PNG per page).

    Default: <pipeline project>/data/interim/high_res/<document_id>/page_XXXX.png
    Override with REPORT_IMAGES_DIR.
    """
    value = os.getenv("REPORT_IMAGES_DIR")

    if value:
        return Path(value)

    return MAIN_PROJECT_ROOT / "data" / "interim" / "high_res"

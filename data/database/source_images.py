from __future__ import annotations

import logging
from pathlib import Path

from .config import get_interim_dir

LOGGER = logging.getLogger(__name__)
ORIGINAL_IMAGE_DIR = "high_res"
IMAGE_SUFFIXES = {".jpeg", ".jpg", ".png", ".webp"}


def get_original_image_paths(
    document_id: str,
    interim_dir: Path | None = None,
) -> list[Path]:
    """Return the original rendered pages for an extraction document.

    ``document_id`` is the existing content-derived identifier stored in
    ``extraction_runs``. The high-resolution render is used instead of the
    cleaned or VLM-resized derivatives so the dashboard shows source images.
    """
    image_dir = (
        interim_dir or get_interim_dir()
    ) / ORIGINAL_IMAGE_DIR / document_id

    if not image_dir.is_dir():
        LOGGER.warning(
            "Original image directory is missing for document_id=%s: %s",
            document_id,
            image_dir,
        )
        return []

    paths = sorted(
        (
            path
            for path in image_dir.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        ),
        key=lambda path: path.name,
    )

    if not paths:
        LOGGER.warning(
            "No original images found for document_id=%s in %s",
            document_id,
            image_dir,
        )

    return paths

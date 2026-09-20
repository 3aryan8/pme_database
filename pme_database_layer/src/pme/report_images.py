"""Locate the four rendered report pages for one document.

The assembly stage renders every person's report to
data/interim/high_res/<document_id>/page_0000.png .. page_0003.png.
A person report unit is exactly four pages, so all four are required.
"""
from __future__ import annotations

from pathlib import Path

from .config import get_report_images_dir

REPORT_PAGES = 4


def find_report_images(
    document_id: str, base_dir: Path | None = None
) -> list[tuple[int, Path]]:
    """Return (page_number, path) for all four report pages of a document.

    Page numbers are 1-based (1..4), in report order.
    Raises FileNotFoundError naming the first missing page.
    """
    base = (base_dir or get_report_images_dir()) / document_id
    pairs: list[tuple[int, Path]] = []
    for index in range(REPORT_PAGES):
        path = base / f"page_{index:04d}.png"
        if not path.is_file():
            raise FileNotFoundError(
                f"report page {index + 1}/{REPORT_PAGES} missing: {path}"
            )
        pairs.append((index + 1, path))
    return pairs

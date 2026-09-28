# Phase: database report verification | Input: rendered page directory | Output: ordered report-image paths | Command: ``uv run python -m src.database.run_database``.
"""Locate the rendered report pages for one document.

The assembly stage renders every person's report to
data/interim/high_res/<document_id>/page_0000.png, page_0001.png, ...
The page count per person is whatever configs/splits.yaml assigns that
person (N pages — not a fixed number), so a person with 3 or 6 pages works
the same way. When an expected count is given (the record's declared
coverage), a different render count fails the whole import atomically.
"""
from __future__ import annotations

import re
from pathlib import Path

from .config import get_report_images_dir


def find_report_images(
    document_id: str,
    base_dir: Path | None = None,
    expected: int | None = None,
) -> list[tuple[int, Path]]:
    """Return (page_number, path) for every rendered report page of a document.

    Page numbers are 1-based (1..N), in report order, where N is however
    many pages the assembly rendered for this person (per splits.yaml).
    If `expected` is given and the rendered count differs, or no pages
    exist at all, raises FileNotFoundError — no partial report images.
    """
    base = (base_dir or get_report_images_dir()) / document_id
    numbered_pages = []
    for path in base.glob("page_*.png"):
        if not path.is_file():
            continue
        match = re.fullmatch(r"page_(\d{4})\.png", path.name)
        if match is None:
            raise FileNotFoundError(
                f"invalid rendered report page name for document "
                f"{document_id}: {path.name}"
            )
        numbered_pages.append((int(match.group(1)), path))

    pages = [path for _, path in sorted(numbered_pages)]
    if not pages:
        raise FileNotFoundError(
            f"no rendered report pages for document {document_id} in {base}"
        )
    page_numbers = [number for number, _ in sorted(numbered_pages)]
    if page_numbers != list(range(page_numbers[0], page_numbers[0] + len(page_numbers))):
        raise FileNotFoundError(
            f"rendered report pages are not contiguous for document "
            f"{document_id} in {base}"
        )
    if page_numbers[0] != 0:
        raise FileNotFoundError(
            f"rendered report pages must start at page_0000 for document "
            f"{document_id} in {base}"
        )
    if expected is not None and len(pages) != expected:
        raise FileNotFoundError(
            f"expected {expected} rendered report pages for document "
            f"{document_id}, found {len(pages)} in {base}"
        )
    return list(enumerate(pages, start=1))

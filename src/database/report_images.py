"""Locate the rendered report pages for one document.

The assembly stage renders every person's report to
data/interim/high_res/<document_id>/page_0000.png, page_0001.png, ...
The page count per person is whatever configs/splits.yaml assigns that
person (N pages — not a fixed number), so a person with 3 or 6 pages works
the same way. When an expected count is given (the record's declared
coverage), a different render count fails the whole import atomically.
"""
from __future__ import annotations

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
    pages = sorted(p for p in base.glob("page_*.png") if p.is_file())
    if not pages:
        raise FileNotFoundError(
            f"no rendered report pages for document {document_id} in {base}"
        )
    if expected is not None and len(pages) != expected:
        raise FileNotFoundError(
            f"expected {expected} rendered report pages for document "
            f"{document_id}, found {len(pages)} in {base}"
        )
    return list(enumerate(pages, start=1))

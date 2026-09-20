"""Merge PDF files into one document (pure function — no config access).

Uses pymupdf, already a project dependency. Inputs are opened read-only
and are never modified or deleted.
"""
from pathlib import Path

import pymupdf as fitz


def merge_pdfs(input_paths: list[Path], output_path: Path) -> Path:
    """Merge the given PDFs, in exactly the given order, into output_path.

    Raises ValueError on an empty input list or a zero-page PDF, and
    pymupdf's FileDataError if a file is not a readable PDF.
    """
    if not input_paths:
        raise ValueError("no input PDFs to merge")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged = fitz.open()
    try:
        for path in input_paths:
            with fitz.open(str(path)) as source:
                if source.page_count == 0:
                    raise ValueError(f"PDF has no pages: {path}")
                merged.insert_pdf(source)
        merged.save(str(output_path))
    finally:
        merged.close()
    return output_path

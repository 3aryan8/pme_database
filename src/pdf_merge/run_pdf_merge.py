"""Run the PDF merge module.

Phase: PDF merge.
Input: PDF filenames from ``configs/pdf_sources.yaml`` and files in ``data/raw``.
Output: ``data/merged/merged_source.pdf``.
Command: ``uv run python -m src.pdf_merge.run_pdf_merge``.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from src.assembly.id_generator import file_sha256
from src.pdf_merge.merge import merge_pdfs
from src.utils.config_loader import config
from src.utils.logger import setup_logger

log = setup_logger("pdf_merge")
MERGED_FILENAME = "merged_source.pdf"


def resolve_configured_pdfs(raw_dir: Path | None = None) -> list[Path]:
    """Resolve configured PDF names to existing raw files."""
    raw_dir = raw_dir or config.get_path("raw_dir")
    paths = []
    missing = []
    for name in config.pdf_sources.pdfs:
        path = raw_dir / name
        if path.is_file():
            paths.append(path)
        else:
            missing.append(str(name))
    if missing:
        raise FileNotFoundError(
            f"PDFs from configs/pdf_sources.yaml not found in {raw_dir}: {missing}"
        )
    return paths


def merge_configured_pdfs(
    output_path: Path | None = None,
    raw_dir: Path | None = None,
    merged_dir: Path | None = None,
) -> Path:
    """Create the configured merged source PDF without changing inputs."""
    raw_dir = raw_dir or config.get_path("raw_dir")
    inputs = resolve_configured_pdfs(raw_dir)
    if output_path is None:
        output_path = (merged_dir or config.get_path("merged_dir")) / MERGED_FILENAME
    if output_path.resolve() in [path.resolve() for path in inputs]:
        raise ValueError(f"merged output collides with an input PDF: {output_path}")
    if len(inputs) == 1:
        source = inputs[0]
        if not (output_path.is_file() and file_sha256(output_path) == file_sha256(source)):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, output_path)
        log.info("single PDF configured — merged source ready: %s", output_path)
        return output_path
    merged = merge_pdfs(inputs, output_path)
    log.info("merged %d PDFs -> %s", len(inputs), merged)
    return merged


def main() -> int:
    """Merge configured PDFs and return a process status."""
    config.bootstrap_dirs()
    try:
        merged = merge_configured_pdfs()
    except (FileNotFoundError, ValueError) as exc:
        log.error("pdf merge failed: %s", exc)
        return 1
    log.info("merged source ready: %s", merged)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

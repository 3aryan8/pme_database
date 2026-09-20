"""Phase 0 entrypoint: merge the configured raw PDFs into one source PDF.

This is the first step of the pipeline: it reads the PDF filename list
from configs/pdf_sources.yaml, resolves + validates the files in data/raw,
and merges them (in YAML order) into a single source PDF that the existing
assembly stage then splits. Originals are never modified or deleted.

Usage: uv run python -m src.pdf_merge.run_merge
"""
from pathlib import Path

from src.pdf_merge.merge import merge_pdfs
from src.utils.config_loader import config
from src.utils.logger import setup_logger

log = setup_logger("pdf_merge")

MERGED_FILENAME = "merged_source.pdf"


def resolve_configured_pdfs(raw_dir: Path | None = None) -> list[Path]:
    """Resolve the YAML filename list to existing files (default: data/raw).

    Order is preserved. Raises FileNotFoundError naming every missing PDF.
    """
    raw_dir = raw_dir or config.get_path("raw_dir")
    paths: list[Path] = []
    missing: list[str] = []
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
    output_path: Path | None = None, raw_dir: Path | None = None
) -> Path:
    """Merge all configured PDFs, in YAML order, into one source PDF.

    Default output: data/raw/merged_source.pdf. Returns the merged path.
    """
    raw_dir = raw_dir or config.get_path("raw_dir")
    inputs = resolve_configured_pdfs(raw_dir)
    if len(inputs) == 1:
        # Single PDF: use it directly. Re-encoding would change the file
        # SHA and therefore every document_id (sha256(source_sha : person)).
        log.info("single PDF configured — using it directly: %s", inputs[0])
        return inputs[0]
    if output_path is None:
        output_path = raw_dir / MERGED_FILENAME
    if output_path.resolve() in [p.resolve() for p in inputs]:
        raise ValueError(
            f"merged output collides with one of its input PDFs: {output_path}"
        )
    merged = merge_pdfs(inputs, output_path)
    log.info("merged %d PDFs -> %s", len(inputs), merged)
    return merged


def main() -> int:
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

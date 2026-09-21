"""Phase 0 entrypoint: merge the configured raw PDFs into one source PDF.

This is the first step of the pipeline: it reads the PDF filename list
from configs/pdf_sources.yaml, resolves + validates the files in data/raw,
and merges them (in YAML order) into a single source PDF that the existing
assembly stage then splits. Originals are never modified or deleted.

Usage: uv run python -m src.pdf_merge.run_merge
"""
import shutil
from pathlib import Path

from src.assembly.id_generator import file_sha256
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
    output_path: Path | None = None,
    raw_dir: Path | None = None,
    merged_dir: Path | None = None,
) -> Path:
    """Materialize the pipeline's single source PDF in data/merged/.

    The merged file is the ONLY input the rest of the pipeline consumes —
    data/raw is never read downstream. One configured PDF is copied
    byte-for-byte (SHA preserved, so document_ids stay stable — no
    re-encoding); several are merged in YAML order. The output lives in a
    SEPARATE folder from the raw inputs, so it can never be picked up as an
    input on a later run (no recursive re-merging). Originals are never
    modified or deleted. Returns the merged path.
    """
    raw_dir = raw_dir or config.get_path("raw_dir")
    inputs = resolve_configured_pdfs(raw_dir)
    if output_path is None:
        output_path = (merged_dir or config.get_path("merged_dir")) / MERGED_FILENAME
    if output_path.resolve() in [p.resolve() for p in inputs]:
        raise ValueError(
            f"merged output collides with one of its input PDFs: {output_path}"
        )
    if len(inputs) == 1:
        src = inputs[0]
        # Idempotent: skip the copy when the destination is already
        # byte-identical (keeps mtime, avoids pointless rewrites).
        if not (output_path.is_file()
                and file_sha256(output_path) == file_sha256(src)):
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, output_path)
        log.info("single PDF configured — merged source ready: %s", output_path)
        return output_path
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

"""Phase 3 entrypoint: split -> render -> manifest.

Usage: uv run python -m src.assembly.run_assembly
"""
import json
from datetime import datetime, timezone

import pymupdf as fitz

from src.assembly.id_generator import person_document_id
from src.assembly.manifest_builder import write_manifest
from src.assembly.render import render_person_pages
from src.assembly.splitter import load_split_map
from src.utils.config_loader import config
from src.utils.logger import setup_logger

log = setup_logger("assembly")


def main() -> int:
    config.bootstrap_dirs()
    split_map = load_split_map()
    if not split_map.confirmed:
        log.error("configs/splits.yaml has confirmed: false — assembly refuses "
                  "to run on unverified person boundaries. Inspect the PDF and "
                  "confirm the map first.")
        return 1

    rows = []
    high_res_root = config.get_path("high_res_dir")
    mtime_iso = datetime.fromtimestamp(
        split_map.source_path.stat().st_mtime, tz=timezone.utc).isoformat()

    with fitz.open(split_map.source_path) as pdf:
        for person_index, first, last in split_map.persons:
            doc_id = person_document_id(split_map.source_sha, person_index)
            out_dir = high_res_root / doc_id
            out_dir.mkdir(parents=True, exist_ok=True)
            recs = render_person_pages(pdf, first, last, out_dir)
            for rec in recs:
                page = pdf[rec["source_page_number"] - 1]
                rows.append({
                    "document_id": doc_id,
                    "page_index": rec["page_index"],
                    "source_page_number": rec["source_page_number"],
                    "person_index": person_index,
                    "source_file_sha256": split_map.source_sha,
                    "high_res_raw_path":
                        rec["path"].relative_to(config.root_dir).as_posix(),
                    "file_mtime": mtime_iso,
                    "raw_page_width_pts": page.rect.width,
                    "effective_dpi_estimate": rec["effective_dpi_estimate"],
                    "render_dpi_used": rec["render_dpi_used"],
                    "low_source_quality_flag": rec["low_source_quality_flag"],
                    "split_check_status": split_map.split_status(person_index),
                })
            log.info("person %02d -> doc %s (source pages %d-%d, %d rendered)",
                     person_index, doc_id[:12], first, last, len(recs))

    out = write_manifest(rows)
    log.info("manifest written: %s (%d rows, %d persons)",
             out, len(rows), len(split_map.persons))

    audit = {
        "source_file_sha256": split_map.source_sha,
        "source_file": split_map.source_path.name,
        "persons": [[f, l] for _, f, l in split_map.persons],
        "rendering": "adaptive — page dpi = min(source effective dpi, cap)",
        "render_dpi_cap": config.pipeline.rendering.render_dpi,
        "applied_at": datetime.now(timezone.utc).isoformat(),
    }
    (config.get_path("metadata_dir") / "splits_applied.json").write_text(
        json.dumps(audit, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
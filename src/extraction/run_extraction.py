"""Phase 5 runner: single-pass document extraction (default) + per-page A/B.

Usage:
  CUDA_VISIBLE_DEVICES=0 uv run python -m src.extraction.run_extraction --ndocs 6
  ... --source raw --overwrite            (A/B: 300 DPI vs 1280px input)
  ... --doc <document_id>
  ... --mode per_page                     (A/B: one call per page + merge)

Outputs (Group 1 contract location, PII — gitignored via data/):
  document mode (DEFAULT, since 2026-09-12) — ONE JSON per person:
    data/processed/extractions/{doc}/document.json  [sidecar: page order,
        person_index, parse_ok, fields — replaces the 4 half-empty files]
    data/processed/extractions/{doc}/record.json    (validated ExtractionRecord)
  per_page mode (A/B fallback):
    data/processed/extractions/{doc}/page_XXXX.json
    data/processed/extractions/{doc}/record.json    (merged, first-non-null-wins)
"""
import argparse
import json
import sys
from datetime import datetime, timezone

import pandas as pd

from src.extraction.vlm_extractor import (DEFAULT_LONG_EDGE_HIRES,
                                           VlmSchemaExtractor)
from src.models.fields import (flatten_fields, iter_leaves,
                               unflatten_fields)
from src.models.schemas import ExtractionRecord, ProvenanceEntry
from src.utils.config_loader import config
from src.utils.logger import setup_logger

log = setup_logger("extraction")

SOURCE_COLS = {"vlm": "vlm_res_path", "clean": "high_res_path",
               "raw": "high_res_raw_path"}


def _resolve(row, source):
    val = row.get(SOURCE_COLS[source])
    if val is None or (isinstance(val, float) and pd.isna(val)) or val == "":
        return None
    return config.root_dir / val


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ndocs", type=int, default=None,
                    help="first N complete person-documents")
    ap.add_argument("--doc", type=str, default=None)
    ap.add_argument("--source", choices=["vlm", "clean", "raw"], default="vlm")
    ap.add_argument("--long-edge", type=int, default=None)
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--mode", choices=["document", "per_page"],
                    default="document",
                    help="document = single pass over all 4 pages, one JSON "
                         "per person (default); per_page = one call per page "
                         "+ first-non-null merge (A/B fallback)")
    args = ap.parse_args()

    manifest = config.get_path("manifest_file")
    if not manifest.exists():
        log.error("no manifest at %s — run assembly + preprocess first", manifest)
        return 1
    df = pd.read_parquet(manifest)
    if args.source != "raw" and SOURCE_COLS[args.source] not in df.columns:
        log.warning("manifest lacks %s — run preprocessing; falling back to raw",
                    SOURCE_COLS[args.source])
    if "blank_page_flag" in df.columns:
        df = df[~df["blank_page_flag"].fillna(False).astype(bool)]

    doc_ids = list(dict.fromkeys(df["document_id"]))   # manifest order
    if args.doc:
        doc_ids = [d for d in doc_ids if d == args.doc]
    if args.ndocs:
        doc_ids = doc_ids[:args.ndocs]
    if not doc_ids:
        log.error("no documents selected")
        return 1

    long_edge = args.long_edge or (
        config.pipeline.rendering.vlm_long_edge_px if args.source == "vlm"
        else DEFAULT_LONG_EDGE_HIRES)

    extractor = VlmSchemaExtractor()
    out_root = config.get_path("processed_dir") / "extractions"
    n_pages = n_fail = 0
    # provenance attribution for document mode: every leaf is credited to the
    # page its schema section belongs to (v2 tags each section with `page:`)
    leaf_page = {path: (s.page - 1 if s.page is not None else 0)
                 for s in extractor.schema.fields
                 for path, _ in iter_leaves([s])}

    for doc in doc_ids:
        rec_path = out_root / doc / "record.json"
        if rec_path.exists() and not args.overwrite:
            log.info("doc %s: record exists, skipping (--overwrite to redo)",
                     doc[:12])
            continue
        pages = df[df.document_id == doc].sort_values("page_index")
        schema_fields = extractor.schema.fields
        # person -> document mapping (acceptance: correct and logged)
        img_paths = [(_resolve(row, args.source)
                      or config.root_dir / row["high_res_raw_path"])
                     for _, row in pages.iterrows()]
        person_index = (int(pages.iloc[0]["person_index"])
                        if "person_index" in pages.columns else -1)
        log.info("doc %s <- person %s · %d pages in order: %s",
                 doc[:12], person_index, len(img_paths),
                 [p.name for p in img_paths])

        if args.mode == "document":
            try:
                n_pages += len(img_paths)
                fields, ok = extractor.extract_document(img_paths, long_edge)
            except Exception as e:    # noqa: BLE001 — never crash the batch
                n_fail += 1
                log.error("doc %s FAILED: %s", doc[:12], e)
                continue
            if not ok:
                n_fail += 1
                log.warning("doc %s: PARSE FAILURE — record will be all-null",
                            doc[:12])
            extracted_at = datetime.now(timezone.utc).isoformat()
            leaves = flatten_fields(fields, schema_fields)
            provenance = {path: {"page_index": leaf_page.get(path, 0),
                                 "model": extractor.model_id,
                                 "extracted_at": extracted_at,
                                 "raw_value": val}
                          for path, val in leaves.items() if val is not None}
            record = ExtractionRecord(
                document_id=doc, model=extractor.model_id, fields=fields,
                provenance={k: ProvenanceEntry(**v)
                            for k, v in provenance.items()},
                conflicts=[],
                pages_covered=[int(i) for i in pages["page_index"]])
            out_dir = out_root / doc
            out_dir.mkdir(parents=True, exist_ok=True)
            sidecar = {"document_id": doc, "mode": "document",
                       "person_index": person_index,
                       "model": extractor.model_id, "parse_ok": ok,
                       "model_input": [str(p.relative_to(config.root_dir))
                                       for p in img_paths],
                       "extracted_at": extracted_at, "fields": fields}
            (out_dir / "document.json").write_text(
                json.dumps(sidecar, indent=2))
            rec_path.parent.mkdir(parents=True, exist_ok=True)
            rec_path.write_text(record.model_dump_json(indent=2))
            log.info("doc %s: %d field-values non-null "
                     "(single pass, %d pages)", doc[:12],
                     sum(v is not None for v in leaves.values()),
                     len(img_paths))
            continue

        # ---------------- per-page A/B mode (original flow) ----------------
        leaves: dict = {}          # value-level dotted path -> str|None
        provenance: dict = {}
        conflicts: list = []
        pages_covered: list = []
        for _, row in pages.iterrows():
            idx = int(row["page_index"])
            img_path = (_resolve(row, args.source)
                        or config.root_dir / row["high_res_raw_path"])
            try:
                n_pages += 1
                # page-specific prompt: only ask for this page's fields
                page_fields, ok = extractor.extract_page(
                    img_path, long_edge, page=idx + 1)
                extracted_at = datetime.now(timezone.utc).isoformat()
                entry = {"document_id": doc, "page_index": idx,
                         "model": extractor.model_id, "parse_ok": ok,
                         "model_input": str(img_path.relative_to(config.root_dir)),
                         "extracted_at": extracted_at,
                         "fields": page_fields}
                page_json = out_root / doc / f"page_{idx:04d}.json"
                page_json.parent.mkdir(parents=True, exist_ok=True)
                page_json.write_text(json.dumps(entry, indent=2))
                pages_covered.append(idx)
                page_leaves = flatten_fields(page_fields, schema_fields)
                for path, val in page_leaves.items():
                    if val is None:
                        continue
                    if path in leaves and leaves[path] != val:
                        if path not in conflicts:
                            conflicts.append(path)
                        continue          # first non-null wins, conflict flagged
                    leaves[path] = val
                    provenance[path] = {"page_index": idx,
                                        "model": extractor.model_id,
                                        "extracted_at": extracted_at,
                                        "raw_value": val}
            except Exception as e:        # noqa: BLE001 — never crash the batch
                n_fail += 1
                log.error("doc %s page %d FAILED: %s", doc[:12], idx, e)

        record = ExtractionRecord(
            document_id=doc, model=extractor.model_id,
            fields=unflatten_fields(leaves, schema_fields),
            provenance={k: ProvenanceEntry(**v) for k, v in provenance.items()},
            conflicts=conflicts, pages_covered=pages_covered)
        rec_path.parent.mkdir(parents=True, exist_ok=True)
        rec_path.write_text(record.model_dump_json(indent=2))
        log.info("doc %s: %d field-values non-null, %d conflicts, %d pages",
                 doc[:12], len(leaves), len(conflicts), len(pages_covered))

    log.info("extraction done: mode=%s, %d pages, %d failures "
             "(source=%s, long_edge=%d)",
             args.mode, n_pages, n_fail, args.source, long_edge)
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
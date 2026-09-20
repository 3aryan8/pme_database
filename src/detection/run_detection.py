"""Batch VLM region detection over the manifest (Phase 6 prototype).

Usage:
  uv run python -m src.detection.run_detection --limit 6
  uv run python -m src.detection.run_detection --doc <document_id>
  uv run python -m src.detection.run_detection --limit 6 --source raw --overwrite

--source picks which image the MODEL sees (default: vlm — the contracted
two-resolution input):
  vlm   -> data/interim/vlm_res/...    (1280px copy)
  clean -> data/interim/high_res_clean/...
  raw   -> data/interim/high_res/...   (A/B: is preprocessing helping or hurting?)

Visualizations are ALWAYS drawn on the full 300 DPI raw render — normalized
boxes are resolution-independent, so review images show maximum detail.
Blank pages are skipped by default.
"""
import argparse
import json
import sys
from datetime import datetime, timezone

import pandas as pd

from src.detection.vlm_detector import VlmRegionDetector
from src.detection.visualize import draw_boxes
from src.utils.config_loader import config
from src.utils.logger import setup_logger

log = setup_logger("detection")

SOURCE_COLS = {"vlm": "vlm_res_path", "clean": "high_res_path",
               "raw": "high_res_raw_path"}


def _resolve(row: pd.Series, source: str):
    val = row.get(SOURCE_COLS[source])
    if val is None or (isinstance(val, float) and pd.isna(val)) or val == "":
        return None
    return config.root_dir / val


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--doc", type=str, default=None)
    ap.add_argument("--source", choices=["vlm", "clean", "raw"], default="vlm")
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--include-blank", action="store_true")
    args = ap.parse_args()

    manifest = config.get_path("manifest_file")
    if not manifest.exists():
        log.error("no manifest at %s — run assembly first", manifest)
        return 1
    df = pd.read_parquet(manifest)
    if args.doc:
        df = df[df.document_id == args.doc]
    if not args.include_blank and "blank_page_flag" in df.columns:
        before = len(df)
        df = df[~df["blank_page_flag"].fillna(False).astype(bool)]
        if before != len(df):
            log.info("skipping %d blank page(s)", before - len(df))
    if args.limit:
        df = df.head(args.limit)
    if df.empty:
        log.error("no pages to process")
        return 1

    if args.source != "raw" and SOURCE_COLS[args.source] not in df.columns:
        log.warning("manifest has no %s column — falling back to raw renders. "
                    "Run preprocessing for the contracted VLM input.",
                    SOURCE_COLS[args.source])

    detector = VlmRegionDetector()
    out_root = config.get_path("processed_dir") / "regions"
    ok = fail = skip = 0
    for _, row in df.iterrows():
        doc, idx = row["document_id"], int(row["page_index"])
        json_path = out_root / doc / f"page_{idx:04d}.json"
        if json_path.exists() and not args.overwrite:
            skip += 1
            continue
        img_path = _resolve(row, args.source)
        if img_path is None or not img_path.exists():
            img_path = config.root_dir / row["high_res_raw_path"]
        review_base = config.root_dir / row["high_res_raw_path"]
        try:
            dets = detector.detect(img_path)
            payload = {
                "document_id": doc,
                "page_index": idx,
                "source_page_number": int(row["source_page_number"]),
                "model": detector.model_id,
                "model_input": str(img_path.relative_to(config.root_dir)),
                "detected_at": datetime.now(timezone.utc).isoformat(),
                "detections": [
                    {"region_class": d.region_class,
                     "box_norm": d.box_norm,
                     "content_hint": d.content_hint} for d in dets],
            }
            json_path.parent.mkdir(parents=True, exist_ok=True)
            json_path.write_text(json.dumps(payload, indent=2))
            draw_boxes(review_base, dets,
                       out_root / doc / "vis" / f"page_{idx:04d}.png")
            ok += 1
        except Exception as e:              # noqa: BLE001
            fail += 1
            log.error("doc %s page %d FAILED: %s", doc[:12], idx, e)

    log.info("done: %d ok, %d failed, %d skipped (source=%s)",
             ok, fail, skip, args.source)
    log.info("REVIEW THESE: data/processed/regions/<doc_id>/vis/page_XXXX.png")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
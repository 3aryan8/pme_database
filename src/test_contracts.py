"""Gate 1 contract tests: pixel-dimension assertions against the manifest.

- high_res_RAW_path is the fidelity reference (must match DPI math exactly).
  Each row is checked against ITS OWN render_dpi_used (adaptive rendering:
  page dpi = min(source effective dpi, cap)); legacy manifests fall back
  to the configured cap.
- high_res_path (cleaned) is checked for plausibility only — deskew and
  crop-to-content legitimately change its dimensions.
- vlm_res_path is checked against the configured long-edge target.

Gracefully SKIPs (exit 0) before Phase 3/4 have produced data.
"""
import argparse
import sys
from pathlib import Path

import pandas as pd
from PIL import Image

from src.utils.config_loader import config

DPI_TOLERANCE_PX = 300  # ~1 inch of slack on the raw render


def _row_dpi(df: pd.DataFrame, row) -> float:
    """Per-row render DPI (adaptive). Old manifests lack the column —
    fall back to the configured cap, which is what they were rendered at."""
    dpi = row.get("render_dpi_used")
    if dpi is None or pd.isna(dpi):
        dpi = config.pipeline.rendering.render_dpi
    return float(dpi)


def test_raw_render_fidelity(df: pd.DataFrame, errors: list) -> None:
    for _, row in df.iterrows():
        raw = row.get("high_res_raw_path")
        if raw is None or pd.isna(raw):
            errors.append(f"doc {row['document_id'][:8]} page {row['page_index']}: "
                          "missing high_res_raw_path")
            continue
        dpi = _row_dpi(df, row)
        try:
            with Image.open(raw) as img:
                expected_w = (row["raw_page_width_pts"] / 72) * dpi
                if abs(img.width - expected_w) > DPI_TOLERANCE_PX:
                    errors.append(
                        f"doc {row['document_id'][:8]} page {row['page_index']}: "
                        f"raw render width {img.width} != expected ~{expected_w:.0f} "
                        f"@ {dpi} DPI")
        except Exception as e:               # noqa: BLE001
            errors.append(f"cannot open raw render {raw}: {e}")


def test_cleaned_plausibility(df: pd.DataFrame, errors: list) -> None:
    for _, row in df.iterrows():
        dpi = _row_dpi(df, row)
        try:
            with Image.open(row["high_res_path"]) as img:
                expected_w = (row["raw_page_width_pts"] / 72) * dpi
                if img.width < expected_w * 0.6:
                    errors.append(
                        f"doc {row['document_id'][:8]} page {row['page_index']}: "
                        f"cleaned image suspiciously small ({img.width}px "
                        f"vs raw ~{expected_w:.0f}px) — crop may be eating the page")
        except Exception as e:               # noqa: BLE001
            errors.append(f"cannot open cleaned image {row['high_res_path']}: {e}")


def test_vlm_resolution(df: pd.DataFrame, errors: list) -> None:
    target = config.pipeline.rendering.vlm_long_edge_px
    for _, row in df.iterrows():
        try:
            with Image.open(row["vlm_res_path"]) as img:
                long_edge = max(img.size)
                if not (target * 0.9 <= long_edge <= target * 1.1):
                    errors.append(
                        f"doc {row['document_id'][:8]} page {row['page_index']}: "
                        f"VLM long edge {long_edge} outside 10% of {target}")
        except Exception as e:               # noqa: BLE001
            errors.append(f"cannot open vlm image {row['vlm_res_path']}: {e}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path,
                        default=config.get_path("manifest_file"))
    args = parser.parse_args()

    if not args.manifest.exists():
        print(f"SKIP: no manifest yet at {args.manifest} — expected before Phase 3/4.")
        return 0

    df = pd.read_parquet(args.manifest)

    # manifest stores paths RELATIVE to project root — resolve to open locally
    for col in ("high_res_raw_path", "high_res_path", "vlm_res_path"):
        if col in df.columns:
            df[col] = df[col].map(lambda rel: str(config.root_dir / rel))
            
    errors: list = []

    if df["document_id"].isnull().any():
        errors.append("manifest contains null document_id values")
    if "high_res_raw_path" not in df.columns:
        errors.append("manifest missing high_res_raw_path column")

    test_raw_render_fidelity(df, errors)
    if "high_res_path" in df.columns:
        test_cleaned_plausibility(df, errors)
    if "vlm_res_path" in df.columns:
        test_vlm_resolution(df, errors)

    if errors:
        print(f"FAIL: {len(errors)} contract violation(s):")
        for e in errors[:50]:
            print(f"  - {e}")
        return 1
    print(f"PASS: all contract tests green for {len(df)} manifest rows.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
"""Phase 4 entrypoint: raw renders -> cleaned + VLM copies; manifest upgrade.

- Every processed row is validated against ManifestRow BEFORE the manifest
  is written — the parquet on disk is guaranteed contract-valid.
- Failures are logged and skipped (the batch never crashes); skipped rows
  keep their Phase-3 state, so src.test_contracts flags them — visible,
  not silent.
- --limit N processes only the first N pages and does NOT write the
  manifest (dry-run mode for benchmarking / eyeballing).
- Prints the per-page runtime benchmark the Group 1 spec requires before
  the <2s/page target may be treated as fixed.
"""
import argparse
import sys
import time

import cv2
import pandas as pd

from src.models.schemas import ManifestRow
from src.preprocessing.cleaner import clean_page
from src.preprocessing.vlm_resizer import make_vlm_copy
from src.utils.config_loader import config
from src.utils.logger import setup_logger

log = setup_logger("preprocess")

SPEC_TARGET_SEC_PER_PAGE = 2.0   # Group 1 spec target (provisional)


def main(limit: int | None = None) -> int:
    manifest_path = config.get_path("manifest_file")
    if not manifest_path.exists():
        log.error("no manifest at %s — run assembly first", manifest_path)
        return 1
    df = pd.read_parquet(manifest_path)
    if limit:
        df = df.head(limit)
        log.info("LIMIT MODE: %d pages — manifest will NOT be written", len(df))

    clean_root = config.get_path("high_res_clean_dir")
    vlm_root = config.get_path("vlm_res_dir")
    result = df.copy()
    for col, default in (("high_res_path", None), ("vlm_res_path", None),
                         ("vlm_res_width", None), ("blank_page_flag", False)):
        if col not in result.columns:
            result[col] = default

    times: list = []
    n_ok = n_fail = n_blank = 0
    for i, row in df.iterrows():
        doc, idx = row["document_id"], int(row["page_index"])
        raw_path = config.root_dir / row["high_res_raw_path"]
        try:
            t0 = time.time()
            bgr = cv2.imread(str(raw_path), cv2.IMREAD_COLOR)
            if bgr is None:
                raise IOError(f"unreadable image: {raw_path}")
            cleaned, flags = clean_page(bgr)

            clean_dir = clean_root / doc
            clean_dir.mkdir(parents=True, exist_ok=True)
            clean_path = clean_dir / f"page_{idx:04d}.png"
            if not cv2.imwrite(str(clean_path), cleaned):
                raise IOError(f"write failed: {clean_path}")

            vlm_dir = vlm_root / doc
            vlm_dir.mkdir(parents=True, exist_ok=True)
            vlm_path = vlm_dir / f"page_{idx:04d}.png"
            vlm_width = make_vlm_copy(clean_path, vlm_path)

            updated = row.to_dict()
            updated.update({
                "high_res_path":
                    clean_path.relative_to(config.root_dir).as_posix(),
                "vlm_res_path":
                    vlm_path.relative_to(config.root_dir).as_posix(),
                "vlm_res_width": vlm_width,
                "blank_page_flag": bool(flags.get("blank", False)),
            })
            ManifestRow(**updated)          # validate BEFORE writing
            for k in ("high_res_path", "vlm_res_path",
                      "vlm_res_width", "blank_page_flag"):
                result.loc[i, k] = updated[k]

            n_ok += 1
            if flags.get("blank"):
                n_blank += 1
            if any(flags.get(k) for k in ("deskewed", "borders_trimmed",
                                          "skew_suspicious", "blank")):
                log.info("doc %s p%d: %s", doc[:12], idx, flags)
            times.append(time.time() - t0)
        except Exception as e:              # noqa: BLE001
            n_fail += 1
            log.error("doc %s page %d FAILED (skipped): %s",
                      doc[:12], idx, e)

    if times:
        mean_t, max_t = sum(times) / len(times), max(times)
        verdict = "MEETS" if mean_t <= SPEC_TARGET_SEC_PER_PAGE else "EXCEEDS"
        log.info("benchmark: mean %.2fs/page, max %.2fs/page over %d pages "
                 "— spec target %.1fs: %s (provisional; revise if "
                 "consistently exceeded, per Group 1 spec)",
                 mean_t, max_t, len(times), SPEC_TARGET_SEC_PER_PAGE, verdict)
    log.info("preprocess done: %d ok, %d failed, %d blank",
             n_ok, n_fail, n_blank)

    if limit:
        return 0 if n_fail == 0 else 1

    result.to_parquet(manifest_path, index=False)
    log.info("manifest upgraded with Phase 4 columns: %s (%d rows)",
             manifest_path, len(result))
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    sys.exit(main(limit=args.limit))
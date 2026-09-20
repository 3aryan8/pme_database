"""Generate ground-truth skeletons for hand-typing.

Usage: uv run python scripts/make_gt_template.py --ndocs 6

Writes data/ground_truth/gt/{document_id}.json with every schema field null.

YOUR JOB per file:
  1. Open data/interim/high_res_clean/{document_id}/page_*.png
  2. Type each value EXACTLY as printed.
     null = field genuinely absent/empty on the form
     '?'  = present but you cannot read it (excluded from scoring)
  3. Fill it in BEFORE looking at record.json — no anchoring on model output.
Then move 2 files into data/ground_truth/eval_holdout/ and list those
document_ids in configs/holdout_ids.txt.
"""
import argparse

import pandas as pd

from src.models.fields import null_shape
from src.utils.config_loader import config
from src.utils.logger import setup_logger

log = setup_logger("gt")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ndocs", type=int, default=6)
    ap.add_argument("--annotator", type=str, default="manual")
    args = ap.parse_args()

    df = pd.read_parquet(config.get_path("manifest_file"))
    doc_ids = list(dict.fromkeys(df["document_id"]))[:args.ndocs]
    skeleton = null_shape(config.schema.fields)   # nested; arrays prefilled

    out_dir = config.root_dir / "data/ground_truth/gt"
    out_dir.mkdir(parents=True, exist_ok=True)
    for doc in doc_ids:
        out = out_dir / f"{doc}.json"
        if out.exists():
            log.info("exists, kept: %s", out.name)
            continue
        out.write_text(json_dump({"document_id": doc,
                                  "annotator": args.annotator,
                                  "fields": skeleton,
                                  "notes": None}))
        n_pages = int((df.document_id == doc).sum())
        log.info("wrote %s — open data/interim/high_res_clean/%s/page_*.png "
                 "(%d pages) and fill it in", out.name, doc, n_pages)


def json_dump(obj) -> str:
    import json
    return json.dumps(obj, indent=2)


if __name__ == "__main__":
    main()
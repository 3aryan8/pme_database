"""Propose person boundaries in the multi-person PDF using the VLM.

Writes configs/splits_draft.yaml — a DRAFT, never auto-applied. You must
review every proposed boundary in a PDF viewer, correct it, save as
configs/splits.yaml, and set confirmed: true.

Usage: uv run python -m src.detection.propose_splits
"""
import json
import re
import sys
from datetime import datetime, timezone

import pymupdf as fitz
import yaml
from PIL import Image

from src.detection.vlm_detector import VlmRegionDetector, pin_size
from src.utils.config_loader import config
from src.utils.logger import setup_logger

log = setup_logger("split-propose")

SOURCE = "data/raw/black_dataset.pdf"

PROMPT = (
    "You are looking at one page from a stack of scanned medical report "
    "PDFs. Each person's report is roughly 4-6 pages. Does THIS page look "
    "like the FIRST page of a NEW person's report? First pages typically "
    "show a report header: photo box, typed name / employee ID / exam "
    "date fields, clinic letterhead. Answer ONLY with JSON: "
    '{"new_report_starts": true|false, "confidence": 0.0-1.0, '
    '"reason": "<short>"}'
)


def main() -> int:
    source = config.root_dir / SOURCE
    if not source.exists():
        log.error("source not found: %s", source)
        return 1
    det = VlmRegionDetector()

    verdicts = {}
    with fitz.open(source) as pdf:
        matrix = fitz.Matrix(100 / 72, 100 / 72)
        for pno in range(pdf.page_count):
            pix = pdf[pno].get_pixmap(matrix=matrix, alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            img = pin_size(img)
            raw = det.ask(img, PROMPT)
            try:
                m = re.search(r"\{.*\}", raw, re.S)
                v = json.loads(m.group(0))
                flag = bool(v.get("new_report_starts"))
                conf = float(v.get("confidence", 0))
                reason = str(v.get("reason", ""))[:80]
            except Exception:
                flag, conf, reason = False, 0.0, "parse-failure"
            verdicts[pno + 1] = flag
            log.info("page %d: new_report=%s conf=%.2f (%s)",
                     pno + 1, flag, conf, reason)
    page_count = len(verdicts)

    persons, start = [], 1
    for pno in range(2, page_count + 1):
        if verdicts.get(pno, False):
            persons.append([start, pno - 1])
            start = pno
    persons.append([start, page_count])

    draft = {
        "source": SOURCE,
        "confirmed": False,
        "persons": [{"pages": r} for r in persons],
        "ignored_pages": [],
        "_proposed_at": datetime.now(timezone.utc).isoformat(),
        "_proposer": "vlm-draft",
    }
    out = config.root_dir / "configs" / "splits_draft.yaml"
    out.write_text(yaml.safe_dump(draft, sort_keys=False))
    log.info("draft written: %s — %d persons proposed", out, len(persons))
    log.info("YOUR JOB: verify every boundary in a PDF viewer (your 4-6 "
             "page/person prior is the fastest sanity check — any proposed "
             "person with 1-2 or 8+ pages deserves a close look), fix, save "
             "as configs/splits.yaml, set confirmed: true.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
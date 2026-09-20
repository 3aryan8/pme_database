"""Numbered thumbnail grids of every page, so you can mark person-start
pages fast, then spot-check in a real PDF viewer.

Output: data/metadata/contact_sheets/sheet_NN.png  (contains PII — stays
under data/, never enters git)

Usage: uv run python scripts/contact_sheet.py
"""
import argparse

import pymupdf as fitz
from PIL import Image, ImageDraw

from src.utils.config_loader import config

SOURCE = "data/raw/black_dataset.pdf"
THUMB_W, COLS, ROWS = 200, 5, 8


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dpi", type=int, default=60)
    args = ap.parse_args()

    source = config.root_dir / SOURCE
    if not source.exists():
        raise SystemExit(f"source not found: {source}")
    out_dir = config.get_path("metadata_dir") / "contact_sheets"
    out_dir.mkdir(parents=True, exist_ok=True)

    matrix = fitz.Matrix(args.dpi / 72, args.dpi / 72)
    thumbs = []
    with fitz.open(source) as pdf:
        for pno in range(pdf.page_count):
            pix = pdf[pno].get_pixmap(matrix=matrix, alpha=False)
            im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            h = round(im.height * THUMB_W / im.width)
            thumbs.append((pno + 1, im.resize((THUMB_W, h), Image.LANCZOS)))

    thumb_h = max(im.height for _, im in thumbs)
    cell_w, cell_h = THUMB_W + 12, thumb_h + 28
    per_sheet = COLS * ROWS
    for s in range(0, len(thumbs), per_sheet):
        chunk = thumbs[s:s + per_sheet]
        sheet = Image.new("RGB", (cell_w * COLS, cell_h * ROWS), "white")
        draw = ImageDraw.Draw(sheet)
        for i, (pno, im) in enumerate(chunk):
            r, c = divmod(i, COLS)
            x, y = c * cell_w + 6, r * cell_h + 24
            draw.text((x, r * cell_h + 4), f"p.{pno}", fill="red")
            sheet.paste(im, (x, y))
            draw.rectangle([x - 2, y - 2, x + im.width + 2, y + im.height + 2],
                           outline=(180, 180, 180))
        out = out_dir / f"sheet_{s // per_sheet + 1:02d}.png"
        sheet.save(out)
        print(f"wrote {out} (pages {chunk[0][0]}-{chunk[-1][0]})")

    print(f"\n{len(thumbs)} pages total. Mark each person's FIRST page "
          f"(the header page: photo box, typed name/ID), then run "
          f"scripts/make_splits.py --starts ...")


if __name__ == "__main__":
    main()
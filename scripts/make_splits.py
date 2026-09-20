"""Build configs/splits.yaml from a list of person START pages.

Usage:
  uv run python scripts/make_splits.py --starts 1,7,13,19 [--ignore 6,12]

- First start MUST be page 1; starts strictly increasing.
- Each person runs to the page before the next start; last runs to the end.
- Ignored (blank separator) pages are trimmed from range edges only.
- Writes confirmed: false — you MUST spot-check, then flip to true.
"""
import argparse

import pymupdf as fitz
import yaml

from src.utils.config_loader import config

SOURCE = "data/raw/black_dataset.pdf"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--starts", required=True,
                    help="comma-separated 1-based start pages, e.g. 1,7,13")
    ap.add_argument("--ignore", default="",
                    help="comma-separated blank/separator pages to skip")
    args = ap.parse_args()

    starts = [int(s) for s in args.starts.split(",") if s.strip()]
    ignore = sorted({int(s) for s in args.ignore.split(",") if s.strip()})
    if not starts or starts[0] != 1:
        raise SystemExit("first start page must be 1")
    if any(b <= a for a, b in zip(starts, starts[1:])):
        raise SystemExit("start pages must be strictly increasing")

    source = config.root_dir / SOURCE
    with fitz.open(source) as pdf:
        page_count = pdf.page_count
    if starts[-1] > page_count:
        raise SystemExit(f"last start {starts[-1]} exceeds page count {page_count}")

    bounds = starts + [page_count + 1]
    persons = []
    for i in range(len(starts)):
        first, last = bounds[i], bounds[i + 1] - 1
        while first in ignore:
            first += 1
        while last in ignore:
            last -= 1
        if first > last:
            raise SystemExit(f"person {i}: range collapsed — check starts/ignore")
        if any(p in ignore for p in range(first, last + 1)):
            raise SystemExit(f"person {i}: ignored page strictly inside range "
                             f"[{first},{last}] — add a split there or fix ranges")
        persons.append({"pages": [first, last]})

    out = config.root_dir / "configs" / "splits.yaml"
    out.write_text(yaml.safe_dump(
        {"source": SOURCE, "confirmed": False,
         "persons": persons, "ignored_pages": ignore}, sort_keys=False))

    sizes = [p["pages"][1] - p["pages"][0] + 1 for p in persons]
    print(f"wrote {out}: {len(persons)} persons, pages/person "
          f"min={min(sizes)} max={max(sizes)}")
    if min(sizes) < 3 or max(sizes) > 8:
        print("WARNING: sizes outside your 4-6 page/person prior — "
              "re-check those boundaries in the PDF viewer!")
    print("NEXT: verify a few ranges against the PDF, set confirmed: true, "
          "then run: uv run python -m src.assembly.run_assembly")


if __name__ == "__main__":
    main()
"""Loads and validates the person split map (configs/splits.yaml).

Hard-refuses unconfirmed maps at assembly time (never split on a guess)
and structurally validates coverage: every page assigned to exactly one
person (or explicitly ignored).

Two modes:
  pages_per_person: N   — DYNAMIC. Every person occupies exactly N
                          consecutive pages, in page order. The person count
                          is derived from the source PDF's actual page count
                          (page_count / N), so the map stays correct when the
                          merged PDF grows (more PDFs added).
  persons: [...]        — MANUAL. Explicit per-person page ranges
                          (for non-uniform reports).
"""
from pathlib import Path
from typing import List, Tuple

import pymupdf as fitz
import yaml

from src.assembly.id_generator import file_sha256
from src.utils.config_loader import config


class SplitMap:
    def __init__(self, data: dict, source_path: Path, source_sha: str,
                 page_count: int):
        self.source_path = source_path
        self.source_sha = source_sha
        self.page_count = page_count
        self.confirmed: bool = bool(data.get("confirmed", False))
        self.ignored: set = set(data.get("ignored_pages") or [])
        self.pages_per_person: int | None = data.get("pages_per_person")
        if self.pages_per_person is not None:
            if self.ignored:
                raise ValueError(
                    "pages_per_person splits cover every page exactly once — "
                    "ignored_pages is not supported in this mode")
            self.persons = self._dynamic_persons(
                self.pages_per_person, page_count)
        else:
            persons = data.get("persons")
            if persons is None:
                raise ValueError(
                    "splits.yaml must define 'pages_per_person' (equal "
                    "splits) or 'persons' (manual page ranges)")
            self.persons: List[Tuple[int, int, int]] = []
            for i, p in enumerate(persons):
                first, last = p["pages"]
                if not (1 <= first <= last <= page_count):
                    raise ValueError(f"person {i}: invalid range {p['pages']}")
                self.persons.append((i, first, last))
        self._validate_coverage()

    @staticmethod
    def _dynamic_persons(pages_per_person, page_count: int
                         ) -> List[Tuple[int, int, int]]:
        """Equal consecutive splits: person i owns pages (i*N+1)..(i+1)*N."""
        n = pages_per_person
        if not isinstance(n, int) or isinstance(n, bool) or n < 1:
            raise ValueError(
                f"pages_per_person must be a positive integer, got {n!r}")
        if page_count % n != 0:
            raise ValueError(
                f"source PDF has {page_count} pages — not a multiple of "
                f"{n} pages/person; assembly refuses to guess a partial "
                f"person. Fix configs/splits.yaml or the PDF set.")
        count = page_count // n
        return [(i, i * n + 1, (i + 1) * n) for i in range(count)]

    def _validate_coverage(self) -> None:
        covered = sorted(pg for _, f, l in self.persons for pg in range(f, l + 1))
        expected = sorted(
            pg for pg in range(1, self.page_count + 1) if pg not in self.ignored)
        if covered != expected:
            missing = sorted(set(expected) - set(covered))
            dupes = sorted({p for p in covered if covered.count(p) > 1})
            raise ValueError(
                f"split map must cover every page exactly once. "
                f"missing={missing[:10]} duplicated={dupes[:10]}")
        starts = [f for _, f, _ in self.persons]
        if starts != sorted(starts):
            raise ValueError("person ranges must be in ascending page order")

    def split_status(self, person_index: int) -> str:
        return "manually_cleared" if self.confirmed else "flagged"


def load_split_map(source_path=None) -> SplitMap:
    """source_path overrides the splits.yaml 'source' (the merged PDF);
    the split map must then describe that PDF."""
    path = config.root_dir / "configs" / "splits.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Fill it in manually after inspecting the PDF, "
            f"or generate a draft: uv run python -m src.detection.pose_splits")
    data = yaml.safe_load(path.read_text())
    if not data:
        raise ValueError("configs/splits.yaml is empty — fill it in")
    if source_path is not None:
        source_path = Path(source_path).expanduser().resolve()
    else:
        source_path = config.root_dir / data["source"]
    if not source_path.exists():
        raise FileNotFoundError(f"source PDF missing: {source_path}")
    source_sha = file_sha256(source_path)
    with fitz.open(source_path) as pdf:
        page_count = pdf.page_count
    return SplitMap(data, source_path, source_sha, page_count)
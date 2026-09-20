"""Loads and validates the person split map (configs/splits.yaml).

Hard-refuses unconfirmed maps at assembly time (never merge on a guess)
and structurally validates coverage: every page assigned to exactly one
person (or explicitly ignored).
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
        self.persons: List[Tuple[int, int, int]] = []  # (person_index, first, last)
        for i, p in enumerate(data.get("persons") or []):
            first, last = p["pages"]
            if not (1 <= first <= last <= page_count):
                raise ValueError(f"person {i}: invalid range {p['pages']}")
            self.persons.append((i, first, last))
        self._validate_coverage()

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
    """source_path overrides the splits.yaml 'source' (e.g. merged PDF);
    the person boundaries in splits.yaml must then describe that PDF."""
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
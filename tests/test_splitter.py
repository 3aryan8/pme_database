"""Split-map (configs/splits.yaml) contract: dynamic equal splits + manual ranges."""
from pathlib import Path

import pytest

from src.assembly.splitter import SplitMap


def _split(data: dict, page_count: int) -> SplitMap:
    # The constructor does no I/O — a fake source path is fine.
    return SplitMap(data, Path("/fake/source.pdf"), "a" * 64, page_count)


# --- dynamic mode (pages_per_person) ---------------------------------------

def test_dynamic_split_even_pages():
    sm = _split({"pages_per_person": 4, "confirmed": True}, 48)
    assert [p for p in sm.persons] == \
        [(i, i * 4 + 1, (i + 1) * 4) for i in range(12)]
    assert sm.split_status(0) == "manually_cleared"


def test_dynamic_split_derives_person_count_from_page_count():
    """The merged PDF grew (more PDFs added) — person count follows it."""
    sm = _split({"pages_per_person": 4, "confirmed": True}, 12)
    assert len(sm.persons) == 3
    assert sm.persons[-1] == (2, 9, 12)


def test_dynamic_split_refuses_partial_person():
    with pytest.raises(ValueError, match="multiple"):
        _split({"pages_per_person": 4, "confirmed": True}, 50)


def test_dynamic_split_rejects_ignored_pages():
    with pytest.raises(ValueError, match="ignored_pages"):
        _split({"pages_per_person": 4, "ignored_pages": [3]}, 48)


def test_dynamic_split_requires_positive_int():
    for bad in (0, -2, "4"):
        with pytest.raises(ValueError, match="pages_per_person"):
            _split({"pages_per_person": bad}, 48)


# --- manual mode (persons) — still supported --------------------------------

def test_manual_persons_mode_valid_ranges():
    sm = _split({"confirmed": True, "persons": [
        {"pages": [1, 4]}, {"pages": [5, 8]}]}, 8)
    assert sm.persons == [(0, 1, 4), (1, 5, 8)]


def test_manual_persons_mode_coverage_gap():
    with pytest.raises(ValueError, match="cover every page"):
        _split({"confirmed": True, "persons": [
            {"pages": [1, 4]}, {"pages": [6, 8]}]}, 8)


def test_manual_persons_mode_coverage_duplicate():
    with pytest.raises(ValueError, match="cover every page"):
        _split({"confirmed": True, "persons": [
            {"pages": [1, 4]}, {"pages": [5, 5]}, {"pages": [5, 8]}]}, 8)


def test_manual_persons_mode_range_beyond_page_count():
    with pytest.raises(ValueError, match="invalid range"):
        _split({"confirmed": True, "persons": [
            {"pages": [1, 4]}, {"pages": [5, 9]}]}, 8)


def test_neither_mode_defined():
    with pytest.raises(ValueError, match="pages_per_person"):
        _split({"confirmed": True}, 8)


def test_unconfirmed_flag_is_exposed():
    assert _split({"pages_per_person": 4, "confirmed": False}, 8).confirmed is False

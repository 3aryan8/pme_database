"""Tests for report image ingestion + retrieval (four pages per report).

Covers: insertion with four images, correct candidate association,
page numbers preserved, retrieval by candidate ID, no orphans, and
transaction safety when image insertion fails.
"""
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from src.database.config import MAIN_PROJECT_ROOT
from src.database.importer import import_one, to_stored_path
from src.database.models import Base, Candidate, MedicalExamination, ReportImage
from src.database.report_images import find_report_images
from src.database.repository import (
    get_candidate_report_images,
    get_report_images,
)
from src.database.schemas import PMEExtraction

DOC_A = "doc_alpha"
DOC_B = "doc_beta"


def _extraction(
    document_id: str,
    roll_number: str,
    pages: list[int] | None = None,
) -> PMEExtraction:
    return PMEExtraction(
        document_id=document_id,
        fields={
            "page_1_basic_info": {
                "general_details": {
                    "candidate_name": f"CANDIDATE {roll_number}",
                },
                "narrative_details": {"roll_number": roll_number},
            },
        },
        # declared coverage drives the expected page count (default 4,
        # as in configs/splits.yaml for the current dataset)
        pages_covered=[0, 1, 2, 3] if pages is None else pages,
    )


def _make_pages(base, document_id: str, count: int = 4):
    d = base / document_id
    d.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        (d / f"page_{i:04d}.png").write_bytes(b"fake-png")
    return d


@pytest.fixture()
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _counts(session):
    return (
        session.scalar(select(func.count()).select_from(Candidate)),
        session.scalar(select(func.count()).select_from(MedicalExamination)),
        session.scalar(select(func.count()).select_from(ReportImage)),
    )


def test_candidate_inserted_with_four_images(session, monkeypatch, tmp_path):
    monkeypatch.setenv("REPORT_IMAGES_DIR", str(tmp_path))
    _make_pages(tmp_path, DOC_A)

    with session.begin_nested():
        examination, created = import_one(
            session, _extraction(DOC_A, "1111111111"))
    session.commit()

    assert created is True
    assert _counts(session) == (1, 1, 4)
    images = get_report_images(session, examination.id)
    assert [i.page_number for i in images] == [1, 2, 3, 4]
    # stored paths must resolve back to the real files
    for image in images:
        assert Path(image.image_path).is_file()


def test_images_retrieved_by_candidate_id(session, monkeypatch, tmp_path):
    monkeypatch.setenv("REPORT_IMAGES_DIR", str(tmp_path))
    _make_pages(tmp_path, DOC_A)
    with session.begin_nested():
        import_one(session, _extraction(DOC_A, "2222222222"))
    session.commit()

    candidate = session.scalar(
        select(Candidate).where(Candidate.roll_number == "2222222222"))
    images = get_candidate_report_images(session, candidate.id)
    assert [i.page_number for i in images] == [1, 2, 3, 4]
    assert all(i.document_id == DOC_A for i in images)


def test_images_associated_with_correct_candidate(session, monkeypatch, tmp_path):
    monkeypatch.setenv("REPORT_IMAGES_DIR", str(tmp_path))
    _make_pages(tmp_path, DOC_A)
    _make_pages(tmp_path, DOC_B)
    with session.begin_nested():
        import_one(session, _extraction(DOC_A, "3333333331"))
    session.commit()
    with session.begin_nested():
        import_one(session, _extraction(DOC_B, "3333333332"))
    session.commit()

    by_doc = {}
    for doc in (DOC_A, DOC_B):
        candidate = session.scalar(
            select(Candidate).where(Candidate.roll_number ==
                                    ("3333333331" if doc == DOC_A else "3333333332")))
        images = get_candidate_report_images(session, candidate.id)
        by_doc[doc] = {i.id for i in images}
        assert len(images) == 4
        assert all(i.document_id == doc for i in images)
    # disjoint: no image belongs to the wrong candidate
    assert by_doc[DOC_A].isdisjoint(by_doc[DOC_B])


def test_page_numbers_preserved(session, monkeypatch, tmp_path):
    monkeypatch.setenv("REPORT_IMAGES_DIR", str(tmp_path))
    _make_pages(tmp_path, DOC_A)
    with session.begin_nested():
        examination, _ = import_one(
            session, _extraction(DOC_A, "4444444444"))
    session.commit()

    pages = list(
        session.scalars(
            select(ReportImage.page_number)
            .where(ReportImage.examination_id == examination.id)
            .order_by(ReportImage.page_number)
        )
    )
    assert pages == [1, 2, 3, 4]


def test_missing_page_fails_atomically_no_orphans(session, monkeypatch, tmp_path):
    monkeypatch.setenv("REPORT_IMAGES_DIR", str(tmp_path))
    _make_pages(tmp_path, DOC_A, count=3)  # only 3 of the declared 4 pages

    with pytest.raises(FileNotFoundError, match="expected 4"):
        with session.begin_nested():
            import_one(session, _extraction(DOC_A, "5555555555"))
    session.rollback()

    assert _counts(session) == (0, 0, 0)


def test_candidate_inserted_with_six_pages(session, monkeypatch, tmp_path):
    """Pages per person come from splits.yaml (via pages_covered), not a
    hard-coded 4: a 6-page person imports all six."""
    monkeypatch.setenv("REPORT_IMAGES_DIR", str(tmp_path))
    _make_pages(tmp_path, DOC_A, count=6)
    with session.begin_nested():
        examination, created = import_one(
            session,
            _extraction(DOC_A, "7777777777", pages=[0, 1, 2, 3, 4, 5]),
        )
    session.commit()

    assert created is True
    assert _counts(session) == (1, 1, 6)
    images = get_report_images(session, examination.id)
    assert [i.page_number for i in images] == [1, 2, 3, 4, 5, 6]


def test_duplicate_import_no_duplicate_images(session, monkeypatch, tmp_path):
    monkeypatch.setenv("REPORT_IMAGES_DIR", str(tmp_path))
    _make_pages(tmp_path, DOC_A)
    with session.begin_nested():
        examination, created = import_one(
            session, _extraction(DOC_A, "6666666666"))
    session.commit()
    assert created is True

    with session.begin_nested():
        examination2, created2 = import_one(
            session, _extraction(DOC_A, "6666666666"))
    session.commit()

    assert created2 is False
    assert examination.id == examination2.id
    assert _counts(session) == (1, 1, 4)


def test_to_stored_path_relative_inside_project_absolute_outside():
    inside = MAIN_PROJECT_ROOT / "data" / "interim" / "high_res" / "x" / "page_0000.png"
    assert to_stored_path(inside) == "data/interim/high_res/x/page_0000.png"

    outside = Path("/definitely/outside/anywhere.png")
    assert to_stored_path(outside).startswith("/")


def test_find_report_images_count_and_mismatch(tmp_path):
    _make_pages(tmp_path, DOC_A, count=4)
    pairs = find_report_images(DOC_A, base_dir=tmp_path, expected=4)
    assert [n for n, _ in pairs] == [1, 2, 3, 4]
    assert all(p.is_file() for _, p in pairs)

    # N is not hard-coded: a 6-page person (per splits.yaml) works as-is
    _make_pages(tmp_path, "doc_six_pages", count=6)
    pairs = find_report_images("doc_six_pages", base_dir=tmp_path, expected=6)
    assert [n for n, _ in pairs] == [1, 2, 3, 4, 5, 6]

    # declared vs rendered mismatch fails the import (atomic rollback)
    _make_pages(tmp_path, DOC_B, count=2)
    with pytest.raises(FileNotFoundError, match="expected 4"):
        find_report_images(DOC_B, base_dir=tmp_path, expected=4)

    # no rendered pages at all fails
    with pytest.raises(FileNotFoundError, match="no rendered"):
        find_report_images("doc_missing", base_dir=tmp_path, expected=4)

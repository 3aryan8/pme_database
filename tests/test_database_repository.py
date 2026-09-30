"""Tests for live dashboard queries against the normalized database."""
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.database.models import (
    Base,
    Candidate,
    ExtractionRun,
    MedicalExamination,
)
from src.database.repository import (
    get_candidate_directory,
    get_dashboard_stats,
    search_candidates,
)


def test_dashboard_queries_use_current_database_rows():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            candidate = Candidate(
                roll_number="ROLL-1",
                candidate_name="  Candidate Name  ",
                father_name="Father Name",
                date_of_birth=date(1990, 1, 2),
            )
            session.add(candidate)
            session.flush()
            examination = MedicalExamination(
                candidate=candidate,
                medical_examination_date=date(2025, 1, 2),
            )
            session.add(examination)
            session.flush()
            session.add(
                ExtractionRun(
                    examination=examination,
                    document_id="current-document",
                    raw_json={},
                )
            )
            duplicate_examination = MedicalExamination(
                candidate=candidate,
                medical_examination_date=date(2025, 1, 2),
            )
            session.add(duplicate_examination)
            session.flush()
            session.add(
                ExtractionRun(
                    examination=duplicate_examination,
                    document_id="duplicate-current-document",
                    raw_json={},
                )
            )

            old_candidate = Candidate(
                roll_number="ROLL-2",
                candidate_name="Old Candidate",
            )
            session.add(old_candidate)
            session.flush()
            old_examination = MedicalExamination(candidate=old_candidate)
            session.add(old_examination)
            session.flush()
            session.add(
                ExtractionRun(
                    examination=old_examination,
                    document_id="old-document",
                    raw_json={},
                )
            )
            session.flush()

            assert get_dashboard_stats(session) == {
                "candidates": 2,
                "examinations": 3,
            }
            assert get_dashboard_stats(
                session,
                {"current-document", "duplicate-current-document"},
            ) == {
                "candidates": 1,
                "examinations": 1,
            }
            assert {item.roll_number for item in get_candidate_directory(session)} == {
                "ROLL-1",
                "ROLL-2",
            }
            assert search_candidates(
                session,
                "candidate name",
                "FATHER NAME",
                date(1990, 1, 2),
            ) == [candidate]
            assert search_candidates(
                session,
                "Candidate Name",
                "Different Father",
                date(1990, 1, 2),
            ) == []
    finally:
        engine.dispose()

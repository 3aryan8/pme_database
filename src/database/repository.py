# Phase: normalized database access | Input: SQLAlchemy session and query parameters | Output: candidates, examinations, and report data | Command: ``uv run python scripts/generate_report.py``.
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .models import (
    Candidate,
    Declaration,
    Doctor,
    ExtractionRun,
    FitnessClassification,
    MedicalExamination,
    PhysicalExamination,
    PmeCase,
    PmeCaseMeasurement,
    PmeVisionRow,
    ReportImage,
    VisionExamination,
)


def get_candidate_directory(session: Session) -> list[Candidate]:
    """Return candidates with the most recently imported records first."""
    statement = select(Candidate).order_by(
        Candidate.created_at.desc(),
        Candidate.id.desc(),
    )
    return list(session.scalars(statement).all())


def get_dashboard_stats(
    session: Session,
    document_ids: set[str] | None = None,
) -> dict[str, int]:
    """Return candidate and examination counts, optionally source-scoped."""
    if document_ids is None:
        candidates = session.scalar(
            select(func.count()).select_from(Candidate)
        )
        examinations = session.scalar(
            select(func.count()).select_from(MedicalExamination)
        )
    else:
        candidates = session.scalar(
            select(func.count(func.distinct(Candidate.id)))
            .join(Candidate.examinations)
            .join(MedicalExamination.extraction_runs)
            .where(ExtractionRun.document_id.in_(document_ids))
        )
        current_examinations = (
            select(
                MedicalExamination.candidate_id,
                MedicalExamination.medical_examination_date,
            )
            .join(MedicalExamination.extraction_runs)
            .where(ExtractionRun.document_id.in_(document_ids))
            .distinct()
            .subquery()
        )
        examinations = session.scalar(
            select(func.count()).select_from(current_examinations)
        )
    return {
        "candidates": candidates or 0,
        "examinations": examinations or 0,
    }


def search_candidates(
    session: Session,
    candidate_name: str,
    father_name: str,
    date_of_birth,
) -> list[Candidate]:
    """Find candidates by exact, case-insensitive identity fields."""
    statement = (
        select(Candidate)
        .where(
            func.lower(func.trim(Candidate.candidate_name))
            == candidate_name.strip().casefold(),
            func.lower(func.trim(Candidate.father_name))
            == father_name.strip().casefold(),
            Candidate.date_of_birth == date_of_birth,
        )
        .order_by(Candidate.id)
    )
    return list(session.scalars(statement).all())


def get_candidate_by_roll_number(
    session: Session,
    roll_number: str,
) -> Candidate | None:
    """
    Find a candidate using their unique roll number.
    """

    return session.scalar(
        select(Candidate).where(
            Candidate.roll_number == roll_number
        )
    )


def get_candidate_by_id(
    session: Session,
    candidate_id: int,
) -> Candidate | None:
    """
    Find a candidate using the database ID.
    """

    return session.get(Candidate, candidate_id)


def get_examination_by_id(
    session: Session,
    examination_id: int,
) -> MedicalExamination | None:
    """
    Fetch one medical examination with all related PME data.
    """

    statement = (
        select(MedicalExamination)
        .where(
            MedicalExamination.id == examination_id
        )
        .options(
            selectinload(
                MedicalExamination.candidate
            ),
            selectinload(
                MedicalExamination.examining_doctor
            ),
            selectinload(
                MedicalExamination.pme_case
            ).selectinload(
                PmeCase.measurements
            ),
            selectinload(
                MedicalExamination.pme_case
            ).selectinload(
                PmeCase.vision_rows
            ),
            selectinload(
                MedicalExamination.vision
            ),
            selectinload(
                MedicalExamination.physical
            ),
            selectinload(
                MedicalExamination.fitness
            ),
            selectinload(
                MedicalExamination.declarations
            ),
            selectinload(
                MedicalExamination.extraction_runs
            ),
        )
    )

    return session.scalar(statement)


def get_latest_examination_for_candidate(
    session: Session,
    candidate_id: int,
) -> MedicalExamination | None:
    """
    Fetch the latest medical examination
    belonging to a candidate.
    """

    statement = (
        select(MedicalExamination)
        .where(
            MedicalExamination.candidate_id
            == candidate_id
        )
        .order_by(
            MedicalExamination.medical_examination_date.desc(),
            MedicalExamination.id.desc(),
        )
        .limit(1)
        .options(
            selectinload(
                MedicalExamination.candidate
            ),
            selectinload(
                MedicalExamination.examining_doctor
            ),
            selectinload(
                MedicalExamination.pme_case
            ).selectinload(
                PmeCase.measurements
            ),
            selectinload(
                MedicalExamination.pme_case
            ).selectinload(
                PmeCase.vision_rows
            ),
            selectinload(
                MedicalExamination.vision
            ),
            selectinload(
                MedicalExamination.physical
            ),
            selectinload(
                MedicalExamination.fitness
            ),
            selectinload(
                MedicalExamination.declarations
            ),
            selectinload(
                MedicalExamination.extraction_runs
            ),
        )
    )

    return session.scalar(statement)


def get_examination_by_roll_number(
    session: Session,
    roll_number: str,
) -> MedicalExamination | None:
    """
    Fetch the latest medical examination
    for a candidate using roll number.
    """

    statement = (
        select(MedicalExamination)
        .join(
            MedicalExamination.candidate
        )
        .where(
            Candidate.roll_number == roll_number
        )
        .order_by(
            MedicalExamination.medical_examination_date.desc(),
            MedicalExamination.id.desc(),
        )
        .limit(1)
        .options(
            selectinload(
                MedicalExamination.candidate
            ),
            selectinload(
                MedicalExamination.examining_doctor
            ),
            selectinload(
                MedicalExamination.pme_case
            ).selectinload(
                PmeCase.measurements
            ),
            selectinload(
                MedicalExamination.pme_case
            ).selectinload(
                PmeCase.vision_rows
            ),
            selectinload(
                MedicalExamination.vision
            ),
            selectinload(
                MedicalExamination.physical
            ),
            selectinload(
                MedicalExamination.fitness
            ),
            selectinload(
                MedicalExamination.declarations
            ),
            selectinload(
                MedicalExamination.extraction_runs
            ),
        )
    )

    return session.scalar(statement)


def get_pme_case(
    session: Session,
    examination_id: int,
) -> PmeCase | None:
    """
    Fetch the PME case associated with
    a medical examination.
    """

    statement = (
        select(PmeCase)
        .where(
            PmeCase.examination_id
            == examination_id
        )
        .options(
            selectinload(
                PmeCase.measurements
            ),
            selectinload(
                PmeCase.vision_rows
            ),
        )
    )

    return session.scalar(statement)


def get_pme_measurements(
    session: Session,
    pme_case_id: int,
) -> list[PmeCaseMeasurement]:
    """
    Fetch all generic Page 2 handwritten
    measurements belonging to a PME case.
    """

    statement = (
        select(PmeCaseMeasurement)
        .where(
            PmeCaseMeasurement.pme_case_id
            == pme_case_id
        )
        .order_by(
            PmeCaseMeasurement.id
        )
    )

    return list(
        session.scalars(statement).all()
    )


def get_pme_vision_rows(
    session: Session,
    pme_case_id: int,
) -> list[PmeVisionRow]:
    """Fetch Page 2 side-by-side vision rows for a PME case."""
    statement = (
        select(PmeVisionRow)
        .where(PmeVisionRow.pme_case_id == pme_case_id)
        .order_by(PmeVisionRow.id)
    )

    return list(session.scalars(statement).all())


def get_vision_examination(
    session: Session,
    examination_id: int,
) -> VisionExamination | None:
    """
    Fetch the vision examination.
    """

    statement = (
        select(VisionExamination)
        .where(
            VisionExamination.examination_id
            == examination_id
        )
    )

    return session.scalar(statement)


def get_physical_examination(
    session: Session,
    examination_id: int,
) -> PhysicalExamination | None:
    """
    Fetch the physical examination.
    """

    statement = (
        select(PhysicalExamination)
        .where(
            PhysicalExamination.examination_id
            == examination_id
        )
    )

    return session.scalar(statement)


def get_fitness_classification(
    session: Session,
    examination_id: int,
) -> FitnessClassification | None:
    """
    Fetch the fitness classification.
    """

    statement = (
        select(FitnessClassification)
        .where(
            FitnessClassification.examination_id
            == examination_id
        )
    )

    return session.scalar(statement)


def get_declarations(
    session: Session,
    examination_id: int,
) -> list[Declaration]:
    """
    Fetch all declarations for an examination.
    """

    statement = (
        select(Declaration)
        .where(
            Declaration.examination_id
            == examination_id
        )
        .order_by(
            Declaration.part,
            Declaration.question_no,
        )
    )

    return list(
        session.scalars(statement).all()
    )


def get_doctor(
    session: Session,
    doctor_id: int,
) -> Doctor | None:
    """
    Fetch a doctor by database ID.
    """

    return session.get(
        Doctor,
        doctor_id,
    )


def get_extraction_runs(
    session: Session,
    examination_id: int,
) -> list[ExtractionRun]:
    """
    Fetch all extraction runs associated
    with an examination.
    """

    statement = (
        select(ExtractionRun)
        .where(
            ExtractionRun.examination_id
            == examination_id
        )
        .order_by(
            ExtractionRun.id.desc()
        )
    )

    return list(
        session.scalars(statement).all()
    )


def get_examination_by_document_id(
    session: Session,
    document_id: str,
) -> MedicalExamination | None:
    """
    Fetch the examination associated with
    an extraction document ID.
    """

    statement = (
        select(ExtractionRun)
        .where(
            ExtractionRun.document_id
            == document_id
        )
        .options(
            selectinload(
                ExtractionRun.examination
            ).selectinload(
                MedicalExamination.candidate
            ),
            selectinload(
                ExtractionRun.examination
            ).selectinload(
                MedicalExamination.examining_doctor
            ),
            selectinload(
                ExtractionRun.examination
            ).selectinload(
                MedicalExamination.pme_case
            ).selectinload(
                PmeCase.measurements
            ),
            selectinload(
                ExtractionRun.examination
            ).selectinload(
                MedicalExamination.pme_case
            ).selectinload(
                PmeCase.vision_rows
            ),
            selectinload(
                ExtractionRun.examination
            ).selectinload(
                MedicalExamination.vision
            ),
            selectinload(
                ExtractionRun.examination
            ).selectinload(
                MedicalExamination.physical
            ),
            selectinload(
                ExtractionRun.examination
            ).selectinload(
                MedicalExamination.fitness
            ),
            selectinload(
                ExtractionRun.examination
            ).selectinload(
                MedicalExamination.declarations
            ),
            selectinload(
                ExtractionRun.examination
            ).selectinload(
                MedicalExamination.extraction_runs
            ),
        )
    )

    extraction_run = session.scalar(statement)

    if extraction_run is None:
        return None

    return extraction_run.examination


def get_report_images(
    session: Session,
    examination_id: int,
) -> list[ReportImage]:
    """
    Fetch the report page images for an examination,
    in page order (1..N, where N = that person's splits.yaml page count).
    """

    statement = (
        select(ReportImage)
        .where(
            ReportImage.examination_id == examination_id
        )
        .order_by(
            ReportImage.page_number
        )
    )

    return list(
        session.scalars(statement).all()
    )


def get_candidate_report_images(
    session: Session,
    candidate_id: int,
) -> list[ReportImage]:
    """
    Fetch the report page images for a candidate's
    latest examination (the report record).
    """

    examination = get_latest_examination_for_candidate(
        session,
        candidate_id,
    )

    if examination is None:
        return []

    return get_report_images(
        session,
        examination.id,
    )


def get_all_candidates(
    session: Session,
) -> list[Candidate]:
    """
    Fetch all candidates ordered by roll number.
    """

    statement = (
        select(Candidate)
        .order_by(
            Candidate.roll_number
        )
    )

    return list(
        session.scalars(statement).all()
    )


def get_all_examinations(
    session: Session,
) -> list[MedicalExamination]:
    """
    Fetch all medical examinations.
    """

    statement = (
        select(MedicalExamination)
        .order_by(
            MedicalExamination.id
        )
    )

    return list(
        session.scalars(statement).all()
    )
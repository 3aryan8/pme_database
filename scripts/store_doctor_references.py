"""Seed doctor signature/stamp references from detected report regions."""

from __future__ import annotations

from sqlalchemy import select

from src.database.database import get_session, init_db
from src.database.doctor_assets import save_detected_doctor_assets
from src.database.models import MedicalExamination


def main() -> int:
    init_db()
    saved = 0
    skipped = 0
    with get_session() as session:
        examinations = session.scalars(
            select(MedicalExamination).where(
                MedicalExamination.examining_doctor_id.is_not(None)
            )
        ).all()
        for examination in examinations:
            if not examination.extraction_runs or examination.examining_doctor is None:
                skipped += 1
                continue
            extraction = max(
                examination.extraction_runs,
                key=lambda run: run.id,
            )
            if save_detected_doctor_assets(
                session,
                examination.examining_doctor,
                examination.candidate,
                extraction.document_id,
            ):
                saved += 1
            else:
                skipped += 1
        session.commit()

    print(f"Doctor reference records saved: {saved}; skipped: {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
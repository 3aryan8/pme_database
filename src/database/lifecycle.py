from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .models import ExaminationPageStatus, ExaminationStatusEvent, MedicalExamination


EXAMINATION_TRANSITIONS = {
    "UPLOADED": {"PROCESSING", "FAILED"},
    "PROCESSING": {"PARTIALLY_EXTRACTED", "PENDING_REVIEW", "FAILED"},
    "PARTIALLY_EXTRACTED": {"PROCESSING", "PENDING_REVIEW", "FAILED"},
    "PENDING_REVIEW": {"PROCESSING", "VERIFIED", "FAILED"},
    "VERIFIED": {"PENDING_REVIEW", "COMPLETED"},
    "FAILED": {"UPLOADED", "PROCESSING"},
    "COMPLETED": set(),
}
PAGE_TRANSITIONS = {
    "NOT_STARTED": {"PROCESSING"},
    "PROCESSING": {"PARTIALLY_EXTRACTED", "PENDING_REVIEW", "FAILED"},
    "PARTIALLY_EXTRACTED": {"PROCESSING", "PENDING_REVIEW", "FAILED"},
    "PENDING_REVIEW": {"PROCESSING", "VERIFIED", "FAILED"},
    "VERIFIED": {"PENDING_REVIEW"},
    "FAILED": {"NOT_STARTED", "PROCESSING"},
}


def transition_examination_status(
    session: Session,
    examination_id: int,
    new_status: str,
    *,
    actor: str,
    reason: str | None = None,
) -> MedicalExamination:
    examination = session.get(MedicalExamination, examination_id)
    if examination is None:
        raise LookupError("Medical examination not found")
    old_status = examination.overall_status
    if new_status not in EXAMINATION_TRANSITIONS.get(old_status, set()):
        raise ValueError(f"Invalid examination status transition: {old_status} -> {new_status}")
    if new_status == "COMPLETED":
        verified_pages = {
            page.page_number
            for page in examination.page_statuses
            if page.status == "VERIFIED"
        }
        if verified_pages != {1, 2, 3, 4}:
            raise ValueError("All four page sections must be verified before completion")
    examination.overall_status = new_status
    session.add(
        ExaminationStatusEvent(
            examination_id=examination_id,
            from_status=old_status,
            to_status=new_status,
            actor=actor,
            reason=reason,
            changed_at=datetime.now(timezone.utc),
        )
    )
    session.flush()
    return examination


def transition_page_status(
    session: Session,
    examination_id: int,
    page_number: int,
    new_status: str,
    *,
    error_detail: str | None = None,
) -> ExaminationPageStatus:
    if page_number not in {1, 2, 3, 4}:
        raise ValueError("Page number must be from 1 through 4")
    page = session.get(ExaminationPageStatus, (examination_id, page_number))
    if page is None:
        raise LookupError("Examination page status not found")
    if new_status not in PAGE_TRANSITIONS.get(page.status, set()):
        raise ValueError(f"Invalid page status transition: {page.status} -> {new_status}")
    now = datetime.now(timezone.utc)
    if new_status == "PROCESSING":
        page.started_at = now
        page.completed_at = None
    elif new_status in {"PENDING_REVIEW", "VERIFIED", "FAILED"}:
        page.completed_at = now
    page.status = new_status
    page.error_detail = error_detail
    session.flush()
    return page
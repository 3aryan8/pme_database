# Phase: normalized database model | Input: validated extraction data | Output: SQLAlchemy table mappings | Command: ``uv run python -m src.database.run_database --help``.
from __future__ import annotations
from datetime import date, datetime
from typing import Any
from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, JSON, LargeBinary, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase): pass
class Timestamps:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

class Candidate(Timestamps, Base):
    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(primary_key=True)

    roll_number: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
    )

    candidate_name: Mapped[str | None] = mapped_column(String(200))
    father_name: Mapped[str | None] = mapped_column(String(200))
    date_of_birth: Mapped[date | None] = mapped_column(Date)

    recruitment_cen: Mapped[str | None] = mapped_column(String(50))
    doctor_id: Mapped[int | None] = mapped_column(
        ForeignKey("doctors.id"),
        nullable=True,
        index=True,
    )

    doctor: Mapped["Doctor | None"] = relationship(back_populates="candidates")

    examinations: Mapped[list["MedicalExamination"]] = relationship(
        back_populates="candidate",
        cascade="all, delete-orphan",
    )

class Doctor(Timestamps, Base):
    __tablename__ = "doctors"
    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    full_name_hindi: Mapped[str | None] = mapped_column(String(200), nullable=True)
    full_name_english: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    designation: Mapped[str | None] = mapped_column(String(200), nullable=True)
    doctor_role: Mapped[str|None] = mapped_column(String(100))
    signature_image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    stamp_image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    signature_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    stamp_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    candidates: Mapped[list[Candidate]] = relationship(back_populates="doctor")
    examinations: Mapped[list["MedicalExamination"]] = relationship(back_populates="examining_doctor")

    __table_args__ = (
        UniqueConstraint(
            "full_name_english",
            "designation",
            name="uq_doctor_name_designation",
        ),
    )

class DoctorIdentification(Timestamps, Base):
    __tablename__ = "doctor_identifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False, index=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id"), nullable=False, index=True)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    identification_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    stamp_detected: Mapped[bool | None] = mapped_column(Boolean, default=False, nullable=True)
    signature_detected: Mapped[bool | None] = mapped_column(Boolean, default=False, nullable=True)
    signature_image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    stamp_image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    review_status: Mapped[str | None] = mapped_column(String(40), nullable=True)

class MedicalExamination(Timestamps, Base):
    __tablename__ = "medical_examinations"
    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False, index=True)
    dv_date: Mapped[date|None] = mapped_column(Date)
    medical_examination_date: Mapped[date|None] = mapped_column(Date, index=True)
    candidate_declaration_date: Mapped[date | None] = mapped_column(Date)
    overall_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="UPLOADED", server_default="PENDING_REVIEW"
    )
    medical_class: Mapped[str|None] = mapped_column(String(100))
    identification_marks: Mapped[str|None] = mapped_column(Text)
    examining_doctor_id: Mapped[int|None] = mapped_column(ForeignKey("doctors.id"))
    candidate: Mapped[Candidate] = relationship(back_populates="examinations")
    examining_doctor: Mapped[Doctor|None] = relationship(back_populates="examinations")
    pme_case: Mapped["PmeCase|None"] = relationship(back_populates="examination", uselist=False, cascade="all, delete-orphan")
    vision: Mapped["VisionExamination|None"] = relationship(back_populates="examination", uselist=False, cascade="all, delete-orphan")
    physical: Mapped["PhysicalExamination|None"] = relationship(back_populates="examination", uselist=False, cascade="all, delete-orphan")
    fitness: Mapped["FitnessClassification|None"] = relationship(back_populates="examination", uselist=False, cascade="all, delete-orphan")
    declarations: Mapped[list["Declaration"]] = relationship(back_populates="examination", cascade="all, delete-orphan")
    extraction_runs: Mapped[list["ExtractionRun"]] = relationship(back_populates="examination", cascade="all, delete-orphan")
    report_images: Mapped[list["ReportImage"]] = relationship(back_populates="examination", cascade="all, delete-orphan")
    page_statuses: Mapped[list["ExaminationPageStatus"]] = relationship(back_populates="examination", cascade="all, delete-orphan")
    page_1: Mapped["ExaminationPage1 | None"] = relationship(back_populates="examination", uselist=False, cascade="all, delete-orphan")
    page_4: Mapped["ExaminationPage4 | None"] = relationship(back_populates="examination", uselist=False, cascade="all, delete-orphan")
    authentication_records: Mapped[list["ExaminationAuthentication"]] = relationship(back_populates="examination", cascade="all, delete-orphan")
    examination_documents: Mapped[list["ExaminationDocument"]] = relationship(back_populates="examination", cascade="all, delete-orphan")
    extracted_field_values: Mapped[list["ExtractedFieldValue"]] = relationship(back_populates="examination", cascade="all, delete-orphan")
    status_events: Mapped[list["ExaminationStatusEvent"]] = relationship(back_populates="examination", cascade="all, delete-orphan")

class PmeCase(Base):
    __tablename__ = "pme_cases"

    id: Mapped[int] = mapped_column(primary_key=True)

    examination_id: Mapped[int] = mapped_column(
        ForeignKey("medical_examinations.id"),
        unique=True,
        nullable=False,
    )

    urine: Mapped[str | None] = mapped_column(String(50))
    sugar: Mapped[str | None] = mapped_column(String(50))
    alb: Mapped[str | None] = mapped_column(String(50))

    chest_xray_result: Mapped[str | None] = mapped_column(Text)
    advice: Mapped[str | None] = mapped_column(Text)
    handwritten_remarks: Mapped[str | None] = mapped_column(Text)

    examination: Mapped[MedicalExamination] = relationship(
        back_populates="pme_case"
    )

    measurements: Mapped[list["PmeCaseMeasurement"]] = relationship(
        back_populates="pme_case",
        cascade="all, delete-orphan",
    )

    vision_rows: Mapped[list["PmeVisionRow"]] = relationship(
        back_populates="pme_case",
        cascade="all, delete-orphan",
    )


class PmeVisionRow(Base):
    """One row of the Page 2 side-by-side measurement table."""

    __tablename__ = "pme_vision_rows"

    id: Mapped[int] = mapped_column(primary_key=True)

    pme_case_id: Mapped[int] = mapped_column(
        ForeignKey("pme_cases.id"),
        nullable=False,
        index=True,
    )

    row_label: Mapped[str | None] = mapped_column(String(100))

    right_value: Mapped[str | None] = mapped_column(String(100))

    left_value: Mapped[str | None] = mapped_column(String(100))
    right_normalized_value: Mapped[str | None] = mapped_column(String(100))
    left_normalized_value: Mapped[str | None] = mapped_column(String(100))
    unit: Mapped[str | None] = mapped_column(String(40))
    source_pdf_page_number: Mapped[int | None] = mapped_column(Integer)

    pme_case: Mapped[PmeCase] = relationship(back_populates="vision_rows")


class ExaminationPageStatus(Base):
    __tablename__ = "examination_page_status"

    examination_id: Mapped[int] = mapped_column(
        ForeignKey("medical_examinations.id", ondelete="CASCADE"), primary_key=True
    )
    page_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="NOT_STARTED", server_default="NOT_STARTED"
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_detail: Mapped[str | None] = mapped_column(Text)
    examination: Mapped[MedicalExamination] = relationship(back_populates="page_statuses")

    __table_args__ = (
        CheckConstraint("page_number BETWEEN 1 AND 4", name="ck_page_status_number"),
        CheckConstraint(
            "status IN ('NOT_STARTED','PROCESSING','PARTIALLY_EXTRACTED','PENDING_REVIEW','VERIFIED','FAILED')",
            name="ck_page_status_value",
        ),
    )


class ExaminationPage1(Base):
    """Immutable page-one candidate facts for one specific examination."""

    __tablename__ = "examination_page_1"

    examination_id: Mapped[int] = mapped_column(
        ForeignKey("medical_examinations.id", ondelete="CASCADE"), primary_key=True
    )
    roll_number: Mapped[str | None] = mapped_column(String(50))
    candidate_name: Mapped[str | None] = mapped_column(String(200))
    father_name: Mapped[str | None] = mapped_column(String(200))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    dv_date: Mapped[date | None] = mapped_column(Date)
    medical_examination_date: Mapped[date | None] = mapped_column(Date)
    recruitment_cen: Mapped[str | None] = mapped_column(String(50))
    post_name: Mapped[str | None] = mapped_column(String(200))
    candidate_class: Mapped[str | None] = mapped_column(String(100))
    age_raw: Mapped[str | None] = mapped_column(String(50))
    memo_number: Mapped[str | None] = mapped_column(String(100))
    addressee_or_hospital: Mapped[str | None] = mapped_column(Text)
    permanent_identification_marks: Mapped[str | None] = mapped_column(Text)
    station: Mapped[str | None] = mapped_column(String(200))
    station_date: Mapped[date | None] = mapped_column(Date)
    examination: Mapped[MedicalExamination] = relationship(back_populates="page_1")

    __table_args__ = (
        Index("ix_examination_page_1_candidate_class", "candidate_class"),
    )


class ExaminationPage4(Base):
    """Candidate particulars repeated on the declaration page."""

    __tablename__ = "examination_page_4"

    examination_id: Mapped[int] = mapped_column(
        ForeignKey("medical_examinations.id", ondelete="CASCADE"), primary_key=True
    )
    candidate_name: Mapped[str | None] = mapped_column(String(200))
    father_name: Mapped[str | None] = mapped_column(String(200))
    roll_number: Mapped[str | None] = mapped_column(String(50))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    mobile_number_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    email_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    permanent_identification_marks: Mapped[str | None] = mapped_column(Text)
    declaration_date: Mapped[date | None] = mapped_column(Date)
    examination: Mapped[MedicalExamination] = relationship(back_populates="page_4")


class PmeCaseMeasurement(Base):
    __tablename__ = "pme_case_measurements"

    id: Mapped[int] = mapped_column(primary_key=True)

    pme_case_id: Mapped[int] = mapped_column(
        ForeignKey("pme_cases.id"),
        nullable=False,
        index=True,
    )

    row_label: Mapped[str | None] = mapped_column(
        String(100)
    )

    column_1: Mapped[str | None] = mapped_column(
        String(100)
    )

    column_2: Mapped[str | None] = mapped_column(
        String(100)
    )

    raw_text: Mapped[str | None] = mapped_column(
        Text
    )
    normalized_value: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(40))
    source_pdf_page_number: Mapped[int | None] = mapped_column(Integer)

    pme_case: Mapped[PmeCase] = relationship(
        back_populates="measurements"
    )

class VisionExamination(Base):
    __tablename__ = "vision_examinations"
    id: Mapped[int] = mapped_column(primary_key=True)
    examination_id: Mapped[int] = mapped_column(ForeignKey("medical_examinations.id"), unique=True, nullable=False)
    right_distance_uncorrected: Mapped[str|None] = mapped_column(String(20)); right_distance_corrected: Mapped[str|None] = mapped_column(String(20))
    right_near_uncorrected: Mapped[str|None] = mapped_column(String(20)); right_near_corrected: Mapped[str|None] = mapped_column(String(20))
    right_glasses_s: Mapped[str|None] = mapped_column(String(20)); right_glasses_c: Mapped[str|None] = mapped_column(String(20)); right_glasses_a: Mapped[str|None] = mapped_column(String(20))
    left_distance_uncorrected: Mapped[str|None] = mapped_column(String(20)); left_distance_corrected: Mapped[str|None] = mapped_column(String(20))
    left_near_uncorrected: Mapped[str|None] = mapped_column(String(20)); left_near_corrected: Mapped[str|None] = mapped_column(String(20))
    left_glasses_s: Mapped[str|None] = mapped_column(String(20)); left_glasses_c: Mapped[str|None] = mapped_column(String(20)); left_glasses_a: Mapped[str|None] = mapped_column(String(20))
    color_perception: Mapped[str|None] = mapped_column(String(50)); binocular_vision: Mapped[str|None] = mapped_column(String(100)); night_vision: Mapped[str|None] = mapped_column(String(50)); field_of_vision: Mapped[str|None] = mapped_column(String(100))
    examination: Mapped[MedicalExamination] = relationship(back_populates="vision")

class PhysicalExamination(Base):
    __tablename__ = "physical_examinations"
    id: Mapped[int] = mapped_column(primary_key=True)
    examination_id: Mapped[int] = mapped_column(ForeignKey("medical_examinations.id"), unique=True, nullable=False)
    urine: Mapped[str|None] = mapped_column(String(100)); hearing: Mapped[str|None] = mapped_column(String(100)); pr: Mapped[str|None] = mapped_column(String(100)); bp: Mapped[str|None] = mapped_column(String(100))
    cvs: Mapped[str|None] = mapped_column(String(255)); rs: Mapped[str|None] = mapped_column(String(255)); pia: Mapped[str|None] = mapped_column(String(255)); spine: Mapped[str|None] = mapped_column(String(255))
    heart: Mapped[str|None] = mapped_column(String(255)); lungs: Mapped[str|None] = mapped_column(String(255)); general_physical_examination: Mapped[str|None] = mapped_column(Text)
    examination: Mapped[MedicalExamination] = relationship(back_populates="physical")

class FitnessClassification(Base):
    __tablename__ = "fitness_classifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    examination_id: Mapped[int] = mapped_column(ForeignKey("medical_examinations.id"), unique=True, nullable=False)
    fit_in_class: Mapped[str|None] = mapped_column(String(100)); unfit_in_class: Mapped[str|None] = mapped_column(String(100))
    examination: Mapped[MedicalExamination] = relationship(back_populates="fitness")

class Declaration(Base):
    __tablename__ = "declarations"

    id: Mapped[int] = mapped_column(primary_key=True)

    examination_id: Mapped[int] = mapped_column(
        ForeignKey("medical_examinations.id"),
        nullable=False,
        index=True,
    )

    part: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    question_no: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    answer: Mapped[str | None] = mapped_column(
        String(100),
    )

    examination: Mapped[MedicalExamination] = relationship(
        back_populates="declarations"
    )

    __table_args__ = (
        UniqueConstraint(
            "examination_id",
            "part",
            "question_no",
            name="uq_declaration_question",
        ),
    )

class ReportImage(Base):
    """One rendered report page, stored for visual verification of extraction.

    One row per rendered page; a person report has as many pages as
    configs/splits.yaml assigns (N — historically 4). page_number is the
    1-based report page (1..N). Tied to the examination (the report record)
    rather than the candidate, because a candidate may have several
    examinations and each rendered set belongs to one specific report.
    """
    __tablename__ = "report_images"

    id: Mapped[int] = mapped_column(primary_key=True)

    examination_id: Mapped[int] = mapped_column(
        ForeignKey("medical_examinations.id"),
        nullable=False,
        index=True,
    )

    page_number: Mapped[int] = mapped_column(nullable=False)
    source_pdf_page_number: Mapped[int | None] = mapped_column(Integer)

    # Where the image file lives (path at import time).
    image_path: Mapped[str] = mapped_column(String(500), nullable=False)

    # Provenance: which extraction document this render came from.
    document_id: Mapped[str | None] = mapped_column(String(255))

    examination: Mapped[MedicalExamination] = relationship(back_populates="report_images")

    __table_args__ = (
        UniqueConstraint(
            "examination_id",
            "page_number",
            name="uq_report_image_page",
        ),
    )


class ExtractionRun(Base):
    __tablename__ = "extraction_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    examination_id: Mapped[int] = mapped_column(ForeignKey("medical_examinations.id"), nullable=False, index=True)
    document_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    model_name: Mapped[str|None] = mapped_column(String(255)); extracted_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True)); raw_json: Mapped[dict[str,Any]] = mapped_column(JSON, nullable=False)
    examination: Mapped[MedicalExamination] = relationship(back_populates="extraction_runs")


class SourceDocument(Base):
    __tablename__ = "source_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    examination_links: Mapped[list["ExaminationDocument"]] = relationship(back_populates="source_document")
    pages: Mapped[list["SourceDocumentPage"]] = relationship(back_populates="source_document", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("file_size_bytes >= 0", name="ck_source_document_size"),
    )


class ExaminationDocument(Base):
    __tablename__ = "examination_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    examination_id: Mapped[int] = mapped_column(
        ForeignKey("medical_examinations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_documents.id"), nullable=True, index=True
    )
    form_page_number: Mapped[int | None] = mapped_column(Integer)
    source_pdf_page_number: Mapped[int | None] = mapped_column(Integer)
    asset_type: Mapped[str] = mapped_column(String(40), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    verification_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="UNVERIFIED", server_default="UNVERIFIED"
    )
    examination: Mapped[MedicalExamination] = relationship(back_populates="examination_documents")
    source_document: Mapped[SourceDocument | None] = relationship(back_populates="examination_links")

    __table_args__ = (
        CheckConstraint(
            "form_page_number IS NULL OR form_page_number BETWEEN 1 AND 4",
            name="ck_document_form_page",
        ),
        CheckConstraint(
            "source_pdf_page_number IS NULL OR source_pdf_page_number >= 1",
            name="ck_document_source_page",
        ),
        CheckConstraint("file_size_bytes >= 0", name="ck_examination_document_size"),
        CheckConstraint(
            "verification_status IN ('MISSING','UNVERIFIED','PENDING_REVIEW','VERIFIED','REJECTED')",
            name="ck_document_verification_status",
        ),
        UniqueConstraint(
            "examination_id", "asset_type", "form_page_number", "sha256",
            name="uq_examination_document_evidence",
        ),
    )


class SourceDocumentPage(Base):
    __tablename__ = "source_document_pages"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_document_id: Mapped[int] = mapped_column(
        ForeignKey("source_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_pdf_page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    page_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    examination_id: Mapped[int | None] = mapped_column(
        ForeignKey("medical_examinations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    packet_index: Mapped[int | None] = mapped_column(Integer)
    form_page_number: Mapped[int | None] = mapped_column(Integer)
    supplemental_kind: Mapped[str | None] = mapped_column(String(80))
    source_document: Mapped[SourceDocument] = relationship(back_populates="pages")

    __table_args__ = (
        CheckConstraint("source_pdf_page_number >= 1", name="ck_source_page_number"),
        CheckConstraint(
            "page_kind IN ('CANDIDATE_FORM','SUPPLEMENTAL','UNCLASSIFIED')",
            name="ck_source_page_kind",
        ),
        CheckConstraint(
            "(page_kind = 'CANDIDATE_FORM' AND form_page_number BETWEEN 1 AND 4 AND "
            "(examination_id IS NOT NULL OR packet_index IS NOT NULL)) OR "
            "(page_kind != 'CANDIDATE_FORM' AND examination_id IS NULL AND "
            "packet_index IS NULL AND form_page_number IS NULL)",
            name="ck_source_page_assignment",
        ),
        UniqueConstraint(
            "source_document_id", "source_pdf_page_number", name="uq_source_document_page"
        ),
        UniqueConstraint(
            "examination_id", "form_page_number", name="uq_exam_form_page"
        ),
    )


class ExaminationAuthentication(Base):
    __tablename__ = "examination_authentication"

    id: Mapped[int] = mapped_column(primary_key=True)
    examination_id: Mapped[int] = mapped_column(
        ForeignKey("medical_examinations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_pdf_page_number: Mapped[int | None] = mapped_column(Integer)
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False, default="UNKNOWN")
    doctor_id: Mapped[int | None] = mapped_column(ForeignKey("doctors.id"))
    observed_name: Mapped[str | None] = mapped_column(String(200))
    designation: Mapped[str | None] = mapped_column(String(200))
    registration_number: Mapped[str | None] = mapped_column(String(100))
    signed_date: Mapped[date | None] = mapped_column(Date)
    signature_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="UNVERIFIED", server_default="UNVERIFIED"
    )
    stamp_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="UNVERIFIED", server_default="UNVERIFIED"
    )
    signature_document_id: Mapped[int | None] = mapped_column(ForeignKey("examination_documents.id"))
    stamp_document_id: Mapped[int | None] = mapped_column(ForeignKey("examination_documents.id"))
    examination: Mapped[MedicalExamination] = relationship(back_populates="authentication_records")

    __table_args__ = (
        CheckConstraint("page_number BETWEEN 1 AND 4", name="ck_auth_form_page"),
        CheckConstraint(
            "source_pdf_page_number IS NULL OR source_pdf_page_number >= 1",
            name="ck_auth_source_page",
        ),
        CheckConstraint(
            "actor_role IN ('MEDICAL_EXAMINER','ISSUING_OFFICIAL','CANDIDATE','UNKNOWN')",
            name="ck_auth_actor_role",
        ),
        CheckConstraint(
            "signature_status IN ('MISSING','UNVERIFIED','PENDING_REVIEW','VERIFIED','REJECTED')",
            name="ck_auth_signature_status",
        ),
        CheckConstraint(
            "stamp_status IN ('MISSING','UNVERIFIED','PENDING_REVIEW','VERIFIED','REJECTED')",
            name="ck_auth_stamp_status",
        ),
    )


class ExtractedFieldValue(Base):
    __tablename__ = "extracted_field_values"

    id: Mapped[int] = mapped_column(primary_key=True)
    examination_id: Mapped[int] = mapped_column(
        ForeignKey("medical_examinations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    extraction_run_id: Mapped[int] = mapped_column(
        ForeignKey("extraction_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field_name: Mapped[str] = mapped_column(String(200), nullable=False)
    form_page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_pdf_page_number: Mapped[int | None] = mapped_column(Integer)
    extracted_value: Mapped[Any | None] = mapped_column(JSON)
    normalized_value: Mapped[Any | None] = mapped_column(JSON)
    confidence: Mapped[float | None] = mapped_column(Float)
    validation_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="PENDING", server_default="PENDING"
    )
    human_verification_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="PENDING", server_default="PENDING"
    )
    bounding_box: Mapped[list[float] | None] = mapped_column(JSON)
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("extracted_field_values.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    examination: Mapped[MedicalExamination] = relationship(back_populates="extracted_field_values")

    __table_args__ = (
        CheckConstraint("form_page_number BETWEEN 1 AND 4", name="ck_field_form_page"),
        CheckConstraint(
            "source_pdf_page_number IS NULL OR source_pdf_page_number >= 1",
            name="ck_field_source_page",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_field_confidence",
        ),
        CheckConstraint(
            "validation_status IN ('PENDING','VALID','INVALID','AMBIGUOUS')",
            name="ck_field_validation_status",
        ),
        CheckConstraint(
            "human_verification_status IN ('PENDING','VERIFIED','REJECTED','NOT_REQUIRED')",
            name="ck_field_human_status",
        ),
        Index("ix_field_review", "human_verification_status", "validation_status"),
    )


class ExaminationStatusEvent(Base):
    __tablename__ = "examination_status_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    examination_id: Mapped[int] = mapped_column(
        ForeignKey("medical_examinations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    actor: Mapped[str] = mapped_column(String(100), nullable=False, default="system")
    reason: Mapped[str | None] = mapped_column(Text)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    examination: Mapped[MedicalExamination] = relationship(back_populates="status_events")


class DocumentAccessEvent(Base):
    __tablename__ = "document_access_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    examination_document_id: Mapped[int] = mapped_column(
        ForeignKey("examination_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

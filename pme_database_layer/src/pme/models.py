from __future__ import annotations
from datetime import date, datetime
from typing import Any
from sqlalchemy import Date, DateTime, ForeignKey, JSON, String, Text, UniqueConstraint, func
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

    mobile_number: Mapped[str | None] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(255))

    recruitment_cen: Mapped[str | None] = mapped_column(String(50))

    examinations: Mapped[list["MedicalExamination"]] = relationship(
        back_populates="candidate",
        cascade="all, delete-orphan",
    )

class Doctor(Base):
    __tablename__ = "doctors"
    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_name: Mapped[str] = mapped_column(String(200), nullable=False)
    doctor_role: Mapped[str|None] = mapped_column(String(100))
    examinations: Mapped[list["MedicalExamination"]] = relationship(back_populates="examining_doctor")

class MedicalExamination(Timestamps, Base):
    __tablename__ = "medical_examinations"
    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False, index=True)
    dv_date: Mapped[date|None] = mapped_column(Date)
    medical_examination_date: Mapped[date|None] = mapped_column(Date)
    candidate_declaration_date: Mapped[date | None] = mapped_column(Date)
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

    pme_case: Mapped[PmeCase] = relationship(back_populates="vision_rows")


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

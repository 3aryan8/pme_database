from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from .models import MedicalExamination


# ============================================================
# Candidate
# ============================================================

@dataclass
class CandidateReportData:
    roll_number: str | None = None
    candidate_name: str | None = None
    father_name: str | None = None
    date_of_birth: date | None = None
    mobile_number: str | None = None
    email: str | None = None
    recruitment_cen: str | None = None


# ============================================================
# Medical Examination
# ============================================================

@dataclass
class ExaminationReportData:
    dv_date: date | None = None
    medical_examination_date: date | None = None
    candidate_declaration_date: date | None = None
    medical_class: str | None = None
    identification_marks: str | None = None


# ============================================================
# Page 2 - PME Case
# ============================================================

@dataclass
class PmeMeasurementReportData:
    row_label: str | None = None
    column_1: str | None = None
    column_2: str | None = None
    raw_text: str | None = None


@dataclass
class PmeCaseReportData:
    urine: str | None = None
    sugar: str | None = None
    alb: str | None = None
    chest_xray_result: str | None = None
    advice: str | None = None
    handwritten_remarks: str | None = None

    measurements: list[PmeMeasurementReportData] = field(
        default_factory=list
    )


# ============================================================
# Page 3 - Vision
# ============================================================

@dataclass
class EyeReportData:
    distance_uncorrected: str | None = None
    distance_corrected: str | None = None
    near_uncorrected: str | None = None
    near_corrected: str | None = None
    glasses_s: str | None = None
    glasses_c: str | None = None
    glasses_a: str | None = None


@dataclass
class VisionReportData:
    right_eye: EyeReportData = field(
        default_factory=EyeReportData
    )

    left_eye: EyeReportData = field(
        default_factory=EyeReportData
    )

    color_perception: str | None = None
    binocular_vision: str | None = None
    night_vision: str | None = None
    field_of_vision: str | None = None


# ============================================================
# Page 3 - Physical Examination
# ============================================================

@dataclass
class PhysicalReportData:
    urine: str | None = None
    hearing: str | None = None
    pr: str | None = None
    bp: str | None = None

    cvs: str | None = None
    rs: str | None = None
    pia: str | None = None
    spine: str | None = None

    heart: str | None = None
    lungs: str | None = None

    general_physical_examination: str | None = None


# ============================================================
# Page 3 - Fitness
# ============================================================

@dataclass
class FitnessReportData:
    fit_in_class: str | None = None
    unfit_in_class: str | None = None


# ============================================================
# Page 4 - Declarations
# ============================================================

@dataclass
class DeclarationReportData:
    part: str
    question_no: str
    answer: str | None = None


# ============================================================
# Doctor
# ============================================================

@dataclass
class DoctorReportData:
    doctor_name: str | None = None
    doctor_role: str | None = None


# ============================================================
# Extraction metadata
# ============================================================

@dataclass
class ExtractionReportData:
    document_id: str | None = None
    model_name: str | None = None
    extracted_at: datetime | None = None


# ============================================================
# Complete PME report data
# ============================================================

@dataclass
class PMEReportData:
    candidate: CandidateReportData = field(
        default_factory=CandidateReportData
    )

    examination: ExaminationReportData = field(
        default_factory=ExaminationReportData
    )

    pme_case: PmeCaseReportData = field(
        default_factory=PmeCaseReportData
    )

    vision: VisionReportData = field(
        default_factory=VisionReportData
    )

    physical: PhysicalReportData = field(
        default_factory=PhysicalReportData
    )

    fitness: FitnessReportData = field(
        default_factory=FitnessReportData
    )

    declarations: list[DeclarationReportData] = field(
        default_factory=list
    )

    doctor: DoctorReportData = field(
        default_factory=DoctorReportData
    )

    extraction: ExtractionReportData = field(
        default_factory=ExtractionReportData
    )


# ============================================================
# Conversion helpers
# ============================================================

def build_report_data(
    examination: MedicalExamination,
) -> PMEReportData:
    """
    Convert a SQLAlchemy MedicalExamination object
    into a report-oriented PMEReportData object.
    """

    candidate = examination.candidate

    # --------------------------------------------------------
    # Candidate
    # --------------------------------------------------------

    candidate_data = CandidateReportData(
        roll_number=candidate.roll_number,
        candidate_name=candidate.candidate_name,
        father_name=candidate.father_name,
        date_of_birth=candidate.date_of_birth,
        mobile_number=candidate.mobile_number,
        email=candidate.email,
        recruitment_cen=candidate.recruitment_cen,
    )

    # --------------------------------------------------------
    # Medical examination
    # --------------------------------------------------------

    examination_data = ExaminationReportData(
        dv_date=examination.dv_date,
        medical_examination_date=(
            examination.medical_examination_date
        ),
        candidate_declaration_date=(
            examination.candidate_declaration_date
        ),
        medical_class=examination.medical_class,
        identification_marks=(
            examination.identification_marks
        ),
    )

    # --------------------------------------------------------
    # Page 2 - PME case
    # --------------------------------------------------------

    pme_case_data = PmeCaseReportData()

    if examination.pme_case:
        pme_case = examination.pme_case

        pme_case_data = PmeCaseReportData(
            urine=pme_case.urine,
            sugar=pme_case.sugar,
            alb=pme_case.alb,
            chest_xray_result=(
                pme_case.chest_xray_result
            ),
            advice=pme_case.advice,
            handwritten_remarks=(
                pme_case.handwritten_remarks
            ),
            measurements=[
                PmeMeasurementReportData(
                    row_label=measurement.row_label,
                    column_1=measurement.column_1,
                    column_2=measurement.column_2,
                    raw_text=measurement.raw_text,
                )
                for measurement in pme_case.measurements
            ],
        )

    # --------------------------------------------------------
    # Page 3 - Vision
    # --------------------------------------------------------

    vision_data = VisionReportData()

    if examination.vision:
        vision = examination.vision

        vision_data = VisionReportData(
            right_eye=EyeReportData(
                distance_uncorrected=(
                    vision.right_distance_uncorrected
                ),
                distance_corrected=(
                    vision.right_distance_corrected
                ),
                near_uncorrected=(
                    vision.right_near_uncorrected
                ),
                near_corrected=(
                    vision.right_near_corrected
                ),
                glasses_s=vision.right_glasses_s,
                glasses_c=vision.right_glasses_c,
                glasses_a=vision.right_glasses_a,
            ),
            left_eye=EyeReportData(
                distance_uncorrected=(
                    vision.left_distance_uncorrected
                ),
                distance_corrected=(
                    vision.left_distance_corrected
                ),
                near_uncorrected=(
                    vision.left_near_uncorrected
                ),
                near_corrected=(
                    vision.left_near_corrected
                ),
                glasses_s=vision.left_glasses_s,
                glasses_c=vision.left_glasses_c,
                glasses_a=vision.left_glasses_a,
            ),
            color_perception=(
                vision.color_perception
            ),
            binocular_vision=(
                vision.binocular_vision
            ),
            night_vision=vision.night_vision,
            field_of_vision=(
                vision.field_of_vision
            ),
        )

    # --------------------------------------------------------
    # Page 3 - Physical examination
    # --------------------------------------------------------

    physical_data = PhysicalReportData()

    if examination.physical:
        physical = examination.physical

        physical_data = PhysicalReportData(
            urine=physical.urine,
            hearing=physical.hearing,
            pr=physical.pr,
            bp=physical.bp,
            cvs=physical.cvs,
            rs=physical.rs,
            pia=physical.pia,
            spine=physical.spine,
            heart=physical.heart,
            lungs=physical.lungs,
            general_physical_examination=(
                physical.general_physical_examination
            ),
        )

    # --------------------------------------------------------
    # Fitness
    # --------------------------------------------------------

    fitness_data = FitnessReportData()

    if examination.fitness:
        fitness_data = FitnessReportData(
            fit_in_class=(
                examination.fitness.fit_in_class
            ),
            unfit_in_class=(
                examination.fitness.unfit_in_class
            ),
        )

    # --------------------------------------------------------
    # Declarations
    # --------------------------------------------------------

    declarations = [
        DeclarationReportData(
            part=declaration.part,
            question_no=declaration.question_no,
            answer=declaration.answer,
        )
        for declaration in examination.declarations
    ]

    # --------------------------------------------------------
    # Doctor
    # --------------------------------------------------------

    doctor_data = DoctorReportData()

    if examination.examining_doctor:
        doctor_data = DoctorReportData(
            doctor_name=(
                examination.examining_doctor.doctor_name
            ),
            doctor_role=(
                examination.examining_doctor.doctor_role
            ),
        )

    # --------------------------------------------------------
    # Extraction
    # --------------------------------------------------------

    extraction_data = ExtractionReportData()

    if examination.extraction_runs:
        latest = sorted(
            examination.extraction_runs,
            key=lambda item: item.id,
            reverse=True,
        )[0]

        extraction_data = ExtractionReportData(
            document_id=latest.document_id,
            model_name=latest.model_name,
            extracted_at=latest.extracted_at,
        )

    # --------------------------------------------------------
    # Complete object
    # --------------------------------------------------------

    return PMEReportData(
        candidate=candidate_data,
        examination=examination_data,
        pme_case=pme_case_data,
        vision=vision_data,
        physical=physical_data,
        fitness=fitness_data,
        declarations=declarations,
        doctor=doctor_data,
        extraction=extraction_data,
    )


def report_data_to_dict(
    report: PMEReportData,
) -> dict[str, Any]:
    """
    Convert PMEReportData into a normal dictionary.

    Useful for debugging, JSON output, APIs, and templates.
    """

    return {
        "candidate": {
            "roll_number": report.candidate.roll_number,
            "candidate_name": report.candidate.candidate_name,
            "father_name": report.candidate.father_name,
            "date_of_birth": report.candidate.date_of_birth,
            "mobile_number": report.candidate.mobile_number,
            "email": report.candidate.email,
            "recruitment_cen": report.candidate.recruitment_cen,
        },
        "examination": {
            "dv_date": report.examination.dv_date,
            "medical_examination_date": (
                report.examination.medical_examination_date
            ),
            "candidate_declaration_date": (
                report.examination.candidate_declaration_date
            ),
            "medical_class": (
                report.examination.medical_class
            ),
            "identification_marks": (
                report.examination.identification_marks
            ),
        },
        "pme_case": {
            "urine": report.pme_case.urine,
            "sugar": report.pme_case.sugar,
            "alb": report.pme_case.alb,
            "chest_xray_result": (
                report.pme_case.chest_xray_result
            ),
            "advice": report.pme_case.advice,
            "handwritten_remarks": (
                report.pme_case.handwritten_remarks
            ),
            "measurements": [
                {
                    "row_label": item.row_label,
                    "column_1": item.column_1,
                    "column_2": item.column_2,
                    "raw_text": item.raw_text,
                }
                for item in report.pme_case.measurements
            ],
        },
        "vision": {
            "right_eye": {
                "distance_uncorrected": (
                    report.vision.right_eye
                    .distance_uncorrected
                ),
                "distance_corrected": (
                    report.vision.right_eye
                    .distance_corrected
                ),
                "near_uncorrected": (
                    report.vision.right_eye
                    .near_uncorrected
                ),
                "near_corrected": (
                    report.vision.right_eye
                    .near_corrected
                ),
                "glasses_s": (
                    report.vision.right_eye.glasses_s
                ),
                "glasses_c": (
                    report.vision.right_eye.glasses_c
                ),
                "glasses_a": (
                    report.vision.right_eye.glasses_a
                ),
            },
            "left_eye": {
                "distance_uncorrected": (
                    report.vision.left_eye
                    .distance_uncorrected
                ),
                "distance_corrected": (
                    report.vision.left_eye
                    .distance_corrected
                ),
                "near_uncorrected": (
                    report.vision.left_eye
                    .near_uncorrected
                ),
                "near_corrected": (
                    report.vision.left_eye
                    .near_corrected
                ),
                "glasses_s": (
                    report.vision.left_eye.glasses_s
                ),
                "glasses_c": (
                    report.vision.left_eye.glasses_c
                ),
                "glasses_a": (
                    report.vision.left_eye.glasses_a
                ),
            },
            "color_perception": (
                report.vision.color_perception
            ),
            "binocular_vision": (
                report.vision.binocular_vision
            ),
            "night_vision": (
                report.vision.night_vision
            ),
            "field_of_vision": (
                report.vision.field_of_vision
            ),
        },
        "physical": {
            "urine": report.physical.urine,
            "hearing": report.physical.hearing,
            "pr": report.physical.pr,
            "bp": report.physical.bp,
            "cvs": report.physical.cvs,
            "rs": report.physical.rs,
            "pia": report.physical.pia,
            "spine": report.physical.spine,
            "heart": report.physical.heart,
            "lungs": report.physical.lungs,
            "general_physical_examination": (
                report.physical
                .general_physical_examination
            ),
        },
        "fitness": {
            "fit_in_class": (
                report.fitness.fit_in_class
            ),
            "unfit_in_class": (
                report.fitness.unfit_in_class
            ),
        },
        "declarations": [
            {
                "part": item.part,
                "question_no": item.question_no,
                "answer": item.answer,
            }
            for item in report.declarations
        ],
        "doctor": {
            "doctor_name": report.doctor.doctor_name,
            "doctor_role": report.doctor.doctor_role,
        },
        "extraction": {
            "document_id": (
                report.extraction.document_id
            ),
            "model_name": (
                report.extraction.model_name
            ),
            "extracted_at": (
                report.extraction.extracted_at
            ),
        },
    }

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import MAIN_PROJECT_ROOT
from .models import (
    Candidate,
    Declaration,
    Doctor,
    ExtractionRun,
    FitnessClassification,
    MedicalExamination,
    PhysicalExamination,
    PmeCase,
    PmeVisionRow,
    ReportImage,
    VisionExamination,
)
from .report_images import find_report_images
from .schemas import PMEExtraction


def clean(value):
    if value is None:
        return None

    value = str(value).strip()
    return value or None


def to_stored_path(path: Path) -> str:
    """Store paths relative to the pipeline project when possible
    (matches the manifest convention, e.g. data/interim/high_res/...),
    absolute otherwise."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(MAIN_PROJECT_ROOT).as_posix()
    except ValueError:
        return str(resolved)


def parse_metrics(text):
    output = {}

    if not text:
        return output

    for item in text.split(";"):
        if ":" not in item:
            continue

        key, value = item.split(":", 1)

        key = key.strip().lower()
        value = value.strip()

        if key:
            output[key] = value

    return output


def import_one(session: Session, data: PMEExtraction):
    # ---------------------------------------------------------
    # Prevent duplicate imports
    # ---------------------------------------------------------
    existing = session.scalar(
        select(ExtractionRun).where(
            ExtractionRun.document_id == data.document_id
        )
    )

    if existing:
        return existing.examination, False

    # ---------------------------------------------------------
    # Extract pages
    # ---------------------------------------------------------
    page1 = data.page1
    page2 = data.page2
    page3 = data.page3
    page4 = data.page4

    general = page1.general_details
    narrative = page1.narrative_details
    physical_traits = page1.physical_traits

    # ---------------------------------------------------------
    # Candidate validation
    # ---------------------------------------------------------
    if not narrative.roll_number:
        raise ValueError(
            f"{data.document_id}: roll_number is required"
        )

    roll_number = clean(narrative.roll_number)

    # ---------------------------------------------------------
    # Find or create candidate
    # ---------------------------------------------------------
    candidate = session.scalar(
        select(Candidate).where(
            Candidate.roll_number == roll_number
        )
    )

    if not candidate:
        candidate = Candidate(
            roll_number=roll_number,
            candidate_name=clean(general.candidate_name),
            father_name=clean(general.father_name),
            date_of_birth=general.date_of_birth,
            mobile_number=clean(general.mobile_number),
            email=clean(general.email),
            recruitment_cen=clean(narrative.recruitment_cen),
        )

        session.add(candidate)
        session.flush()

    else:
        candidate_updates = {
            "candidate_name": general.candidate_name,
            "father_name": general.father_name,
            "date_of_birth": general.date_of_birth,
            "mobile_number": general.mobile_number,
            "email": general.email,
            "recruitment_cen": narrative.recruitment_cen,
        }

        for attribute, value in candidate_updates.items():
            if value in (None, ""):
                continue

            if attribute == "date_of_birth":
                setattr(candidate, attribute, value)
            else:
                setattr(candidate, attribute, clean(value))

        session.flush()

    # ---------------------------------------------------------
    # Medical examination
    # ---------------------------------------------------------
    examination = MedicalExamination(
        candidate=candidate,
        dv_date=general.dv_date,
        medical_examination_date=general.medical_examination_date,
        candidate_declaration_date=page4.declaration_date,
        medical_class=clean(narrative.class_name),
        identification_marks=clean(
            physical_traits.permanent_physical_identification_marks
        ),
    )

    session.add(examination)
    session.flush()

    # ---------------------------------------------------------
    # Report images — every rendered page of this document. N pages per
    # person comes from configs/splits.yaml (via the record's
    # pages_covered), not a fixed number.
    # Added in the same transaction as the examination: if any page is
    # missing the whole import rolls back (no orphans, no partial state).
    # ---------------------------------------------------------
    expected_pages = len(data.pages_covered) or None
    for page_number, image_path in find_report_images(
        data.document_id, expected=expected_pages
    ):
        session.add(
            ReportImage(
                examination=examination,
                page_number=page_number,
                image_path=to_stored_path(image_path),
                document_id=data.document_id,
            )
        )

    # ---------------------------------------------------------
    # Page 2 - PME Case
    # ------------------------------------------------=========
    pme_case = PmeCase(
        examination=examination,
        urine=clean(page2.pme_case.urine),
        sugar=clean(page2.pme_case.sugar),
        alb=clean(page2.pme_case.alb),
        handwritten_remarks=clean(page2.handwritten_remarks),
    )

    session.add(pme_case)
    session.flush()

    # ---------------------------------------------------------
    # Page 2 - vision/table rows
    # ---------------------------------------------------------
    for row in page2.right_side_table:
        pme_vision_row = PmeVisionRow(
            pme_case_id=pme_case.id,
            row_label=clean(row.row) or "UNKNOWN",
            right_value=clean(row.side_r),
            left_value=clean(row.side_l),
        )

        session.add(pme_vision_row)

    # ---------------------------------------------------------
    # Page 3 - handwritten metrics
    # ---------------------------------------------------------
    metrics = parse_metrics(
        page3.handwritten_text_below_vision_table
    )

    # ---------------------------------------------------------
    # Page 3 - eyes
    # ---------------------------------------------------------
    right_eye = page3.accuracy_of_vision.get("right_eye")
    left_eye = page3.accuracy_of_vision.get("left_eye")

    vision = VisionExamination(
        examination=examination,

        right_distance_uncorrected=(
            right_eye.distance_uncorrected
            if right_eye
            else None
        ),

        right_distance_corrected=(
            right_eye.distance_corrected
            if right_eye
            else None
        ),

        right_near_uncorrected=(
            right_eye.near_uncorrected
            if right_eye
            else None
        ),

        right_near_corrected=(
            right_eye.near_corrected
            if right_eye
            else None
        ),

        right_glasses_s=(
            right_eye.glasses_power_s
            if right_eye
            else None
        ),

        right_glasses_c=(
            right_eye.glasses_power_c
            if right_eye
            else None
        ),

        right_glasses_a=(
            right_eye.glasses_power_a
            if right_eye
            else None
        ),

        left_distance_uncorrected=(
            left_eye.distance_uncorrected
            if left_eye
            else None
        ),

        left_distance_corrected=(
            left_eye.distance_corrected
            if left_eye
            else None
        ),

        left_near_uncorrected=(
            left_eye.near_uncorrected
            if left_eye
            else None
        ),

        left_near_corrected=(
            left_eye.near_corrected
            if left_eye
            else None
        ),

        left_glasses_s=(
            left_eye.glasses_power_s
            if left_eye
            else None
        ),

        left_glasses_c=(
            left_eye.glasses_power_c
            if left_eye
            else None
        ),

        left_glasses_a=(
            left_eye.glasses_power_a
            if left_eye
            else None
        ),

        color_perception=clean(
            page3.color_perception
            or metrics.get("colour perception")
            or metrics.get("color perception")
        ),

        binocular_vision=clean(
            page3.binocular_vision
        ),

        night_vision=clean(
            page3.night_vision
            or metrics.get("night vision")
        ),

        field_of_vision=clean(
            page3.field_of_vision
        ),
    )

    session.add(vision)

    # ---------------------------------------------------------
    # Page 3 - physical examination
    # ---------------------------------------------------------
    physical = PhysicalExamination(
        examination=examination,

        urine=clean(
            page3.urine
            or metrics.get("urine")
        ),

        hearing=clean(
            page3.hearing
            or metrics.get("hearing")
        ),

        pr=clean(
            page3.pr
            or metrics.get("pr")
        ),

        bp=clean(
            page3.bp
            or metrics.get("bp")
        ),

        cvs=clean(page3.cvs),
        rs=clean(page3.rs),
        pia=clean(page3.pia),
        spine=clean(page3.spine),

        heart=clean(
            page3.heart
            or metrics.get("heart")
        ),

        lungs=clean(
            page3.lungs
            or metrics.get("lungs")
        ),

        general_physical_examination=clean(
            page3.general_physical_examination
        ),
    )

    session.add(physical)

    # ---------------------------------------------------------
    # Page 3 - fitness classification
    # ---------------------------------------------------------
    fitness = FitnessClassification(
        examination=examination,
        fit_in_class=clean(page3.fit_in_class),
        unfit_in_class=clean(page3.unfit_in_class),
    )

    session.add(fitness)

    # ---------------------------------------------------------
    # Page 4 - declarations
    # ---------------------------------------------------------
    declaration_groups = (
        ("Part 1", page4.part_one),
        ("Part 2", page4.part_two),
    )

    for part_name, items in declaration_groups:
        for item in items:
            declaration = Declaration(
                examination=examination,
                part=part_name,
                question_no=(
                    clean(item.question_no)
                    or "UNKNOWN"
                ),
                answer=clean(item.answer),
            )

            session.add(declaration)

    # ---------------------------------------------------------
    # Doctor
    # ---------------------------------------------------------
    doctor_name = clean(
        page3.doctor_name
        or page4.doctor_name
    )

    if doctor_name:
        doctor = session.scalar(
            select(Doctor).where(
                Doctor.doctor_name == doctor_name,
                Doctor.doctor_role
                == "Railway Medical Examiner",
            )
        )

        if not doctor:
            doctor = Doctor(
                doctor_name=doctor_name,
                doctor_role="Railway Medical Examiner",
            )

            session.add(doctor)
            session.flush()

        examination.examining_doctor = doctor

    # ---------------------------------------------------------
    # Extraction run
    # ---------------------------------------------------------
    extracted_at = next(
        (
            provenance.extracted_at
            for provenance in data.provenance.values()
            if provenance.extracted_at
        ),
        None,
    )

    extraction_run = ExtractionRun(
        examination=examination,
        document_id=data.document_id,
        model_name=data.model,
        extracted_at=extracted_at,
        raw_json=data.model_dump(mode="json"),
    )

    session.add(extraction_run)

    session.flush()

    return examination, True


def import_directory(
    session: Session,
    directory: Path,
):
    successful = 0
    failed = 0

    for path in sorted(directory.rglob("*.json")):
        try:
            with session.begin_nested():
                _, created = import_one(
                    session,
                    PMEExtraction.from_file(path),
                )

            session.commit()

            successful += 1

            status = (
                "imported"
                if created
                else "already imported"
            )

            print(
                f"[OK] {path.name} {status}"
            )

        except Exception as error:
            session.rollback()
            failed += 1

            print(
                f"[ERROR] {path.name}: {error}"
            )

    return successful, failed
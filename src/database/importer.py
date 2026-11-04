# Phase: normalized database import | Input: canonical record.json files | Output: relational database rows and report-image references | Command: ``uv run python -m src.database.run_database``.
from __future__ import annotations

from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .config import MAIN_PROJECT_ROOT, get_extraction_dir
from .doctor_assets import identify_doctor_from_document, save_examination_visual_evidence
from .doctor_utils import normalize_doctor_name
from .models import (
    Candidate,
    Declaration,
    Doctor,
    DoctorIdentification,
    ExaminationPage1,
    ExaminationPage4,
    ExaminationPageStatus,
    ExaminationAuthentication,
    ExtractedFieldValue,
    ExtractionRun,
    ExaminationStatusEvent,
    FitnessClassification,
    MedicalExamination,
    PhysicalExamination,
    PmeCase,
    PmeCaseMeasurement,
    PmeVisionRow,
    ReportImage,
    SourceDocument,
    SourceDocumentPage,
    VisionExamination,
)
from .report_images import find_report_images
from .security import encrypt_contact, link_original_pdf
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


def _flatten_values(value, prefix=""):
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield from _flatten_values(child, path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _flatten_values(child, f"{prefix}.{index}")
    else:
        yield prefix, value


def _page_for_field(field_name: str) -> int | None:
    if field_name.startswith("page_1_"):
        return 1
    if field_name.startswith("page_2_"):
        return 2
    if field_name.startswith("page_3_"):
        return 3
    if field_name.startswith("page_4_"):
        return 4
    return None


def _redacted_extraction(data: PMEExtraction) -> dict:
    payload = data.model_dump(mode="json")
    for path, entry in payload.get("provenance", {}).items():
        if path.rsplit(".", 1)[-1].lower() in {"mobile_number", "email"}:
            entry["raw_value"] = "[ENCRYPTED]"
            entry["normalized_value"] = None
    for path, value in _flatten_values(payload.get("fields", {})):
        if path.rsplit(".", 1)[-1].lower() not in {"mobile_number", "email"}:
            continue
        cursor = payload["fields"]
        parts = path.split(".")
        for part in parts[:-1]:
            cursor = cursor[int(part)] if isinstance(cursor, list) else cursor[part]
        if isinstance(cursor, dict):
            cursor[parts[-1]] = "[ENCRYPTED]" if value else None
    return payload


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
            recruitment_cen=clean(narrative.recruitment_cen),
        )

        session.add(candidate)
        session.flush()

    else:
        # Candidate master data is not rewritten from later examination forms.
        # Each form's observed identity values are retained in its page snapshots.
        pass

    # ---------------------------------------------------------
    # Medical examination
    # ---------------------------------------------------------
    candidate_class = clean(narrative.class_name)
    covered_pages = set(data.pages_covered)
    overall_status = (
        "PENDING_REVIEW"
        if {0, 1, 2, 3}.issubset(covered_pages)
        else "PARTIALLY_EXTRACTED"
        if covered_pages
        else "UPLOADED"
    )
    examination = MedicalExamination(
        candidate=candidate,
        dv_date=general.dv_date,
        medical_examination_date=general.medical_examination_date,
        candidate_declaration_date=page4.declaration_date,
        identification_marks=clean(
            physical_traits.permanent_physical_identification_marks
        ),
        overall_status=overall_status,
    )

    session.add(examination)
    session.flush()

    page4_identity = page4.repeated_candidate_particulars
    session.add(
        ExaminationPage1(
            examination_id=examination.id,
            roll_number=roll_number,
            candidate_name=clean(general.candidate_name),
            father_name=clean(general.father_name),
            date_of_birth=general.date_of_birth,
            dv_date=general.dv_date,
            medical_examination_date=general.medical_examination_date,
            recruitment_cen=clean(narrative.recruitment_cen),
            post_name=clean(narrative.post_name),
            candidate_class=candidate_class,
            age_raw=clean(narrative.age_raw),
            memo_number=clean(narrative.memo_number),
            addressee_or_hospital=clean(narrative.addressee_or_hospital),
            permanent_identification_marks=clean(
                physical_traits.permanent_physical_identification_marks
            ),
            station=clean(narrative.station),
            station_date=narrative.station_date,
        )
    )
    session.add(
        ExaminationPage4(
            examination_id=examination.id,
            candidate_name=clean(page4_identity.candidate_name or page4.candidate_name),
            father_name=clean(page4_identity.father_name or page4.father_name),
            roll_number=clean(page4_identity.roll_number or page4.roll_number),
            date_of_birth=page4_identity.date_of_birth or page4.date_of_birth,
            mobile_number_encrypted=encrypt_contact(
                clean(page4_identity.mobile_number or page4.mobile_number)
            ),
            email_encrypted=encrypt_contact(
                clean(page4_identity.email or page4.email)
            ),
            permanent_identification_marks=clean(
                page4_identity.permanent_identification_marks
                or page4.permanent_identification_marks
            ),
            declaration_date=page4.declaration_date,
        )
    )
    for page_number in range(1, 5):
        session.add(
            ExaminationPageStatus(
                examination_id=examination.id,
                page_number=page_number,
                status=(
                    "PENDING_REVIEW"
                    if page_number - 1 in covered_pages
                    else "NOT_STARTED"
                ),
            )
        )
        session.add(
            ExaminationAuthentication(
                examination_id=examination.id,
                page_number=page_number,
                source_pdf_page_number=data.source_pdf_pages.get(page_number - 1),
                actor_role="UNKNOWN",
                signature_status="UNVERIFIED",
                stamp_status="UNVERIFIED",
            )
        )
    session.add(
        ExaminationStatusEvent(
            examination_id=examination.id,
            from_status=None,
            to_status=overall_status,
            actor="extraction_import",
            reason="Extraction import recorded with page coverage",
        )
    )

    source_document = None
    if data.source_document_id is not None:
        source_document = session.get(SourceDocument, data.source_document_id)
    elif data.source_pdf_sha256:
        source_document = session.scalar(
            select(SourceDocument).where(SourceDocument.sha256 == data.source_pdf_sha256)
        )
    if source_document is not None:
        link_original_pdf(
            session,
            examination_id=examination.id,
            source_document=source_document,
        )

    # ---------------------------------------------------------
    # Report images — every rendered page of this document. N pages per
    # person comes from configs/splits.yaml (via the record's
    # pages_covered), not a fixed number.
    # Added in the same transaction as the examination: if any page is
    # missing the whole import rolls back (no orphans, no partial state).
    # ---------------------------------------------------------
    expected_pages = (
        len(data.source_pdf_pages)
        or len(data.pages_covered)
        or None
    )
    for page_number, image_path in find_report_images(
        data.document_id, expected=expected_pages
    ):
        source_pdf_page_number = data.source_pdf_pages.get(page_number - 1)
        session.add(
            ReportImage(
                examination=examination,
                page_number=page_number,
                image_path=to_stored_path(image_path),
                document_id=data.document_id,
                source_pdf_page_number=source_pdf_page_number,
            )
        )
        if source_document is not None and source_pdf_page_number is not None:
            source_page = session.scalar(
                select(SourceDocumentPage).where(
                    SourceDocumentPage.source_document_id == source_document.id,
                    SourceDocumentPage.source_pdf_page_number == source_pdf_page_number,
                )
            )
            if source_page is not None:
                if (
                    source_page.page_kind != "CANDIDATE_FORM"
                    or source_page.form_page_number != page_number
                    or (
                        data.source_packet_index is not None
                        and source_page.packet_index != data.source_packet_index
                    )
                ):
                    raise ValueError(
                        f"Source page {source_pdf_page_number} conflicts with the reviewed split map"
                    )
                source_page.examination_id = examination.id
            else:
                session.add(
                    SourceDocumentPage(
                        source_document_id=source_document.id,
                        source_pdf_page_number=source_pdf_page_number,
                        page_kind="CANDIDATE_FORM",
                        packet_index=data.source_packet_index,
                        examination_id=examination.id,
                        form_page_number=page_number,
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
        chest_xray_result=clean(
            page2.pme_case.chest_xray_result or page2.chest_xray_result
        ),
        advice=clean(page2.pme_case.advice or page2.advice),
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

    for row in page2.measurements:
        session.add(
            PmeCaseMeasurement(
                pme_case_id=pme_case.id,
                row_label=clean(row.row_label),
                column_1=clean(row.column_1),
                column_2=clean(row.column_2),
                raw_text=clean(row.raw_text),
                source_pdf_page_number=data.source_pdf_pages.get(1),
            )
        )

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

    doctor = None
    if doctor_name:
        normalized_name = normalize_doctor_name(doctor_name)
        doctor = session.scalar(
            select(Doctor).where(
                (Doctor.full_name_english == normalized_name)
                | (Doctor.doctor_name == doctor_name)
            )
        )

        if not doctor:
            doctor = Doctor(
                doctor_name=doctor_name,
                full_name_english=normalized_name or doctor_name,
                doctor_role="Railway Medical Examiner",
            )

            session.add(doctor)
            session.flush()
    else:
        doctor, _ = identify_doctor_from_document(session, data.document_id)

    if doctor:
        examination.examining_doctor = doctor
        candidate.doctor_id = doctor.id

    authentication_records = save_examination_visual_evidence(
        session,
        examination.id,
        data.document_id,
        data.source_pdf_pages,
    )
    observed_doctor_name = clean(page3.doctor_name or page4.doctor_name)
    for authentication in authentication_records:
        if authentication.page_number in {3, 4}:
            authentication.doctor_id = doctor.id if doctor else None
            authentication.observed_name = observed_doctor_name
            authentication.designation = doctor.designation if doctor else None

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
        raw_json=_redacted_extraction(data),
    )

    session.add(extraction_run)

    session.flush()

    provenance_by_name = data.provenance
    for field_name, extracted_value in _flatten_values(data.fields):
        page_number = _page_for_field(field_name)
        if page_number is None or field_name.rsplit(".", 1)[-1].lower() in {
            "mobile_number", "email"
        }:
            continue
        provenance = provenance_by_name.get(field_name)
        source_page = (
            provenance.source_pdf_page_number
            if provenance and provenance.source_pdf_page_number
            else data.source_pdf_pages.get(page_number - 1)
        )
        session.add(
            ExtractedFieldValue(
                examination_id=examination.id,
                extraction_run_id=extraction_run.id,
                field_name=field_name,
                form_page_number=page_number,
                source_pdf_page_number=source_page,
                extracted_value=(
                    provenance.raw_value if provenance and provenance.raw_value is not None
                    else extracted_value
                ),
                normalized_value=(provenance.normalized_value if provenance else None),
                confidence=(provenance.confidence if provenance else None),
                validation_status=(
                    provenance.validation_status if provenance and provenance.validation_status
                    else "PENDING"
                ),
                human_verification_status=(
                    provenance.human_verification_status
                    if provenance and provenance.human_verification_status
                    else "PENDING"
                ),
                bounding_box=(provenance.bounding_box if provenance else None),
            )
        )

    return examination, True


def import_directory(
    session: Session,
    directory: Path,
):
    successful = 0
    failed = 0

    for path in sorted(directory.rglob("record.json")):
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

            print(f"[OK] extraction record {status}")

        except Exception as error:
            session.rollback()
            failed += 1

            print(f"[ERROR] extraction record failed ({type(error).__name__})")

    return successful, failed


def merge_doctor_aliases(session: Session) -> int:
    """Merge known OCR name aliases and preserve all doctor foreign keys."""
    grouped: dict[str, list[Doctor]] = {}
    for doctor in session.scalars(select(Doctor).order_by(Doctor.id)).all():
        canonical_name = normalize_doctor_name(
            doctor.full_name_english or doctor.doctor_name
        )
        if canonical_name:
            grouped.setdefault(canonical_name, []).append(doctor)

    merged = 0
    for canonical_name, doctors in grouped.items():
        primary = min(
            doctors,
            key=lambda doctor: (
                doctor.full_name_english != canonical_name,
                doctor.id,
            ),
        )
        for duplicate in doctors:
            if duplicate.id == primary.id:
                continue

            for model, column in (
                (Candidate, Candidate.doctor_id),
                (MedicalExamination, MedicalExamination.examining_doctor_id),
                (DoctorIdentification, DoctorIdentification.doctor_id),
            ):
                session.execute(
                    update(model)
                    .where(column == duplicate.id)
                    .values({column.key: primary.id})
                )

            for field in (
                "full_name_hindi",
                "designation",
                "doctor_role",
                "signature_image_path",
                "stamp_image_path",
                "signature_hash",
                "stamp_hash",
            ):
                if getattr(primary, field) is None:
                    setattr(primary, field, getattr(duplicate, field))
            session.delete(duplicate)
            merged += 1

        session.flush()
        primary.full_name_english = canonical_name
        primary.doctor_name = canonical_name

    session.flush()
    return merged


def sync_extractions(
    session: Session,
    directory: Path | None = None,
) -> tuple[int, int]:
    """Import every extraction currently available in the pipeline output."""
    extraction_dir = directory or get_extraction_dir()
    if not extraction_dir.exists():
        raise FileNotFoundError(
            f"Extraction directory does not exist: {extraction_dir}"
        )
    result = import_directory(session, extraction_dir)
    merge_doctor_aliases(session)
    session.commit()
    return result
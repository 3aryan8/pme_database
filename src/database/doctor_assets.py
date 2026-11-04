from __future__ import annotations

import json
from hashlib import sha256
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import MAIN_PROJECT_ROOT
from .models import (
    Candidate,
    Doctor,
    DoctorIdentification,
    ExaminationAuthentication,
    ExaminationDocument,
    MedicalExamination,
)
from .report_images import find_report_images
from .security import private_storage_root, read_private_asset, store_evidence


def _encode_crop(image: Image.Image, label: str) -> bytes:
    if image.width < 8 or image.height < 8:
        raise ValueError(f"The {label} crop is too small to save.")
    buffer = BytesIO()
    image.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def _stored_path(path: Path) -> str:
    try:
        return path.relative_to(MAIN_PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path)


def _asset_path(stored_path: str | None) -> Path | None:
    if not stored_path:
        return None
    path = Path(stored_path)
    return path if path.is_absolute() else MAIN_PROJECT_ROOT / path


def _image_similarity(first: Image.Image, second: Image.Image) -> float:
    size = (128, 64)
    first_array = np.asarray(ImageOps.grayscale(first).resize(size), dtype=np.float32)
    second_array = np.asarray(ImageOps.grayscale(second).resize(size), dtype=np.float32)
    first_mask = first_array < 200
    second_mask = second_array < 200
    return float(1.0 - np.mean(np.logical_xor(first_mask, second_mask)))


def _region_crops(
    document_id: str,
    region_root: Path | None = None,
) -> tuple[Image.Image | None, Image.Image | None, int | None]:
    region_directory = region_root or MAIN_PROJECT_ROOT / "data/processed/regions"
    try:
        report_pages = dict(find_report_images(document_id))
    except FileNotFoundError:
        return None, None, None

    candidates: dict[str, tuple[int, Image.Image, int]] = {}
    for region_path in sorted(region_directory.joinpath(document_id).glob("page_*.json")):
        try:
            payload = json.loads(region_path.read_text(encoding="utf-8"))
            page_index = int(payload["page_index"])
            page_path = report_pages[page_index + 1]
        except (KeyError, TypeError, ValueError, OSError):
            continue
        if page_index not in {2, 3}:
            continue

        try:
            with Image.open(page_path) as source:
                source_image = source.convert("RGB")
                for detection in payload.get("detections", []):
                    region_class = str(detection.get("region_class", "")).lower()
                    asset_type = {
                        "signature": "signature",
                        "stamp_seal": "stamp",
                    }.get(region_class)
                    box = detection.get("box_norm")
                    if asset_type is None or not isinstance(box, list) or len(box) != 4:
                        continue
                    width, height = source_image.size
                    left, top, right, bottom = (
                        max(0, min(1, float(box[0]))) * width,
                        max(0, min(1, float(box[1]))) * height,
                        max(0, min(1, float(box[2]))) * width,
                        max(0, min(1, float(box[3]))) * height,
                    )
                    crop = source_image.crop((left, top, right, bottom))
                    area = crop.width * crop.height
                    if area >= 64 and (
                        asset_type not in candidates
                        or area > candidates[asset_type][0]
                    ):
                        candidates[asset_type] = (area, crop.copy(), page_index + 1)
        except (OSError, ValueError):
            continue

    signature = candidates.get("signature")
    stamp = candidates.get("stamp")
    source_page = signature[2] if signature else stamp[2] if stamp else None
    return (
        signature[1] if signature else None,
        stamp[1] if stamp else None,
        source_page,
    )


def save_examination_visual_evidence(
    session: Session,
    examination_id: int,
    document_id: str,
    source_pdf_pages: dict[int, int] | None = None,
    region_root: Path | None = None,
) -> list[ExaminationAuthentication]:
    """Encrypt and link all detected visual assets to their examination/page."""
    region_directory = region_root or MAIN_PROJECT_ROOT / "data/processed/regions"
    try:
        report_pages = dict(find_report_images(document_id))
    except FileNotFoundError:
        return []

    auth_assets: dict[int, dict[str, int]] = {}
    processed_pages: set[int] = set()
    asset_types = {
        "photo": "CANDIDATE_PHOTO",
        "thumbprint": "CANDIDATE_THUMBPRINT",
        "signature": "SIGNATURE",
        "stamp_seal": "STAMP_SEAL",
    }
    for region_path in sorted(region_directory.joinpath(document_id).glob("page_*.json")):
        try:
            payload = json.loads(region_path.read_text(encoding="utf-8"))
            page_index = int(payload["page_index"])
            form_page = page_index + 1
            image_path = report_pages[form_page]
        except (KeyError, TypeError, ValueError, OSError):
            continue
        if form_page not in range(1, 5):
            continue
        processed_pages.add(form_page)

        try:
            with Image.open(image_path) as source:
                source_image = source.convert("RGB")
                for detection in payload.get("detections", []):
                    region_class = str(detection.get("region_class", "")).lower()
                    asset_type = asset_types.get(region_class)
                    box = detection.get("box_norm")
                    if asset_type is None or not isinstance(box, list) or len(box) != 4:
                        continue
                    width, height = source_image.size
                    left, top, right, bottom = (
                        max(0, min(1, float(box[0]))) * width,
                        max(0, min(1, float(box[1]))) * height,
                        max(0, min(1, float(box[2]))) * width,
                        max(0, min(1, float(box[3]))) * height,
                    )
                    crop = source_image.crop((left, top, right, bottom))
                    if crop.width < 8 or crop.height < 8:
                        continue
                    buffer = BytesIO()
                    crop.save(buffer, format="PNG")
                    evidence = store_evidence(
                        session,
                        examination_id=examination_id,
                        content=buffer.getvalue(),
                        asset_type=asset_type,
                        form_page_number=form_page,
                        source_pdf_page_number=(source_pdf_pages or {}).get(page_index),
                        media_type="image/png",
                    )
                    if asset_type == "SIGNATURE":
                        auth_assets.setdefault(form_page, {})["signature"] = evidence.id
                    elif asset_type == "STAMP_SEAL":
                        auth_assets.setdefault(form_page, {})["stamp"] = evidence.id
        except (OSError, ValueError):
            continue

    records: list[ExaminationAuthentication] = []
    for page_number in range(1, 5):
        assets = auth_assets.get(page_number, {})
        record = session.scalar(
            select(ExaminationAuthentication).where(
                ExaminationAuthentication.examination_id == examination_id,
                ExaminationAuthentication.page_number == page_number,
            )
        )
        if record is None:
            record = ExaminationAuthentication(
                examination_id=examination_id,
                page_number=page_number,
                actor_role="UNKNOWN",
            )
            session.add(record)
        record.source_pdf_page_number = (source_pdf_pages or {}).get(page_number - 1)
        record.signature_status = (
            "UNVERIFIED" if "signature" in assets
            else "MISSING" if page_number in processed_pages
            else "UNVERIFIED"
        )
        record.stamp_status = (
            "UNVERIFIED" if "stamp" in assets
            else "MISSING" if page_number in processed_pages
            else "UNVERIFIED"
        )
        record.signature_document_id = assets.get("signature")
        record.stamp_document_id = assets.get("stamp")
        records.append(record)
    session.flush()
    return records


def save_detected_doctor_assets(
    session: Session,
    doctor: Doctor,
    candidate: Candidate,
    document_id: str,
    region_root: Path | None = None,
) -> bool:
    """Persist detected crops as encrypted examination evidence."""
    examination_id = session.scalar(
        select(MedicalExamination.id)
        .where(
            MedicalExamination.candidate_id == candidate.id,
            MedicalExamination.examining_doctor_id == doctor.id,
        )
        .order_by(MedicalExamination.id.desc())
        .limit(1)
    )
    if examination_id is None:
        return False
    before = session.scalar(
        select(ExaminationDocument.id)
        .where(
            ExaminationDocument.examination_id == examination_id,
            ExaminationDocument.asset_type.in_(("SIGNATURE", "STAMP_SEAL")),
        )
        .limit(1)
    )
    save_examination_visual_evidence(
        session,
        examination_id,
        document_id,
        region_root=region_root,
    )
    after = session.scalar(
        select(ExaminationDocument.id)
        .where(
            ExaminationDocument.examination_id == examination_id,
            ExaminationDocument.asset_type.in_(("SIGNATURE", "STAMP_SEAL")),
        )
        .limit(1)
    )
    return before is None and after is not None


def identify_doctor_from_document(
    session: Session,
    document_id: str,
    region_root: Path | None = None,
) -> tuple[Doctor | None, float]:
    """Return the best stored doctor match for detected signature/stamp crops."""
    signature_crop, stamp_crop, _ = _region_crops(document_id, region_root)
    if signature_crop is None and stamp_crop is None:
        return None, 0.0

    best_doctor: Doctor | None = None
    best_score = 0.0
    for doctor in session.scalars(select(Doctor)).all():
        scores: list[float] = []
        if signature_crop is not None and doctor.signature_image_path:
            try:
                reference = _load_doctor_reference(session, doctor.signature_image_path)
            except (FileNotFoundError, OSError, RuntimeError):
                reference = None
            if reference is not None:
                with reference:
                    stored_signature = reference
                    scores.append(_image_similarity(signature_crop, stored_signature))
        if stamp_crop is not None and doctor.stamp_image_path:
            try:
                reference = _load_doctor_reference(session, doctor.stamp_image_path)
            except (FileNotFoundError, OSError, RuntimeError):
                reference = None
            if reference is not None:
                with reference:
                    stored_stamp = reference
                    scores.append(_image_similarity(stamp_crop, stored_stamp))
        if scores:
            score = sum(scores) / len(scores)
            if score > best_score:
                best_doctor, best_score = doctor, score

    if best_score < 0.78:
        return None, best_score
    return best_doctor, best_score


def _load_doctor_reference(session: Session, value: str) -> Image.Image | None:
    if value.startswith("examinations/"):
        content = read_private_asset(
            session,
            value,
            actor="system:doctor_matcher",
            authorize=lambda actor, _exam_id, asset_type: (
                actor == "system:doctor_matcher"
                and asset_type in {"SIGNATURE", "STAMP_SEAL"}
            ),
        )
        return Image.open(BytesIO(content)).convert("RGB") if content else None
    path = _asset_path(value)
    if path is None or not path.is_file():
        return None
    return Image.open(path).convert("RGB")


def save_doctor_reference_assets(
    session: Session,
    doctor_id: int,
    candidate_id: int,
    source_page: int,
    signature_crop: Image.Image,
    stamp_crop: Image.Image,
    asset_root: Path | None = None,
) -> tuple[Path, Path]:
    """Save a manually reviewed signature/stamp pair as encrypted exam evidence."""
    if source_page not in {3, 4}:
        raise ValueError("Doctor references must come from report page 3 or 4.")

    doctor = session.get(Doctor, doctor_id)
    candidate = session.get(Candidate, candidate_id)
    if doctor is None or candidate is None:
        raise ValueError("The selected doctor or candidate no longer exists.")

    linked_exam = session.scalar(
        select(MedicalExamination)
        .where(
            MedicalExamination.candidate_id == candidate_id,
            MedicalExamination.examining_doctor_id == doctor_id,
        )
        .limit(1)
    )
    if candidate.doctor_id != doctor_id and linked_exam is None:
        raise ValueError("The selected candidate is not linked to this doctor.")
    if linked_exam is None:
        raise ValueError("Doctor references must be linked to a medical examination.")

    if any(
        (
            doctor.signature_image_path,
            doctor.stamp_image_path,
            doctor.signature_hash,
            doctor.stamp_hash,
        )
    ):
        raise ValueError("This doctor already has a saved reference pair.")

    signature_bytes = _encode_crop(signature_crop, "signature")
    stamp_bytes = _encode_crop(stamp_crop, "stamp")
    signature = store_evidence(
        session,
        examination_id=linked_exam.id,
        content=signature_bytes,
        asset_type="SIGNATURE",
        form_page_number=source_page,
        source_pdf_page_number=None,
        media_type="image/png",
        storage_root=asset_root,
    )
    stamp = store_evidence(
        session,
        examination_id=linked_exam.id,
        content=stamp_bytes,
        asset_type="STAMP_SEAL",
        form_page_number=source_page,
        source_pdf_page_number=None,
        media_type="image/png",
        storage_root=asset_root,
    )
    doctor.signature_image_path = signature.storage_key
    doctor.stamp_image_path = stamp.storage_key
    doctor.signature_hash = signature.sha256
    doctor.stamp_hash = stamp.sha256
    authentication = session.scalar(
        select(ExaminationAuthentication).where(
            ExaminationAuthentication.examination_id == linked_exam.id,
            ExaminationAuthentication.page_number == source_page,
        )
    )
    if authentication is None:
        authentication = ExaminationAuthentication(
            examination_id=linked_exam.id,
            page_number=source_page,
            actor_role="MEDICAL_EXAMINER",
        )
        session.add(authentication)
    authentication.doctor_id = doctor_id
    authentication.signature_status = "VERIFIED"
    authentication.stamp_status = "VERIFIED"
    authentication.signature_document_id = signature.id
    authentication.stamp_document_id = stamp.id
    identification = DoctorIdentification(
        candidate_id=candidate_id,
        doctor_id=doctor_id,
        source_page=source_page,
        identification_method="manual_reference_crop",
        stamp_detected=True,
        signature_detected=True,
        review_status="reviewed",
    )
    session.add(identification)
    session.flush()
    root = asset_root or private_storage_root()
    return root / signature.storage_key, root / stamp.storage_key
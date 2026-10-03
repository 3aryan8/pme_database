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
from .models import Candidate, Doctor, DoctorIdentification, MedicalExamination
from .report_images import find_report_images


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


def save_detected_doctor_assets(
    session: Session,
    doctor: Doctor,
    candidate: Candidate,
    document_id: str,
    region_root: Path | None = None,
) -> bool:
    """Persist candidate evidence and seed the doctor's canonical references."""
    signature_crop, stamp_crop, source_page = _region_crops(document_id, region_root)
    if source_page is None or (signature_crop is None and stamp_crop is None):
        return False

    directory = MAIN_PROJECT_ROOT / "data/processed/doctor_assets" / str(doctor.id)
    candidate_directory = directory / "candidates" / str(candidate.id)
    directory.mkdir(parents=True, exist_ok=True)
    candidate_directory.mkdir(parents=True, exist_ok=True)
    existing = session.scalar(
        select(DoctorIdentification)
        .where(
            DoctorIdentification.candidate_id == candidate.id,
            DoctorIdentification.doctor_id == doctor.id,
            DoctorIdentification.identification_method == "detected_reference_crop",
        )
        .limit(1)
    )
    saved = False
    evidence_paths: dict[str, str | None] = {
        "signature": existing.signature_image_path if existing else None,
        "stamp": existing.stamp_image_path if existing else None,
    }
    for label, crop, field in (
        ("signature", signature_crop, "signature_image_path"),
        ("stamp", stamp_crop, "stamp_image_path"),
    ):
        if crop is None or evidence_paths[label]:
            continue
        image_bytes = _encode_crop(crop, label)
        evidence_path = candidate_directory / f"{label}.png"
        evidence_path.write_bytes(image_bytes)
        evidence_paths[label] = _stored_path(evidence_path)
        if not getattr(doctor, field):
            canonical_path = directory / f"{label}.png"
            canonical_path.write_bytes(image_bytes)
            setattr(doctor, field, _stored_path(canonical_path))
            setattr(doctor, f"{label}_hash", sha256(image_bytes).hexdigest())
        saved = True

    if existing is not None:
        if not saved:
            return False
        existing.signature_image_path = evidence_paths["signature"]
        existing.stamp_image_path = evidence_paths["stamp"]
        existing.signature_detected = existing.signature_detected or signature_crop is not None
        existing.stamp_detected = existing.stamp_detected or stamp_crop is not None
    elif saved:
        session.add(
            DoctorIdentification(
                candidate_id=candidate.id,
                doctor_id=doctor.id,
                source_page=source_page,
                identification_method="detected_reference_crop",
                stamp_detected=stamp_crop is not None,
                signature_detected=signature_crop is not None,
                signature_image_path=evidence_paths["signature"],
                stamp_image_path=evidence_paths["stamp"],
                review_status="detected",
            )
        )
        session.flush()
    return saved


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
        signature_path = _asset_path(doctor.signature_image_path)
        stamp_path = _asset_path(doctor.stamp_image_path)
        scores: list[float] = []
        if signature_crop is not None and signature_path and signature_path.is_file():
            with Image.open(signature_path) as stored_signature:
                scores.append(_image_similarity(signature_crop, stored_signature))
        if stamp_crop is not None and stamp_path and stamp_path.is_file():
            with Image.open(stamp_path) as stored_stamp:
                scores.append(_image_similarity(stamp_crop, stored_stamp))
        if scores:
            score = sum(scores) / len(scores)
            if score > best_score:
                best_doctor, best_score = doctor, score

    if best_score < 0.78:
        return None, best_score
    return best_doctor, best_score


def save_doctor_reference_assets(
    session: Session,
    doctor_id: int,
    candidate_id: int,
    source_page: int,
    signature_crop: Image.Image,
    stamp_crop: Image.Image,
    asset_root: Path | None = None,
) -> tuple[Path, Path]:
    """Save one manually reviewed signature/stamp pair for a doctor."""
    if source_page not in {3, 4}:
        raise ValueError("Doctor references must come from report page 3 or 4.")

    doctor = session.get(Doctor, doctor_id)
    candidate = session.get(Candidate, candidate_id)
    if doctor is None or candidate is None:
        raise ValueError("The selected doctor or candidate no longer exists.")

    linked_exam = session.scalar(
        select(MedicalExamination.id)
        .where(
            MedicalExamination.candidate_id == candidate_id,
            MedicalExamination.examining_doctor_id == doctor_id,
        )
        .limit(1)
    )
    if candidate.doctor_id != doctor_id and linked_exam is None:
        raise ValueError("The selected candidate is not linked to this doctor.")

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
    directory = (asset_root or MAIN_PROJECT_ROOT / "data/processed/doctor_assets") / str(doctor_id)
    signature_path = directory / "signature.png"
    stamp_path = directory / "stamp.png"
    if signature_path.exists() or stamp_path.exists():
        raise ValueError("Reference image files already exist for this doctor.")

    directory.mkdir(parents=True, exist_ok=True)
    signature_tmp = directory / ".signature.png.tmp"
    stamp_tmp = directory / ".stamp.png.tmp"
    try:
        signature_tmp.write_bytes(signature_bytes)
        stamp_tmp.write_bytes(stamp_bytes)
        signature_tmp.replace(signature_path)
        stamp_tmp.replace(stamp_path)

        doctor.signature_image_path = _stored_path(signature_path)
        doctor.stamp_image_path = _stored_path(stamp_path)
        doctor.signature_hash = sha256(signature_bytes).hexdigest()
        doctor.stamp_hash = sha256(stamp_bytes).hexdigest()
        session.add(
            DoctorIdentification(
                candidate_id=candidate_id,
                doctor_id=doctor_id,
                source_page=source_page,
                identification_method="manual_reference_crop",
                stamp_detected=True,
                signature_detected=True,
                review_status="reviewed",
            )
        )
        session.flush()
    except Exception:
        signature_tmp.unlink(missing_ok=True)
        stamp_tmp.unlink(missing_ok=True)
        signature_path.unlink(missing_ok=True)
        stamp_path.unlink(missing_ok=True)
        raise

    return signature_path, stamp_path
from __future__ import annotations

import json
import logging
from hashlib import sha256
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from sqlalchemy import select

from src.database.database import get_session
from src.database.doctor_utils import normalize_doctor_name
from src.database.models import Candidate, Doctor, DoctorIdentification

LOGGER = logging.getLogger("doctor_pipeline")

PAGE_PREFERENCE = ("page_0003.png", "page_0004.png")
SIGNATURE_ROOT = Path(__file__).resolve().parent / "doctors"
SIGNATURE_EMBEDDING_SIZE = (32, 16)
SIGNATURE_MATCH_THRESHOLD = 0.82


def extract_doctor_region(image_path: Path) -> np.ndarray:
    """Crop the lower-right medical-examiner region where signature/stamp usually live."""
    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(f"Unable to read image: {image_path}")

    height, width = image.shape[:2]
    x_start = max(0, int(width * 0.18))
    y_start = max(0, int(height * 0.62))
    x_end = min(width, int(width * 0.96))
    y_end = min(height, int(height * 0.98))
    return image[y_start:y_end, x_start:x_end]


def extract_signature(image: np.ndarray) -> np.ndarray:
    """Return a normalized signature crop for comparison."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return cv2.resize(gray, (128, 64))
    x, y, w, h = cv2.boundingRect(max(contours, key=cv2.contourArea))
    crop = gray[max(0, y - 10):min(gray.shape[0], y + h + 10), max(0, x - 10):min(gray.shape[1], x + w + 10)]
    return cv2.resize(crop, (128, 64), interpolation=cv2.INTER_AREA)


def extract_stamp(image: np.ndarray) -> np.ndarray:
    """Return a normalized stamp crop for OCR and hashing."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    _, thresh = cv2.threshold(blur, 165, 255, cv2.THRESH_BINARY)
    return cv2.resize(thresh, (256, 128), interpolation=cv2.INTER_AREA)


def signature_embedding(signature: np.ndarray) -> list[float]:
    """Create a compact, normalized image embedding for a signature."""
    gray = cv2.cvtColor(signature, cv2.COLOR_BGR2GRAY) if signature.ndim == 3 else signature
    resized = cv2.resize(gray, SIGNATURE_EMBEDDING_SIZE, interpolation=cv2.INTER_AREA)
    values = resized.astype(np.float32).reshape(-1)
    values = (values - values.mean()) / (values.std() + 1e-6)
    return values.tolist()


def compare_signature_embeddings(reference: list[float], candidate: list[float]) -> float:
    """Return cosine similarity for two persisted signature embeddings."""
    reference_array = np.asarray(reference, dtype=np.float32)
    candidate_array = np.asarray(candidate, dtype=np.float32)
    if reference_array.shape != candidate_array.shape or not reference_array.size:
        return 0.0
    denominator = float(np.linalg.norm(reference_array) * np.linalg.norm(candidate_array))
    if denominator == 0.0:
        return 0.0
    return float(np.clip(np.dot(reference_array, candidate_array) / denominator, -1.0, 1.0))


def ocr_doctor_stamp(image_path: Path) -> dict[str, Any]:
    """Extract OCR text from the stamp region and normalize it."""
    try:
        import easyocr
    except ModuleNotFoundError:
        return {"text": "", "confidence": 0.0, "source": "ocr_unavailable"}

    region = extract_doctor_region(image_path)
    stamp = extract_stamp(region)
    temp_path = image_path.with_suffix(".stamp_temp.png")
    cv2.imwrite(str(temp_path), stamp)
    try:
        reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        results = reader.readtext(str(temp_path), detail=1, paragraph=False)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)

    text_parts: list[str] = []
    confidences: list[float] = []
    for box, text, conf in results:
        cleaned = (text or "").strip()
        if cleaned:
            text_parts.append(cleaned)
            confidences.append(float(conf))

    normalized_text = " ".join(text_parts)
    confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return {"text": normalized_text, "confidence": confidence, "source": "easyocr"}


def match_signature(reference: np.ndarray, candidate: np.ndarray) -> float:
    """Return a lightweight similarity score between two signature images."""
    ref = cv2.cvtColor(reference, cv2.COLOR_BGR2GRAY) if reference.ndim == 3 else reference
    cand = cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY) if candidate.ndim == 3 else candidate

    ref = cv2.resize(ref, (128, 64), interpolation=cv2.INTER_AREA)
    cand = cv2.resize(cand, (128, 64), interpolation=cv2.INTER_AREA)

    ref = cv2.threshold(ref, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    cand = cv2.threshold(cand, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]

    difference = cv2.absdiff(ref, cand)
    score = 1.0 - (np.count_nonzero(difference) / float(difference.size))
    return float(max(0.0, min(1.0, score)))


def select_candidate_page(candidate_dir: Path) -> Path | None:
    """Prefer page 3 and fall back to page 4 when the primary page is missing."""
    for page_name in PAGE_PREFERENCE:
        candidate_page = candidate_dir / page_name
        if candidate_page.exists():
            return candidate_page
    return None


def save_doctor_reference(
    doctor: Doctor,
    signature_path: Path | None,
    stamp_path: Path | None,
    embedding: list[float] | None = None,
) -> None:
    """Store per-doctor reference images and metadata under the signature folder."""
    if doctor.id is None:
        raise ValueError("Doctor must be persisted before saving reference files.")

    doctor_dir = SIGNATURE_ROOT / f"doctor_{doctor.id:04d}"
    doctor_dir.mkdir(parents=True, exist_ok=True)

    if signature_path and signature_path.exists() and not doctor.signature_image_path:
        destination = doctor_dir / "signature.png"
        destination.write_bytes(signature_path.read_bytes())
        doctor.signature_image_path = str(destination)
        doctor.signature_hash = sha256(destination.read_bytes()).hexdigest()

    if stamp_path and stamp_path.exists() and not doctor.stamp_image_path:
        destination = doctor_dir / "stamp.png"
        destination.write_bytes(stamp_path.read_bytes())
        doctor.stamp_image_path = str(destination)
        doctor.stamp_hash = sha256(destination.read_bytes()).hexdigest()

    if embedding:
        (doctor_dir / "signature_embedding.json").write_text(
            json.dumps(embedding), encoding="utf-8"
        )

    metadata = {
        "doctor_id": doctor.id,
        "full_name_hindi": doctor.full_name_hindi,
        "full_name_english": doctor.full_name_english,
        "designation": doctor.designation,
    }
    (doctor_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


def find_signature_match(
    session,
    embedding: list[float],
    threshold: float = SIGNATURE_MATCH_THRESHOLD,
) -> tuple[Doctor | None, float]:
    """Find the closest persisted doctor signature above the match threshold."""
    best_doctor: Doctor | None = None
    best_score = -1.0
    for doctor in session.scalars(select(Doctor)).all():
        if not doctor.signature_image_path:
            continue
        embedding_path = Path(doctor.signature_image_path).parent / "signature_embedding.json"
        if not embedding_path.exists():
            signature_path = Path(doctor.signature_image_path)
            if not signature_path.exists():
                continue
            signature = cv2.imread(str(signature_path), cv2.IMREAD_GRAYSCALE)
            if signature is None:
                continue
            saved_embedding = signature_embedding(signature)
        else:
            saved_embedding = json.loads(embedding_path.read_text(encoding="utf-8"))
        score = compare_signature_embeddings(saved_embedding, embedding)
        if score > best_score:
            best_doctor, best_score = doctor, score
    if best_score < threshold:
        return None, best_score
    return best_doctor, best_score


def _write_image(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), image):
        raise RuntimeError(f"Unable to save image: {path}")


def find_existing_doctor(session, full_name: str | None, designation: str | None = None) -> Doctor | None:
    """Look for an existing doctor using the normalized English/Hindi name and designation."""
    if not full_name:
        return None

    normalized = normalize_doctor_name(full_name)
    candidates = []
    if normalized:
        candidates.append((Doctor.full_name_english == normalized))
    candidates.append((Doctor.doctor_name == full_name))

    if designation:
        candidates.append((Doctor.designation == designation))

    clause = None
    for condition in candidates:
        clause = condition if clause is None else (clause | condition)

    if clause is None:
        return None

    return session.scalar(select(Doctor).where(clause).limit(1))


def assign_doctor_to_candidate(session, candidate: Candidate, doctor_name: str | None, designation: str | None = None) -> tuple[Doctor | None, str]:
    """Create or reuse a doctor record and attach it to the candidate."""
    if not doctor_name:
        return None, "unknown"

    doctor = find_existing_doctor(session, doctor_name, designation)
    if doctor is None:
        normalized = normalize_doctor_name(doctor_name)
        doctor = Doctor(
            doctor_name=doctor_name,
            full_name_english=normalized or doctor_name,
            full_name_hindi=None,
            designation=designation,
            doctor_role="Railway Medical Examiner",
        )
        session.add(doctor)
        session.flush()
        LOGGER.info("Created doctor record for %s", doctor.full_name_english)
    else:
        LOGGER.info("Matched existing doctor %s", doctor.full_name_english)

    candidate.doctor_id = doctor.id
    session.flush()
    return doctor, "auto_verified"


def process_candidate_dir(candidate_dir: Path) -> dict[str, object]:
    """Process one candidate directory and return an audit record."""
    with get_session() as session:
        candidate = session.scalar(select(Candidate).where(Candidate.roll_number == candidate_dir.name))
        if candidate is None:
            return {"candidate": candidate_dir.name, "status": "skipped", "doctor": None}

        page_path = select_candidate_page(candidate_dir)
        if page_path is None:
            return {"candidate": candidate.candidate_name or candidate.roll_number, "status": "missing_page", "doctor": None}

        region = extract_doctor_region(page_path)
        signature = extract_signature(region)
        stamp = extract_stamp(region)
        embedding = signature_embedding(signature)
        doctor, match_score = find_signature_match(session, embedding)
        ocr_payload: dict[str, Any] = {"text": "", "confidence": 0.0, "source": "signature_match"}
        status = "signature_matched"

        if doctor is None:
            doctor_name = None
            designation = None
            ocr_payload = ocr_doctor_stamp(page_path)
            if ocr_payload.get("text"):
                normalized = normalize_doctor_name(ocr_payload["text"])
                doctor_name = normalized or ocr_payload["text"]
                designation = "DMO/BRC" if "DMO" in (ocr_payload["text"] or "").upper() else None

            if (candidate_dir / "doctor_reference.json").exists():
                payload = json.loads((candidate_dir / "doctor_reference.json").read_text(encoding="utf-8"))
                doctor_name = payload.get("full_name_english") or doctor_name or payload.get("doctor_name")
                designation = payload.get("designation") or designation

            doctor, status = assign_doctor_to_candidate(session, candidate, doctor_name, designation)
            if doctor is not None:
                status = "ocr"
        if doctor is not None:
            candidate.doctor_id = doctor.id
            session.flush()
            doctor_dir = SIGNATURE_ROOT / f"doctor_{doctor.id:04d}"
            evidence_dir = doctor_dir / "candidates" / candidate_dir.name
            signature_path = evidence_dir / "signature.png"
            stamp_path = evidence_dir / "stamp.png"
            _write_image(signature_path, signature)
            _write_image(stamp_path, stamp)
            save_doctor_reference(doctor, signature_path, stamp_path, embedding)
            identification = session.scalar(
                select(DoctorIdentification)
                .where(
                    DoctorIdentification.candidate_id == candidate.id,
                    DoctorIdentification.doctor_id == doctor.id,
                )
                .order_by(DoctorIdentification.id.desc())
                .limit(1)
            )
            if identification is None:
                identification = DoctorIdentification(
                    candidate_id=candidate.id,
                    doctor_id=doctor.id,
                )
                session.add(identification)
            identification.source_page = int(page_path.stem.split("_")[-1])
            identification.identification_method = status
            identification.confidence = (
                match_score
                if status == "signature_matched"
                else float(ocr_payload.get("confidence") or 0.0)
            )
            identification.stamp_detected = True
            identification.signature_detected = True
            identification.signature_image_path = str(signature_path)
            identification.stamp_image_path = str(stamp_path)
            identification.review_status = "matched" if status == "signature_matched" else "ocr"
        session.commit()
        return {
            "candidate": candidate.candidate_name or candidate.roll_number,
            "status": status,
            "doctor": doctor.full_name_english if doctor else None,
            "page_used": page_path.name,
            "ocr_text": ocr_payload.get("text"),
            "signature_match_score": None if match_score < 0 else match_score,
        }


def process_candidate_directory_set(root: Path) -> list[dict[str, object]]:
    """Process all candidate directories under a root folder."""
    results: list[dict[str, object]] = []
    for candidate_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        results.append(process_candidate_dir(candidate_dir))
    return results


def summarize_results(results: list[dict[str, object]]) -> dict[str, int]:
    summary = {
        "total": len(results),
        "auto_verified": 0,
        "signature_matched": 0,
        "ocr": 0,
        "skipped": 0,
        "unknown": 0,
        "missing_page": 0,
    }
    for item in results:
        status = item.get("status")
        if status in {"auto_verified"}:
            summary["auto_verified"] += 1
        elif status == "signature_matched":
            summary["signature_matched"] += 1
        elif status == "ocr":
            summary["ocr"] += 1
        elif status == "unknown":
            summary["unknown"] += 1
        elif status == "missing_page":
            summary["missing_page"] += 1
        else:
            summary["skipped"] += 1
    return summary


def main() -> None:
    image_root = Path("data/interim/high_res_clean")
    if not image_root.exists():
        image_root = Path("data/interim/high_res")

    if not image_root.exists():
        raise FileNotFoundError(f"Expected candidate images under {image_root}")

    results = process_candidate_directory_set(image_root)
    summary = summarize_results(results)
    LOGGER.info("Processed %s candidates: %s", summary["total"], summary)
    for item in results:
        LOGGER.info("%s -> %s -> %s", item.get("candidate"), item.get("doctor"), item.get("status"))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()

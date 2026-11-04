from pathlib import Path

import cv2
import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from signature.doctor_pipeline import (
    compare_signature_embeddings,
    find_signature_match,
    save_doctor_reference,
    signature_embedding,
)
from src.database.models import Base, Doctor


def _signature_image(variant: int = 0) -> np.ndarray:
    image = np.full((64, 128), 255, dtype=np.uint8)
    cv2.line(image, (10, 45), (60, 20 + variant), 0, 3)
    cv2.line(image, (60, 20 + variant), (115, 42), 0, 3)
    return image


def test_signature_embeddings_match_identical_signatures() -> None:
    first = signature_embedding(_signature_image())
    second = signature_embedding(_signature_image())

    assert compare_signature_embeddings(first, second) > 0.99


def test_find_signature_match_returns_saved_doctor(tmp_path: Path) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    signature_path = tmp_path / "signature.png"
    assert cv2.imwrite(str(signature_path), _signature_image())

    with Session(engine) as session:
        doctor = Doctor(full_name_english="DR. SAVED")
        doctor.signature_image_path = str(signature_path)
        session.add(doctor)
        session.commit()

        match, score = find_signature_match(
            session,
            signature_embedding(_signature_image()),
            threshold=0.82,
        )

    assert match is not None
    assert match.full_name_english == "DR. SAVED"
    assert score > 0.99


def test_save_doctor_reference_does_not_replace_canonical_signature(
    tmp_path: Path,
    monkeypatch,
) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    first_path = tmp_path / "first.png"
    second_path = tmp_path / "second.png"
    assert cv2.imwrite(str(first_path), _signature_image())
    assert cv2.imwrite(str(second_path), _signature_image(1))
    import signature.doctor_pipeline as pipeline

    monkeypatch.setattr(pipeline, "SIGNATURE_ROOT", tmp_path / "doctors")

    with Session(engine) as session:
        doctor = Doctor(full_name_english="DR. IMMUTABLE")
        session.add(doctor)
        session.flush()
        save_doctor_reference(doctor, first_path, None, signature_embedding(_signature_image()))
        canonical_bytes = Path(doctor.signature_image_path).read_bytes()
        save_doctor_reference(doctor, second_path, None, signature_embedding(_signature_image(1)))

    assert Path(doctor.signature_image_path).read_bytes() == canonical_bytes

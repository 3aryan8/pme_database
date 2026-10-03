from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src.database.database import init_db
from src.database.doctor_assets import save_doctor_reference_assets
from src.database.importer import merge_doctor_aliases
from src.database.models import (
    Base,
    Candidate,
    Doctor,
    DoctorIdentification,
    FitnessClassification,
    MedicalExamination,
)
from src.database.repository import get_candidates_by_doctor, get_doctor_directory, search_doctors
from src.database.doctor_utils import normalize_doctor_name
from src.models.fields import leaf_specs
from src.utils.config_loader import config


def test_normalize_doctor_name_handles_common_variants() -> None:
    assert normalize_doctor_name("DR. DARSHANSINH SOLANKI DMO/BRC") == "DR. DARSHANSINH SOLANKI"
    assert normalize_doctor_name("Dr. Darshansinh Solanki") == "DR. DARSHANSINH SOLANKI"
    assert normalize_doctor_name("Dr. A. ROBIN") == "DR. A. ROBIN"
    assert normalize_doctor_name("DR. A. ROBIN DMO I BRC") == "DR. A. ROBIN"
    assert normalize_doctor_name("DR. PARAG ADHIYAPAK") == "DR. PARAG ADHYAPAK"
    assert normalize_doctor_name("DR. PARAG ADHYAPAK S. DMO/BRC") == "DR. PARAG ADHYAPAK"


def test_merge_doctor_aliases_preserves_candidate_and_examination_links() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        canonical = Doctor(full_name_english="DR. PARAG ADHYAPAK")
        alias = Doctor(full_name_english="DR. PARAG ADHIYAPAK")
        session.add_all([canonical, alias])
        session.flush()
        candidate = Candidate(
            roll_number="ROLL-ALIAS",
            candidate_name="ALIAS CANDIDATE",
            doctor_id=alias.id,
        )
        session.add(candidate)
        session.flush()
        examination = MedicalExamination(
            candidate_id=candidate.id,
            examining_doctor_id=alias.id,
        )
        session.add(examination)
        session.flush()
        identification = DoctorIdentification(
            candidate_id=candidate.id,
            doctor_id=alias.id,
        )
        session.add(identification)
        session.commit()

        assert merge_doctor_aliases(session) == 1
        session.commit()

        doctors = list(session.scalars(select(Doctor)).all())
        assert [doctor.full_name_english for doctor in doctors] == [
            "DR. PARAG ADHYAPAK"
        ]
        assert candidate.doctor_id == canonical.id
        assert examination.examining_doctor_id == canonical.id
        assert identification.doctor_id == canonical.id


def test_save_doctor_reference_assets_stores_once_with_review_record(tmp_path: Path) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        doctor = Doctor(full_name_english="DR. TEST")
        session.add(doctor)
        session.flush()
        candidate = Candidate(
            roll_number="ROLL-ASSET",
            candidate_name="ASSET CANDIDATE",
            doctor_id=doctor.id,
        )
        session.add(candidate)
        session.commit()

        signature = Image.new("RGB", (80, 28), "white")
        stamp = Image.new("RGB", (120, 70), "white")
        signature_path, stamp_path = save_doctor_reference_assets(
            session,
            doctor.id,
            candidate.id,
            3,
            signature,
            stamp,
            asset_root=tmp_path,
        )
        session.commit()

        session.refresh(doctor)
        assert signature_path.is_file()
        assert stamp_path.is_file()
        assert doctor.signature_image_path == str(signature_path)
        assert doctor.stamp_image_path == str(stamp_path)
        assert doctor.signature_hash
        assert doctor.stamp_hash
        identification = session.scalar(select(DoctorIdentification))
        assert identification is not None
        assert identification.candidate_id == candidate.id
        assert identification.doctor_id == doctor.id
        assert identification.source_page == 3
        assert identification.review_status == "reviewed"

        with pytest.raises(ValueError, match="already has a saved reference pair"):
            save_doctor_reference_assets(
                session,
                doctor.id,
                candidate.id,
                3,
                signature,
                stamp,
                asset_root=tmp_path,
            )


def test_doctor_lookup_and_candidate_linking() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        doctor = Doctor(
            full_name_english="DR. DARSHANSINH SOLANKI",
            full_name_hindi="डॉ. दर्शनसिह सोलंकी",
            designation="DMO/BRC",
        )
        session.add(doctor)
        session.flush()

        candidate_a = Candidate(
            roll_number="ROLL-001",
            candidate_name="CANDIDATE A",
            father_name="FATHER A",
            doctor_id=doctor.id,
        )
        candidate_b = Candidate(
            roll_number="ROLL-002",
            candidate_name="CANDIDATE B",
            father_name="FATHER B",
            doctor_id=doctor.id,
        )
        session.add_all([candidate_a, candidate_b])
        session.commit()

        matches = search_doctors(session, "darshansinh")
        assert [doctor.full_name_english for doctor in matches] == ["DR. DARSHANSINH SOLANKI"]

        approved = get_candidates_by_doctor(session, doctor.id)
        assert {candidate.roll_number for candidate in approved} == {"ROLL-001", "ROLL-002"}


def test_doctor_candidate_search_combines_medical_and_fitness_filters() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        doctor = Doctor(full_name_english="DR. TEST")
        session.add(doctor)
        session.flush()

        matching_candidate = Candidate(
            roll_number="ROLL-MATCH",
            candidate_name="MATCHING CANDIDATE",
            doctor_id=doctor.id,
        )
        medical_mismatch_candidate = Candidate(
            roll_number="ROLL-MEDICAL-MISMATCH",
            candidate_name="MEDICAL MISMATCH",
            doctor_id=doctor.id,
        )
        fitness_mismatch_candidate = Candidate(
            roll_number="ROLL-FITNESS-MISMATCH",
            candidate_name="FITNESS MISMATCH",
            doctor_id=doctor.id,
        )
        session.add_all(
            [matching_candidate, medical_mismatch_candidate, fitness_mismatch_candidate]
        )
        session.flush()

        for candidate, medical_class, fit_in_class in (
            (matching_candidate, "A3", "FIT-A3"),
            (medical_mismatch_candidate, "B1", "FIT-A3"),
            (fitness_mismatch_candidate, "A3", "FIT-B1"),
        ):
            examination = MedicalExamination(
                candidate_id=candidate.id,
                examining_doctor_id=doctor.id,
                medical_class=medical_class,
            )
            session.add(examination)
            session.flush()
            session.add(
                FitnessClassification(
                    examination_id=examination.id,
                    fit_in_class=fit_in_class,
                )
            )
        session.commit()

        matches = get_candidates_by_doctor(
            session,
            doctor.id,
            medical_class="A3",
            fit_in_class="FIT-A3",
        )
        assert [candidate.roll_number for candidate in matches] == ["ROLL-MATCH"]


def test_schema_exposes_doctor_name_fields_on_pages_3_and_4() -> None:
    leaves = set(leaf_specs(config.schema).keys())
    assert "page_3_fitness_classification.doctor_name" in leaves
    assert "page_4_declarations.doctor_name" in leaves


def test_search_doctors_repairs_stale_sqlite_schema() -> None:
    db_path = Path("/tmp/test_pme_doctor_stale_schema.sqlite3")
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE doctors (id INTEGER PRIMARY KEY, doctor_name TEXT, full_name_english TEXT, designation TEXT, doctor_role TEXT, created_at DATETIME, updated_at DATETIME)"
    )
    conn.execute(
        "INSERT INTO doctors (doctor_name, full_name_english, designation, doctor_role) VALUES (?, ?, ?, ?)",
        ("Dr. Naveen V.T.", "DR. NAVEEN V.T.", "DMO/BRC", "Railway Medical Examiner"),
    )
    conn.commit()
    conn.close()

    engine = create_engine(f"sqlite:///{db_path}")
    with Session(engine) as session:
        assert search_doctors(session, "naveen")

    db_path.unlink(missing_ok=True)


def test_doctor_directory_lists_all_saved_doctors() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        doctor_a = Doctor(
            doctor_name="Dr. A",
            full_name_english="DR. A",
            designation="DMO",
        )
        doctor_b = Doctor(
            doctor_name="Dr. B",
            full_name_english="DR. B",
            designation="BRC",
        )
        session.add_all([doctor_a, doctor_b])
        session.commit()

        doctors = get_doctor_directory(session)
        assert [doctor.full_name_english for doctor in doctors] == ["DR. A", "DR. B"]

        candidate = Candidate(
            roll_number="ROLL-101",
            candidate_name="CANDIDATE ONE",
            father_name="FATHER ONE",
            date_of_birth=date(1996, 2, 21),
            doctor_id=doctor_b.id,
        )
        session.add(candidate)
        session.commit()

        assert candidate.doctor_id == doctor_b.id

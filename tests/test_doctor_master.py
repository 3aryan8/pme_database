from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.database.database import init_db
from src.database.models import Base, Candidate, Doctor
from src.database.repository import get_candidates_by_doctor, get_doctor_directory, search_doctors
from src.database.doctor_utils import normalize_doctor_name
from src.models.fields import leaf_specs
from src.utils.config_loader import config


def test_normalize_doctor_name_handles_common_variants() -> None:
    assert normalize_doctor_name("DR. DARSHANSINH SOLANKI DMO/BRC") == "DR. DARSHANSINH SOLANKI"
    assert normalize_doctor_name("Dr. Darshansinh Solanki") == "DR. DARSHANSINH SOLANKI"
    assert normalize_doctor_name("Dr. A. ROBIN") == "DR. A. ROBIN"


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

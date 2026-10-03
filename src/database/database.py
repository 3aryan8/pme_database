# Phase: database connection | Input: configured database URL | Output: SQLAlchemy engine and sessions | Command: ``uv run python -m src.database.run_database --help``.
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from .config import get_database_url
from .models import Base


DATABASE_URL = get_database_url()

connect_args = (
    {"check_same_thread": False}
    if DATABASE_URL.startswith("sqlite")
    else {}
)

engine = create_engine(
    DATABASE_URL,
    future=True,
    pool_pre_ping=True,
    connect_args=connect_args,
)

SessionLocal = sessionmaker(
    bind=engine,
    expire_on_commit=False,
)


def _ensure_sqlite_doctor_columns(target_engine=None) -> None:
    target = target_engine or engine
    database_url = str(target.url)

    if not database_url.startswith("sqlite"):
        return

    with target.begin() as connection:
        inspector = inspect(connection)
        if not inspector.has_table("doctors"):
            Base.metadata.create_all(target)
            return

        if inspector.has_table("candidates"):
            candidate_columns = {column["name"] for column in inspector.get_columns("candidates")}
            if "doctor_id" not in candidate_columns:
                connection.execute(text("ALTER TABLE candidates ADD COLUMN doctor_id INTEGER"))
                connection.execute(
                    text(
                        "UPDATE candidates SET doctor_id = ("
                        "SELECT examining_doctor_id FROM medical_examinations "
                        "WHERE medical_examinations.candidate_id = candidates.id "
                        "ORDER BY medical_examinations.medical_examination_date DESC, "
                        "medical_examinations.id DESC LIMIT 1) "
                        "WHERE doctor_id IS NULL"
                    )
                )

        doctor_columns = {column["name"] for column in inspector.get_columns("doctors")}
        for column_name, column_sql in {
            "full_name_hindi": "VARCHAR(200)",
            "full_name_english": "VARCHAR(200)",
            "designation": "VARCHAR(200)",
            "signature_image_path": "VARCHAR(500)",
            "stamp_image_path": "VARCHAR(500)",
            "signature_hash": "VARCHAR(128)",
            "stamp_hash": "VARCHAR(128)",
            "created_at": "DATETIME",
            "updated_at": "DATETIME",
        }.items():
            if column_name not in doctor_columns:
                connection.execute(
                    text(f"ALTER TABLE doctors ADD COLUMN {column_name} {column_sql}")
                )

        if inspector.has_table("candidates"):
            existing_indexes = inspector.get_indexes("candidates")
            if not any(index["name"] == "ix_candidates_doctor_id" for index in existing_indexes):
                connection.execute(text("CREATE INDEX ix_candidates_doctor_id ON candidates (doctor_id)"))

        existing_indexes = inspector.get_indexes("doctors")
        names = {index["name"] for index in existing_indexes}
        if "ix_doctors_full_name_english" not in names:
            connection.execute(text("CREATE INDEX ix_doctors_full_name_english ON doctors (full_name_english)"))

        if inspector.has_table("doctor_identifications"):
            identification_columns = {
                column["name"]
                for column in inspector.get_columns("doctor_identifications")
            }
            for column_name in ("signature_image_path", "stamp_image_path"):
                if column_name not in identification_columns:
                    connection.execute(
                        text(
                            f"ALTER TABLE doctor_identifications "
                            f"ADD COLUMN {column_name} VARCHAR(500)"
                        )
                    )


def init_db(target_engine=None):
    target = target_engine or engine
    Base.metadata.create_all(target)
    _ensure_sqlite_doctor_columns(target)


def get_session():
    return SessionLocal()
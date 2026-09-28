"""Tests for normalized database record discovery and import.

Phase: database import. Input: temporary canonical and sidecar JSON files. Output: isolated SQLite rows and validation outcomes. Command: ``uv run pytest tests/test_database_importer.py -q``.
"""
import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from src.database import importer
from src.database.models import Base, Candidate
from src.database.schemas import PMEExtraction
from scripts.validate_extractions import canonical_records


@pytest.fixture()
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    database_session = session_factory()
    try:
        yield database_session
    finally:
        database_session.close()
        engine.dispose()


def test_import_directory_only_processes_canonical_records(
    session,
    monkeypatch,
    tmp_path,
):
    extraction = PMEExtraction(
        document_id="canonical-document",
        fields={
            "page_1_basic_info": {
                "general_details": {"candidate_name": "CANONICAL NAME"},
                "narrative_details": {"roll_number": "ROLL-1"},
            }
        },
    )
    extraction_dir = tmp_path / extraction.document_id
    extraction_dir.mkdir()
    extraction_path = extraction_dir / "record.json"
    extraction_path.write_text(extraction.model_dump_json())

    sidecar = extraction.model_dump(mode="json")
    sidecar["fields"]["page_1_basic_info"]["general_details"][
        "candidate_name"
    ] = "SIDECAR NAME"
    (extraction_dir / "document.json").write_text(json.dumps(sidecar))

    monkeypatch.setattr(importer, "find_report_images", lambda *args, **kwargs: [])

    successful, failed = importer.import_directory(session, tmp_path)

    candidate = session.scalar(
        select(Candidate).where(Candidate.roll_number == "ROLL-1")
    )
    assert (successful, failed) == (1, 0)
    assert candidate is not None
    assert candidate.candidate_name == "CANONICAL NAME"


def test_validation_discovers_only_canonical_records(tmp_path):
    extraction_dir = tmp_path / "document"
    extraction_dir.mkdir()
    (extraction_dir / "record.json").write_text("{}")
    (extraction_dir / "document.json").write_text("{}")

    assert canonical_records(tmp_path) == [extraction_dir / "record.json"]
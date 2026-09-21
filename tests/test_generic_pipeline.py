"""Tests for the generic text -> LLM -> schema -> DB pipeline.

Covers: prompt built from the schema class, tolerant JSON recovery,
validation at the trust boundary, and the zero-touch property — save /
retrieve / list working for ANY SQLModel class, including one defined
here in the test that no other code knows about.
"""
from datetime import date

import pytest
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.extraction_schema import MedicalExaminationRecord, ReportTableRow
from src.database.extractor import (
    ExtractionError,
    LLMExtractor,
    build_prompt,
    first_json_object,
)
from src.database.models import Base
from src.database.store import all_rows, get, save


class FakeClient:
    """Stands in for any LLM backend; only needs complete(prompt) -> str."""

    def __init__(self, reply: str):
        self.reply = reply
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.reply


CANNED = (
    'Here you go:\n```json\n'
    '{"document_id": "DOC-1", "candidate_name": "RAVI KUMAR", '
    '"roll_number": "116244151979349", "date_of_birth": "1992-08-12", '
    '"urine": "NORMAL", "sugar": "ABSENT", '
    '"distance_vision_right": "6/6", "distance_vision_left": "6/9", '
    '"fitness_classification": "FIT IN CLASS SSB", '
    '"rows": [{"section": "vision", "row_label": "Distance vision", '
    '          "value_right": "6/6", "value_left": "6/9"},'
    '         {"section": "vision", "row_label": "Near vision", '
    '          "value_right": "60/60", "value_left": "60/60"}]}\n```'
)


@pytest.fixture()
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


# ---------------------------------------------------------------- extract


def test_build_prompt_contains_schema_and_text():
    prompt = build_prompt(MedicalExaminationRecord, "CANDIDATE : RAVI")
    for field in ("candidate_name", "roll_number", "distance_vision_right", "rows"):
        assert field in prompt
    assert "CANDIDATE : RAVI" in prompt
    assert "ONLY one JSON object" in prompt


def test_first_json_object_finds_embedded_json():
    raw = 'Sure! Here is the JSON:\n```json\n{"a": {"b": "c}"}}\n```\nDone.'
    assert first_json_object(raw) == '{"a": {"b": "c}"}}'
    assert first_json_object("no json here") is None


def test_extract_returns_validated_instance():
    client = FakeClient(CANNED)
    extractor = LLMExtractor(client)
    record = extractor.extract("whatever report text", MedicalExaminationRecord)

    assert isinstance(record, MedicalExaminationRecord)
    assert record.document_id == "DOC-1"
    assert record.date_of_birth == date(1992, 8, 12)
    assert [row.row_label for row in record.rows] == ["Distance vision", "Near vision"]
    # the LLM was asked for exactly this schema's fields
    assert "candidate_name" in client.prompts[0]


def test_extract_rejects_output_without_json():
    extractor = LLMExtractor(FakeClient("I cannot do that."))
    with pytest.raises(ExtractionError):
        extractor.extract("some text", MedicalExaminationRecord)


def test_extract_rejects_values_that_fail_validation():
    extractor = LLMExtractor(FakeClient('{"date_of_birth": "not-a-date"}'))
    with pytest.raises(ExtractionError):
        extractor.extract("some text", MedicalExaminationRecord)


def test_extract_rejects_empty_input():
    extractor = LLMExtractor(FakeClient(CANNED))
    with pytest.raises(ExtractionError):
        extractor.extract("   ", MedicalExaminationRecord)


# ------------------------------------------------------------------- store


def test_save_and_retrieve_roundtrip(session):
    record = MedicalExaminationRecord(
        document_id="DOC-1",
        candidate_name="RAVI KUMAR",
        roll_number="116244151979349",
        distance_vision_right="6/6",
        rows=[
            ReportTableRow(
                section="vision",
                row_label="Distance vision",
                value_right="6/6",
                value_left="6/9",
            )
        ],
    )

    record_id = save(record, session)
    assert record_id >= 1

    loaded = get(MedicalExaminationRecord, record_id, session)
    assert loaded.candidate_name == "RAVI KUMAR"
    assert loaded.distance_vision_right == "6/6"
    # nested rows round-tripped through the generic store untouched
    assert len(loaded.rows) == 1
    assert loaded.rows[0].value_left == "6/9"
    assert len(all_rows(MedicalExaminationRecord, session)) == 1


def test_save_any_schema_zero_touch(session):
    """The zero-touch property: a brand-new schema class defined HERE —
    extractor, store, and pipeline code know nothing about it, yet it
    saves and retrieves without any code change (nested fields included)."""

    class LabResult(BaseModel):
        model_config = ConfigDict(extra="ignore")

        sample_id: str
        glucose: float | None = None
        cholesterol: float | None = None  # a field added "later"
        notes: list[str] = Field(default_factory=list)

    record_id = save(LabResult(sample_id="L-9", glucose=5.4, notes=["ok"]), session)

    loaded = get(LabResult, record_id, session)
    assert loaded.glucose == 5.4
    assert loaded.cholesterol is None  # new field, no code touched
    assert loaded.notes == ["ok"]
    assert len(all_rows(LabResult, session)) == 1

    # other schemas' records are not mixed into this class's rows
    save(MedicalExaminationRecord(document_id="OTHER"), session)
    assert len(all_rows(MedicalExaminationRecord, session)) == 1
    assert len(all_rows(LabResult, session)) == 1

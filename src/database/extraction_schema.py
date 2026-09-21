"""THE schema — single source of truth for the generic pipeline.

This one file drives everything downstream, and nothing else needs to
change when it changes:

    field added / removed / renamed here
        -> LLM prompt   (built from model_json_schema)   [pme/extractor.py]
        -> validation   (Pydantic model_validate)        [pme/extractor.py]
        -> storage      (payload = the instance itself)  [pme/store.py]

Extractor, store, and pipeline runner are generic and stay untouched.
Nested fields (e.g. ``rows``) are first-class: the LLM emits them,
Pydantic validates them, and the store carries them — no mapping code.
"""
from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class ReportTableRow(BaseModel):
    """One printed row of a report measurement table."""

    model_config = ConfigDict(extra="ignore")

    section: str | None = None
    row_label: str | None = None
    value_right: str | None = None
    value_left: str | None = None


class MedicalExaminationRecord(BaseModel):
    """One candidate's medical examination report, extracted from text.

    Edit this class to change what the pipeline extracts and stores —
    no other file in the pipeline changes.
    """

    model_config = ConfigDict(extra="ignore")

    document_id: str

    # Page 1 — identity
    candidate_name: str | None = None
    father_name: str | None = None
    roll_number: str | None = None
    date_of_birth: date | None = None
    examination_date: date | None = None
    medical_class: str | None = None

    # Page 2 — lab values
    urine: str | None = None
    sugar: str | None = None
    alb: str | None = None

    # Page 3 — vitals / vision
    blood_pressure: str | None = None
    distance_vision_right: str | None = None
    distance_vision_left: str | None = None

    fitness_classification: str | None = None
    declaration_date: date | None = None
    remarks: str | None = None

    # Printed measurement table (nested, validated as ReportTableRow)
    rows: list[ReportTableRow] = Field(default_factory=list)

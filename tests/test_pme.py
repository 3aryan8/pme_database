"""Tests for normalized PME extraction schema loading.

Phase: database schema validation. Input: tracked JSON schema fixture. Output: validated candidate and declaration fields. Command: ``uv run pytest tests/test_pme.py -q``.
"""
from pathlib import Path
from src.database.schemas import PMEExtraction

# Keep this schema fixture tracked and independent of ignored pipeline output.
SAMPLE = Path(__file__).parent / "fixtures" / "sample_record.json"

def test_sample_json():
    d=PMEExtraction.from_file(SAMPLE)
    assert d.page1.general_details.candidate_name == "AJAY SINGH"
    assert d.page1.narrative_details.roll_number == "116244151979348"
    assert d.page2.pme_case.urine == "SUGAR"
    assert len(d.page4.part_one) == 5
    assert len(d.page4.part_two) == 6

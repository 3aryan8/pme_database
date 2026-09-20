from pathlib import Path
from pme.schemas import PMEExtraction

# Sample extraction lives in the pipeline project (one level up).
SAMPLE = (
    Path(__file__).resolve().parents[2]
    / "data" / "processed" / "extractions"
    / "231c1d5189f1bcd717ab880cca4d0682799911a892bb1974b230982c00721ce7"
    / "record.json"
)

def test_sample_json():
    d=PMEExtraction.from_file(SAMPLE)
    assert d.page1.general_details.candidate_name == "AJAY SINGH"
    assert d.page1.narrative_details.roll_number == "116244151979348"
    assert d.page2.pme_case.urine == "SUGAR"
    assert len(d.page4.part_one) == 5
    assert len(d.page4.part_two) == 6

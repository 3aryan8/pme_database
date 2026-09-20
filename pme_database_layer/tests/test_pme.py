from pathlib import Path
from pme.schemas import PMEExtraction

def test_sample_json():
    d=PMEExtraction.from_file(Path("data/processed/extractions/record.json"))
    assert d.page1.general_details.candidate_name == "AJAY SINGH"
    assert d.page1.narrative_details.roll_number == "116244151979348"
    assert d.page2.pme_case.urine == "N"
    assert len(d.page4.part_one) == 5
    assert len(d.page4.part_two) == 6

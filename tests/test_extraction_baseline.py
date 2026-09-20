"""No GPU needed — these test the pure parts: prompt, parser, normalizer,
scorer taxonomy (schema v2: hierarchical, page-structured), and the runner's
document/per-page output layout (fake extractor, no model)."""
import json
import sys

import pandas as pd

from src.extraction.vlm_extractor import (build_extraction_prompt,
                                           parse_extraction_output)
from src.utils.config_loader import config
from src.ground_truth.normalize import normalize_value
from src.ground_truth.scorer import score_document


def test_prompt_is_schema_driven_and_page_filtered():
    full = build_extraction_prompt(config.schema)
    for token in ("candidate_name", "pme_case", "sugar", "alb",
                  "accuracy_of_vision", "fit_in_class", "part_one",
                  "part_two", "NEVER guess", "null"):
        assert token in full, f"missing {token} in full prompt"

    p1 = build_extraction_prompt(config.schema, page=1)
    assert "candidate_name" in p1 and "roll_number" in p1
    assert "accuracy_of_vision" not in p1 and "part_one" not in p1

    p2 = build_extraction_prompt(config.schema, page=2)
    assert "pme_case" in p2 and "right_side_table" in p2
    assert "candidate_name" not in p2 and "fit_in_class" not in p2

    p3 = build_extraction_prompt(config.schema, page=3)
    assert "fit_in_class" in p3 and "accuracy_of_vision" in p3
    assert "candidate_name" not in p3 and "part_one" not in p3

    p4 = build_extraction_prompt(config.schema, page=4)
    assert "part_one" in p4 and "part_two" in p4 and "question_no" in p4
    assert "pme_case" not in p4 and "fit_in_class" not in p4


def test_prompt_document_mode():
    doc = build_extraction_prompt(config.schema, n_pages=4)
    # all four sections in ONE prompt (single pass over the whole document)
    for token in ("page_1_basic_info", "candidate_name", "pme_case",
                  "fit_in_class", "accuracy_of_vision", "part_one",
                  "part_two", "NEVER guess", "COMPLETE", "IN ORDER"):
        assert token in doc, f"missing {token!r} in document prompt"
    assert "reading ONE page" not in doc
    assert "Transcribe values EXACTLY as printed" in doc
    # legacy single-page and page-filtered prompts unchanged
    assert "reading ONE page" in build_extraction_prompt(config.schema)
    assert "reading ONE page" in build_extraction_prompt(config.schema, page=1)


def test_null_literal_strings_become_null():
    raw = ('{"page_1_basic_info": {'
           '"general_details": {"candidate_name": "  None  ", '
           '"father_name": "N/A", "date_of_birth": "09-07-2003"},'
           '"narrative_details": {"roll_number": "null"}}}')
    fields, ok = parse_extraction_output(raw, config.schema)
    assert ok
    gd = fields["page_1_basic_info"]["general_details"]
    nd = fields["page_1_basic_info"]["narrative_details"]
    assert nd["roll_number"] is None          # "null" -> null
    assert gd["candidate_name"] is None       # "None" -> null
    assert gd["father_name"] is None          # "N/A" -> null
    assert gd["date_of_birth"] == "09-07-2003"  # real value untouched


def test_parser_tolerant_and_schema_shaped():
    raw = (
        '```json\n'
        '{"page_1_basic_info": {'
        '  "general_details": {"candidate_name": 123, '
        '     "father_name": "  X  ", "bogus": "x"},'
        '  "narrative_details": {"roll_number": " 242243220965001 "}}},'
        ' "junk_section": {"a": 1}}\n```')
    fields, ok = parse_extraction_output(raw, config.schema)
    assert ok
    p1 = fields["page_1_basic_info"]
    assert p1["general_details"]["candidate_name"] == "123"
    assert p1["general_details"]["father_name"] == "X"
    assert "bogus" not in p1["general_details"]      # filtered to schema shape
    assert p1["narrative_details"]["roll_number"] == "242243220965001"
    assert "junk_section" not in fields
    # untouched schema sections keep their null shape
    assert fields["page_3_fitness_classification"]["fit_in_class"] is None

    fields, ok = parse_extraction_output("the model rambled", config.schema)
    assert not ok
    assert fields["page_1_basic_info"]["general_details"]["candidate_name"] is None


def test_normalize():
    assert normalize_value("05/09/2026", "date") == "2026-09-05"
    assert normalize_value("120 mmHg", "integer") == "120"
    assert normalize_value(" ab 1234 ", "string", "roll_number") == "AB 1234"
    assert normalize_value("No", "boolean") == "false"
    assert normalize_value("yes", "boolean") == "true"
    assert normalize_value(None, "string") is None
    assert normalize_value("?", "string") == "?"


def test_scorer_taxonomy_nested():
    schema = config.schema
    doc = "d" * 64
    # typed identity leaf: case-normalized match
    leaf = "page_1_basic_info.narrative_details.roll_number"
    gt = {"page_1_basic_info": {"narrative_details": {"roll_number": "ab1234"}}}
    ex = {"page_1_basic_info": {"narrative_details": {"roll_number": "AB1234"}}}
    rows = score_document(doc, gt, ex, schema)
    match = [r for r in rows if r["field"] == leaf]
    assert match and match[0]["taxon"] == "correct"

    # hallucinated: GT null, model gave a value
    gt = {"page_1_basic_info": {"narrative_details": {"roll_number": None}}}
    ex = {"page_1_basic_info": {"narrative_details": {"roll_number": "AB1234"}}}
    rows = score_document(doc, gt, ex, schema)
    assert [r for r in rows if r["field"] == leaf][0]["taxon"] == "hallucinated"

    # missed: GT value, model null
    gt = {"page_1_basic_info": {"narrative_details": {"roll_number": "AB1234"}}}
    ex = {"page_1_basic_info": {"narrative_details": {"roll_number": None}}}
    rows = score_document(doc, gt, ex, schema)
    assert [r for r in rows if r["field"] == leaf][0]["taxon"] == "missed"

    # correctly_nulled: both null
    gt = {"page_1_basic_info": {"narrative_details": {"roll_number": None}}}
    ex = {"page_1_basic_info": {"narrative_details": {"roll_number": None}}}
    rows = score_document(doc, gt, ex, schema)
    assert [r for r in rows if r["field"] == leaf][0]["taxon"] == "correctly_nulled"


def _first_doc():
    df = pd.read_parquet(config.get_path("manifest_file"))
    doc = str(df["document_id"].iloc[0])
    return doc, df


def _redirect_outputs(monkeypatch, tmp_path):
    real_get_path = config.get_path
    monkeypatch.setattr(
        config, "get_path",
        lambda key: (tmp_path / "processed" if key == "processed_dir"
                     else real_get_path(key)))


def _run_runner(monkeypatch, argv):
    from src.extraction import run_extraction as rx
    old_argv = sys.argv
    sys.argv = argv
    try:
        return rx.main()
    finally:
        sys.argv = old_argv


def test_runner_document_mode_one_json_per_person(tmp_path, monkeypatch):
    from src.extraction import run_extraction as rx
    from src.models.fields import null_shape

    doc, df = _first_doc()
    n_pages = int((df["document_id"] == doc).sum())
    assert n_pages == 4

    class FakeExtractor:
        model_id = "fake/vlm"

        def __init__(self):
            self.schema = config.schema

        def extract_document(self, image_paths, long_edge):
            # pages must arrive in order, page 0 first
            assert [p.name for p in image_paths] == \
                [f"page_{i:04d}.png" for i in range(len(image_paths))]
            shape = null_shape(self.schema.fields)
            shape["page_1_basic_info"]["narrative_details"][
                "roll_number"] = "111222333"
            shape["page_3_fitness_classification"]["fit_in_class"] = "BEE ONE"
            return shape, True

    monkeypatch.setattr(rx, "VlmSchemaExtractor", FakeExtractor)
    _redirect_outputs(monkeypatch, tmp_path)
    rc = _run_runner(monkeypatch,
                     ["run_extraction", "--doc", doc, "--mode", "document",
                      "--overwrite"])
    assert rc == 0

    doc_dir = tmp_path / "processed" / "extractions" / doc
    record = json.loads((doc_dir / "record.json").read_text())
    assert record["document_id"] == doc
    assert (record["fields"]["page_1_basic_info"]["narrative_details"]
            ["roll_number"]) == "111222333"
    assert (record["fields"]["page_3_fitness_classification"]
            ["fit_in_class"]) == "BEE ONE"
    # provenance credited to the page each section belongs to
    assert (record["provenance"]
            ["page_1_basic_info.narrative_details.roll_number"]
            ["page_index"]) == 0
    assert (record["provenance"]
            ["page_3_fitness_classification.fit_in_class"]
            ["page_index"]) == 2
    assert record["pages_covered"] == [0, 1, 2, 3]
    assert record["conflicts"] == []
    # acceptance: ONE json per person — no per-page sidecars in this mode
    assert not list(doc_dir.glob("page_*.json"))
    side = json.loads((doc_dir / "document.json").read_text())
    assert side["mode"] == "document"
    assert side["parse_ok"] is True
    assert side["person_index"] == int(df["person_index"].iloc[0])
    assert side["model_input"] == [
        f"data/interim/vlm_res/{doc}/page_{i:04d}.png" for i in range(4)]


def test_runner_per_page_mode_still_merges(tmp_path, monkeypatch):
    from src.extraction import run_extraction as rx
    from src.models.fields import null_shape

    doc, _ = _first_doc()

    class FakeExtractor:
        model_id = "fake/vlm"

        def __init__(self):
            self.schema = config.schema

        def extract_page(self, image_path, long_edge, page=None):
            shape = null_shape(self.schema.fields)
            if page == 1:
                shape["page_1_basic_info"]["narrative_details"][
                    "roll_number"] = "222333444"
            if page == 3:
                shape["page_3_fitness_classification"][
                    "fit_in_class"] = "BEE ONE"
            return shape, True

    monkeypatch.setattr(rx, "VlmSchemaExtractor", FakeExtractor)
    _redirect_outputs(monkeypatch, tmp_path)
    rc = _run_runner(monkeypatch,
                     ["run_extraction", "--doc", doc, "--mode", "per_page",
                      "--overwrite"])
    assert rc == 0

    doc_dir = tmp_path / "processed" / "extractions" / doc
    record = json.loads((doc_dir / "record.json").read_text())
    assert (record["fields"]["page_1_basic_info"]["narrative_details"]
            ["roll_number"]) == "222333444"     # merged from page 1
    # per-page sidecars exist in this A/B mode
    assert sorted(p.name for p in doc_dir.glob("page_*.json")) == \
        ["page_0000.json", "page_0001.json", "page_0002.json",
         "page_0003.json"]
    assert record["pages_covered"] == [0, 1, 2, 3]


def test_scorer_boolean_rows_positional():
    schema = config.schema
    doc = "d" * 64
    leaf = "page_4_declarations.part_one[0].answer"
    gt = {"page_4_declarations": {"part_one": [
        {"question_no": "1a", "answer": "No"}]}}
    ex = {"page_4_declarations": {"part_one": [
        {"question_no": "1a", "answer": "false"}]}}
    rows = score_document(doc, gt, ex, schema)
    assert [r for r in rows if r["field"] == leaf][0]["taxon"] == "correct"
    # row count mismatch: GT has 2 rows, model 1 -> row[1] is missed
    gt = {"page_4_declarations": {"part_one": [
        {"question_no": "1a", "answer": "No"},
        {"question_no": "1b", "answer": "No"}]}}
    rows = score_document(doc, gt, ex, schema)
    assert [r for r in rows if r["field"] ==
            "page_4_declarations.part_one[1].answer"][0]["taxon"] == "missed"

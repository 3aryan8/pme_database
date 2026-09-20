"""Smoke tests: config contracts. Phase 3 will add the ID-stability test here
(regenerate manifest twice -> byte-identical document_ids)."""
from src.utils.config_loader import config


def test_pipeline_config_valid():
    assert config.pipeline.rendering.render_dpi == 300
    assert config.pipeline.quality_checks["low_source_dpi_threshold"] == 150


def test_paths_resolve_absolute():
    p = config.get_path("manifest_file")
    assert p.is_absolute()
    assert p.name == "manifest.parquet"


def test_schema_requires_key_fields():
    from src.models.fields import leaf_specs
    specs = leaf_specs(config.schema)
    leaves = set(specs)
    assert "page_1_basic_info.general_details.candidate_name" in leaves
    assert "page_1_basic_info.general_details.date_of_birth" in leaves
    assert "page_1_basic_info.narrative_details.roll_number" in leaves
    assert "page_2_medical_metrics.pme_case.sugar" in leaves
    assert "page_3_fitness_classification.fit_in_class" in leaves
    assert ("page_3_fitness_classification.accuracy_of_vision"
            ".right_eye.distance_uncorrected") in leaves
    assert "page_4_declarations.part_one.question_no" in leaves
    assert specs["page_4_declarations.part_one.answer"].data_type == "boolean"


def test_regions_defined():
    assert "signature" in config.regions.discard_classes
    assert "data_table_handwritten" in config.regions.extraction_classes

def test_person_document_id_deterministic():
    from src.assembly.id_generator import person_document_id
    sha = "a" * 64
    a = person_document_id(sha, 0)
    assert a == person_document_id(sha, 0)
    assert len(a) == 64
    assert person_document_id(sha, 1) != a          # different person
    assert person_document_id("b" * 64, 0) != a     # different source file
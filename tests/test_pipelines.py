"""Tests for central cross-module pipeline composition.

Phase: pipeline orchestration. Input: runner flags. Output: ordered module commands. Command: ``uv run pytest tests/test_pipelines.py -q``.
"""

from pipelines.run_all import stages


def test_default_pipeline_stitches_cpu_gpu_and_database_modules():
    commands = stages(skip_gpu=False)

    assert [name.split(":", 1)[0] for name, _ in commands] == [
        "pdf_merge",
        "assembly",
        "preprocessing",
        "detection",
        "extraction",
        "database",
    ]
    assert commands[0][1][-1] == "src.pdf_merge.run_pdf_merge"
    assert commands[-1][1][-1] == "data/processed/extractions"


def test_ground_truth_is_opt_in():
    commands = stages(skip_gpu=True, with_ground_truth=True)

    assert commands[-1][0].startswith("ground_truth:")
    assert commands[-1][1][-1] == "src.ground_truth.run_ground_truth"
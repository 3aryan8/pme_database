"""Run the complete cross-module PME pipeline.

Phase: pipeline orchestration.
Input: configured PDFs, module configuration, and existing extraction output.
Output: merged PDFs, assembled/preprocessed manifests, detections, extractions,
validation results, and imported database records.
Commands:
  ``uv run python -m pipelines.run_all`` runs all stages.
  ``uv run python -m pipelines.run_all --skip-gpu`` skips detection/extraction.
    ``uv run python -m pipelines.run_all --dry-run`` prints the stage plan.
    ``uv run python -m pipelines.run_all --with-ground-truth`` adds scoring.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTRACTIONS_DIR = "data/processed/extractions"


def stages(
    skip_gpu: bool,
    with_ground_truth: bool = False,
) -> list[tuple[str, list[str]]]:
    """Return the ordered module runner commands for the pipeline."""
    commands = [
        (
            "pdf_merge: merge configured PDFs",
            ["uv", "run", "python", "-m", "src.pdf_merge.run_pdf_merge"],
        ),
        (
            "assembly: split, render, and build manifest",
            ["uv", "run", "python", "-m", "src.assembly.run_assembly"],
        ),
        (
            "preprocessing: clean and resize pages",
            ["uv", "run", "python", "-m", "src.preprocessing.run_preprocessing"],
        ),
    ]
    if not skip_gpu:
        commands.extend(
            [
                (
                    "detection: VLM region detection",
                    ["uv", "run", "python", "-m", "src.detection.run_detection"],
                ),
                (
                    "extraction: VLM field extraction",
                    ["uv", "run", "python", "-m", "src.extraction.run_extraction"],
                ),
            ]
        )
    commands.append(
        (
            "database: validate and import extraction records",
            [
                "uv",
                "run",
                "python",
                "-m",
                "src.database.run_database",
                "--directory",
                EXTRACTIONS_DIR,
            ],
        )
    )
    if with_ground_truth:
        commands.append(
            (
                "ground_truth: score extraction records",
                ["uv", "run", "python", "-m", "src.ground_truth.run_ground_truth"],
            )
        )
    return commands


def main() -> int:
    """Execute each module runner fail-fast, or print the plan."""
    parser = argparse.ArgumentParser(
        description="Run the complete PME module pipeline"
    )
    parser.add_argument(
        "--skip-gpu",
        action="store_true",
        help="skip detection and extraction stages",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the stage plan without running it",
    )
    parser.add_argument(
        "--with-ground-truth",
        action="store_true",
        help="run Gate 1 scoring after database import",
    )
    args = parser.parse_args()

    plan = stages(args.skip_gpu, args.with_ground_truth)
    for index, (name, command) in enumerate(plan, start=1):
        print(f"[{index}/{len(plan)}] {name}")
        print(f"  $ {' '.join(command)}")
        if args.dry_run:
            continue
        result = subprocess.run(command, cwd=ROOT)
        if result.returncode:
            print(
                f"Pipeline stopped at {name} (exit {result.returncode}).",
                file=sys.stderr,
            )
            return result.returncode

    if not args.dry_run:
        print("Pipeline complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

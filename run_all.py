"""Central orchestrator: runs the ENTIRE pipeline, start to finish.

    uv run python run_all.py               # full run (GPU needed for stages 2-3)
    uv run python run_all.py --skip-gpu    # CPU stages only (reuse existing extractions)
    uv run python run_all.py --dry-run     # print the plan, run nothing

Stages (each in its own `uv run` subprocess, fail-fast on first error):

  1. core      merge PDFs -> assembly -> preprocessing   (this project)
  2. detect    VLM region detection                      (GPU)
  3. extract   VLM field extraction                      (GPU)
  4. validate  validate extraction JSONs                 (pme_database_layer)
  5. import    import extractions + report images -> DB (pme_database_layer)

After a successful run, retrieve a candidate's four report images with
(pme_database_layer):

    from pme.database import get_session, init_db
    from pme.repository import get_candidate_report_images
    init_db(); session = get_session()
    for img in get_candidate_report_images(session, candidate_id):
        print(img.page_number, img.image_path)
"""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_LAYER = ROOT / "pme_database_layer"
DB_EXTRACTIONS_DIR = "../data/processed/extractions"  # relative to DB_LAYER


def stages(skip_gpu: bool) -> list[tuple[str, Path, list[str]]]:
    """Ordered (name, cwd, command) list. Stage 1 already includes the
    merge -> assembly -> preprocessing flow of src/run_pipeline.py."""
    out: list[tuple[str, Path, list[str]]] = [
        ("core: merge -> assembly -> preprocess", ROOT,
         ["uv", "run", "python", "-m", "src.run_pipeline", "--phase", "all"]),
    ]
    if not skip_gpu:
        out += [
            ("detect: VLM region detection (GPU)", ROOT,
             ["uv", "run", "python", "-m", "src.detection.run_detection"]),
            ("extract: VLM field extraction (GPU)", ROOT,
             ["uv", "run", "python", "-m", "src.extraction.run_extraction"]),
        ]
    out += [
        ("validate: check extraction JSONs", DB_LAYER,
         ["uv", "run", "python", "scripts/validate_extractions.py",
          "--directory", DB_EXTRACTIONS_DIR]),
        ("import: extractions + report images -> database", DB_LAYER,
         ["uv", "run", "python", "scripts/import_extractions.py",
          "--directory", DB_EXTRACTIONS_DIR]),
    ]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Run the entire PME pipeline start to finish.")
    ap.add_argument("--skip-gpu", action="store_true",
                    help="skip the GPU stages (detection/extraction); "
                         "validate+import still run on existing extractions")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the stage plan without running anything")
    args = ap.parse_args()

    plan = stages(args.skip_gpu)
    for i, (name, cwd, cmd) in enumerate(plan, 1):
        where = cwd.relative_to(ROOT) if cwd != ROOT else "."
        line = f"[{i}/{len(plan)}] {name}\n        $ {' '.join(cmd)}   (in {where}/)"
        if args.dry_run:
            print(line)
            continue
        print(line, flush=True)
        result = subprocess.run(cmd, cwd=cwd)
        if result.returncode != 0:
            print(f"\nFAILED at stage: {name} (exit {result.returncode}) — stopping.",
                  file=sys.stderr)
            return result.returncode

    print("\nPipeline complete: extractions imported, report images stored.")
    print("Per-candidate reports: "
          "cd pme_database_layer && uv run python scripts/generate_report.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())

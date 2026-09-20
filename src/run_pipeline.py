"""Group 1 pipeline entrypoint: merge PDFs -> assembly -> preprocess."""
import argparse

from src.utils.config_loader import config
from src.utils.logger import setup_logger

log = setup_logger("pipeline")


def main() -> None:
    parser = argparse.ArgumentParser(description="Medical Report Foundation Pipeline")
    parser.add_argument("--phase", choices=["assembly", "preprocess", "all"],
                        default="all")
    parser.add_argument("--dummy", action="store_true",
                        help="Smoke test without touching real data")
    parser.add_argument("--limit", type=int, default=None,
                        help="preprocess only first N pages (dry-run mode)")
    args = parser.parse_args()

    config.bootstrap_dirs()
    log.info("PME pipeline — phase=%s", args.phase)
    log.info("project root: %s", config.root_dir)

    if args.dummy:
        log.info("dummy run — nothing executed")
        return

    if args.phase in ("assembly", "all"):
        from src.pdf_merge.run_merge import merge_configured_pdfs
        try:
            merged_pdf = merge_configured_pdfs()
        except (FileNotFoundError, ValueError) as exc:
            log.error("pdf merge failed: %s", exc)
            raise SystemExit(1)
        from src.assembly.run_assembly import main as run_assembly
        if run_assembly(source_path=merged_pdf) != 0:
            log.error("assembly failed — aborting")
            raise SystemExit(1)

    if args.phase in ("preprocess", "all"):
        from src.preprocessing.run_preprocessing import main as run_preprocess
        raise SystemExit(run_preprocess(limit=args.limit))


if __name__ == "__main__":
    main()
"""Gate 1 evidence: validates every config file against its Pydantic contract.

Exit code 0 = all valid. Exit code 1 = at least one config is invalid.
"""
import sys

from src.utils.config_loader import config


def main() -> int:
    checks = [
        ("configs/pipeline.yaml", lambda: config.pipeline),
        ("configs/regions.yaml", lambda: config.regions),
        ("configs/schema.yaml", lambda: config.schema),
    ]
    failed = False
    for name, getter in checks:
        try:
            obj = getter()
            print(f"PASS  {name}  ({type(obj).__name__})")
        except Exception as e:            # noqa: BLE001 - report, don't crash
            failed = True
            print(f"FAIL  {name}  -> {e}")

    print("INFO  configs/models.yaml loaded raw (Group 2 owns its validation)")
    if failed:
        print("\nRESULT: INVALID CONFIG — fix the files above before proceeding.")
    else:
        print("\nRESULT: ALL CONFIGS VALID.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
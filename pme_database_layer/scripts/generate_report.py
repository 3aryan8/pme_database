from __future__ import annotations

import sys
from pathlib import Path

# Allow execution as:
# python scripts/generate_report.py
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pme.database import get_session
from pme.report_generator import generate_report
from pme.repository import get_examination_by_roll_number


ROLL_NUMBER = "116244151979348"


def main() -> None:
    with get_session() as session:

        examination = get_examination_by_roll_number(
            session,
            ROLL_NUMBER,
        )

        if examination is None:
            print(f"[ERROR] No examination found for roll: {ROLL_NUMBER}")
            raise SystemExit(1)

        html_path, json_path = generate_report(
            examination,
            output_dir=ROOT / "data" / "reports",
        )

        print("[OK] Report generated")
        print(f"HTML : {html_path}")
        print(f"JSON : {json_path}")


if __name__ == "__main__":
    main()
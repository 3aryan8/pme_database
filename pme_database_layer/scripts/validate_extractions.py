from pathlib import Path
import argparse
from pme.schemas import PMEExtraction
p=argparse.ArgumentParser(); p.add_argument("--directory", type=Path, default=Path("data/processed/extractions")); a=p.parse_args()
files=sorted(a.directory.rglob("*.json")); bad=0
for f in files:
    try:
        d=PMEExtraction.from_file(f); print(f"[OK] {f.name} | {d.document_id} | roll={d.page1.narrative_details.roll_number}")
    except Exception as e: bad+=1; print(f"[ERROR] {f.name}: {e}")
print(f"Valid: {len(files)-bad}\nInvalid: {bad}")
raise SystemExit(1 if bad else 0)

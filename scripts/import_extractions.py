from pathlib import Path
import argparse
from src.database.database import init_db, get_session
from src.database.importer import import_directory
p=argparse.ArgumentParser(); p.add_argument("--directory", type=Path, default=Path("data/processed/extractions")); a=p.parse_args()
if not a.directory.exists(): print(f"Directory does not exist: {a.directory}"); raise SystemExit(1)
init_db(); s=get_session()
try: ok,bad=import_directory(s,a.directory)
finally: s.close()
print(f"\nProcessed: {ok}\nFailed: {bad}")
raise SystemExit(1 if bad else 0)

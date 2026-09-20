# PME Database Layer

Purpose: Qwen extraction JSON -> Pydantic validation -> SQLAlchemy relational database -> report generation.

## Install
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Copy `.env.example` to `.env`. The code currently reads environment variables directly, so exporting them in the shell is sufficient; for automatic `.env` loading add `python-dotenv` later if desired.

## Validate
```bash
python scripts/validate_extractions.py
```

## Import
```bash
python scripts/import_extractions.py
```

## Database
Default: SQLite `data/pme.db`.
For MySQL set `DATABASE_URL=mysql+pymysql://USER:PASSWORD@HOST:3306/pme`.

## Tables
`candidates`, `medical_examinations`, `pme_cases`, `pme_vision_rows`, `vision_examinations`, `physical_examinations`, `fitness_classifications`, `declarations`, `doctors`, `extraction_runs`.

`extraction_runs.document_id` is unique, so importing the same JSON twice does not create a second examination.

The raw validated extraction is retained in `extraction_runs.raw_json` for provenance/auditability.

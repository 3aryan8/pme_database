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
`candidates`, `medical_examinations`, `pme_cases`, `pme_vision_rows`, `vision_examinations`, `physical_examinations`, `fitness_classifications`, `declarations`, `doctors`, `extraction_runs`, `report_images`.

`extraction_runs.document_id` is unique, so importing the same JSON twice does not create a second examination.

The raw validated extraction is retained in `extraction_runs.raw_json` for provenance/auditability.

## Report Images (verification)

Every imported examination stores its four rendered report pages in `report_images`:

| column | meaning |
|---|---|
| `examination_id` | the report record this belongs to (candidate → latest examination) |
| `page_number` | 1-based report page (1–4) |
| `image_path` | where the PNG lives (project-relative when under the pipeline project) |
| `document_id` | provenance — which extraction document the render came from |

Unique on `(examination_id, page_number)`. Images are located from the pipeline's
render output (`data/interim/high_res/<document_id>/page_000X.png`, override with
`REPORT_IMAGES_DIR`) and inserted in the **same transaction** as the examination —
a missing page rolls back the whole import, so no orphan rows or partial records.

Retrieve the four images for a candidate:

```python
from pme.database import get_session, init_db
from pme.repository import get_candidate_report_images

init_db()
session = get_session()
for image in get_candidate_report_images(session, candidate_id):
    print(image.page_number, image.image_path)   # 1..4, in order
```

## Generic LLM Extraction Pipeline (zero-touch)

A modular, decoupled text → LLM → schema → DB pipeline where **the schema
class is the single source of truth**. Add, remove, or rename a field in the
schema class and everything downstream adapts automatically — the extractor,
the store, and the pipeline runner are generic and never change:

```
text file ──▶ LLMExtractor.extract(text, Schema) ──▶ validated Schema instance ──▶ store.save() ──▶ extraction_records
   ▲                        │                                                        │
   │                        └─ prompt built from Schema.model_json_schema()          └─ get() / all_rows() read it back as Schema
   └────────────────────────────────────────────────────────────────────────────────────┘
```

| file | role |
|---|---|
| `src/pme/extraction_schema.py` | **the schema** — `MedicalExaminationRecord` (+ `ReportTableRow`). Edit fields here only. |
| `src/pme/extractor.py` | generic LLM extractor: prompt from JSON schema, tolerant JSON recovery, `model_validate` at the trust boundary. Client-agnostic (`complete(prompt) -> str`), default: OpenAI-compatible server via stdlib `urllib`. |
| `src/pme/store.py` | generic store: any validated Pydantic instance → one row in `extraction_records(id, schema_name, payload JSON, created_at)`; `get()`/`all_rows()` validate the payload back into the class. |
| `scripts/run_pipeline.py` | runner: `text → extract → save`, with `--dry-run` (print the prompt) and `--schema` (any Pydantic class). |

Usage:

```bash
uv run python scripts/run_pipeline.py --text samples/sample_report.txt   # one report
uv run python scripts/run_pipeline.py --text-dir /path/to/reports        # a batch of .txt
uv run python scripts/run_pipeline.py --dry-run                          # print the LLM prompt

# retrieve
uv run python -c "from pme.extraction_schema import MedicalExaminationRecord as M; \
                  from pme.store import all_rows; print(all_rows(M))"
```

LLM endpoint (any OpenAI-compatible server — LM Studio, OpenAI, vLLM, Ollama):

| env | default |
|---|---|
| `PME_LLM_BASE_URL` | `http://localhost:1234/v1` |
| `PME_LLM_MODEL` | `qwen/qwen3.8-27b` |
| `PME_LLM_API_KEY` | *(unset)* |
| `PME_LLM_MAX_TOKENS` | `8192` |
| `PME_LLM_TIMEOUT` | `300` |

Notes:

- The generic `extraction_records` table is separate from the normalized
  relational tables (`candidates`, `medical_examinations`, ...) — those stay
  the curated store for the VLM pipeline; this is the schema-driven path.
- `payload` stores the validated instance as JSON, so schema evolution needs
  no table migration and never breaks old rows' reads (they validate against
  the current class or raise clearly).
- Verified live: sample report → Qwen (localhost) → 16/16 fields + 3 nested
  table rows extracted, validated, stored, read back. Zero-touch proven by
  tests and a live run with an extra schema field added to a subclass.
- Tests: `uv run pytest tests/test_generic_pipeline.py -q` (fake LLM client,
  in-memory SQLite — no network, no GPU).

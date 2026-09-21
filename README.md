# Offline Medical Report Digitization & Query System

A local, modular, and reproducible Document-AI pipeline for converting scanned multi-page medical examination reports into structured, queryable, and traceable records.

This system handles complex scanned medical documents containing a mixture of typed text, handwriting, numerical measurements, tables, signatures, stamps/seals, thumbprints, photographs, and overlapping visual regions.

---

## Key Features

* **Strict Local Privacy**: 100% offline. Zero cloud services, remote API calls, or internet dependencies at runtime.
* **Modular Architecture**: AI models, OCR engines, preprocessing algorithms, databases, and storage layers are completely decoupled and independently replaceable.
* **Full Traceability & Provenance**: Every extracted field links directly back to its source PDF, page index, bounding box (`[x1, y1, x2, y2]`), and extraction run metadata.
* **Schema-Driven Extraction**: Medical fields are defined in declarative YAML configurations (`configs/schema.yaml`) rather than hardcoded logic.
* **Human-in-the-Loop Feedback**: Corrections made during review automatically feed back into ground-truth datasets for model evaluation, detector retraining, and fine-tuning.
* **Dual-GPU Optimization**: Configured out-of-the-box for multi-GPU worker parallel inference on hardware setups like 2 × NVIDIA RTX 4500 Ada.

---

## Document Model

The system processes multi-person batch PDFs where every individual candidate report consists of exactly **four pages**:

```text
Person Report Unit (4 Pages)
├── Page 1 — Basic Information, Identification, & Medical Memo
├── Page 2 — Medical Metrics, Lab Results, & Handwritten Remarks
├── Page 3 — Fitness Classification, Vision Measurements, & Clinical Notes
└── Page 4 — Candidate & Examiner Declarations / Consent
```

---

## Pipeline Flow

```text
configs/pdf_sources.yaml          YAML list of PDF filenames
        ↓
PDF merge (src/pdf_merge)         locate + validate + merge in YAML order
        ↓
data/merged/merged_source.pdf     single batched source PDF (separate folder — never re-merged)
        ↓
Assembly (src/assembly)           split per configs/splits.yaml → render N pages/person (per-person page ranges)
        ↓
Preprocessing (src/preprocessing) clean + VLM-sized copies → manifest
        ↓
Detection / Extraction            (VLM stages, separate entrypoints)
        ↓
src/database (validate+import)  validate → SQLite (data/pme.db) → report generation
```

### Run the whole thing, start to finish

```bash
uv run python run_all.py              # all 5 stages (GPU needed for detect/extract)
uv run python run_all.py --skip-gpu   # CPU stages only; validate+import run on existing extractions
uv run python run_all.py --dry-run    # print the plan, run nothing
```

Stages: `core` (merge → assembly → preprocess) → `detect` (GPU) → `extract` (GPU) → `validate` → `import` (extractions + 4 report images into the DB). Fail-fast: stops at the first failing stage.

### CPU-only core pipeline

`uv run python -m src.run_pipeline` (or `--phase assembly|preprocess|all`) — merge → assembly → preprocess without the GPU/DB stages.

## PDF Merging (first pipeline step)

Before assembly, the pipeline merges the configured raw PDFs into one batched source PDF.

1. **Where the config lives:** `configs/pdf_sources.yaml`
   ```yaml
   pdfs:
     - report_001.pdf
     - report_002.pdf
   ```
   Order matters — the merged PDF's page order is exactly this list's order. All listed PDFs must exist or the pipeline fails with a clear error naming the missing files.
2. **Where input PDFs go:** `data/raw/` (filenames in the YAML resolve against this directory).
3. **Where the merged PDF lands:** `data/merged/merged_source.pdf` — a **separate folder** from the raw inputs, so the merged file can never be picked up as an input on a later run (no recursive re-merging). Overwritten on re-run; input PDFs are never modified or deleted. A **single** configured PDF is used directly — no re-encoding, so document IDs stay stable (document IDs derive from the source file SHA).
4. **How the pipeline uses it:** `src/run_pipeline.py` calls `merge_configured_pdfs()` and passes the result to assembly, which splits it into per-person reports. The person boundaries in `configs/splits.yaml` must describe the *merged* PDF's page layout (assembly refuses to run on unverified boundaries).
5. **Standalone:** `uv run python -m src.pdf_merge.run_merge`

## Report Images (verification)

Every imported report stores its **rendered page images** in the database so extracted values can be visually checked against the original scan.

- **N pages per person is set by `configs/splits.yaml`** (the person's page range), not a fixed 4 — a person with 3 or 6 report pages works the same way. The import cross-checks the rendered count against the record's declared coverage (`pages_covered`) and fails atomically on mismatch.
- Images live in the pipeline's standard render output: `data/interim/high_res/<document_id>/page_0000.png .. page_NNNN.png` (assembly output). They are **not** copied — the database stores a path reference (project-relative when possible).
- Stored per examination (the report record) in the `report_images` table: `examination_id`, `page_number` (1-based, 1–N), `image_path`, `document_id` (provenance). Unique on `(examination_id, page_number)` — exactly one image per page per report.
- Inserted in the **same transaction** as the candidate/examination: a missing page rolls back the whole import, so no orphan image rows and no partial records are ever left behind.
- **Retrieving the report images for a candidate** (from the project root):
  ```python
  from src.database.database import get_session, init_db
  from src.database.repository import get_candidate_report_images

  init_db()
  session = get_session()
  for image in get_candidate_report_images(session, candidate_id):
      print(image.page_number, image.image_path)   # 1..N, in order
  ```
  Or by examination: `get_report_images(session, examination_id)`.

## Generic LLM Extraction Pipeline (zero-touch)

A schema-driven, decoupled text → LLM → schema → DB path in `src/database`:
the Pydantic schema class is the **single source of truth** — add/remove/rename
fields there and the LLM prompt, validation, storage, and retrieval all adapt
without touching extractor, store, or pipeline code (generic over *any*
Pydantic class).

| file | role |
|---|---|
| `src/database/extraction_schema.py` | **the schema** — `MedicalExaminationRecord` (+ `ReportTableRow`). Edit fields here only. |
| `src/database/extractor.py` | generic LLM extractor: prompt from JSON schema, tolerant JSON recovery, `model_validate` at the trust boundary. Client-agnostic (`complete(prompt) -> str`), default: OpenAI-compatible server via stdlib `urllib`. |
| `src/database/store.py` | generic store: any validated Pydantic instance → one row in `extraction_records(id, schema_name, payload JSON, created_at)`; `get()`/`all_rows()` validate the payload back into the class. |
| `scripts/run_pipeline.py` | runner: `text → extract → save`, with `--dry-run` (print the prompt) and `--schema` (any Pydantic class). |

```bash
uv run python scripts/run_pipeline.py --text samples/sample_report.txt   # text → LLM → validated schema → DB
uv run python scripts/run_pipeline.py --dry-run                          # print the generated LLM prompt

# retrieve
uv run python -c "from src.database.extraction_schema import MedicalExaminationRecord as M; \
                  from src.database.store import all_rows; print(all_rows(M))"
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
- Tests: `uv run pytest tests/test_generic_pipeline.py -q` (fake LLM client,
  in-memory SQLite — no network, no GPU).
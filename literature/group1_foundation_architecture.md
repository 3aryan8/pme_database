# Sub-Project Report: Group 1 – Foundation & Preprocessing Pipeline
**Version:** 1.1
**Master Pipeline Phases Covered:** 1, 2, 3, 4
**Estimated Duration:** 2–3 Weeks (Realistic)
**Integration Gate:** Gate 1 (Foundation Verified)

---

## Changelog from v1.0

| # | Issue | Fix |
|---|---|---|
| 1 | `document_id = hash(file_bytes + mtime)` violated this doc's own ID-immutability contract — mtime can change on copy/backup/re-sync even when file content is identical, silently orphaning Group 2's prior extraction work. | `document_id` is now content-hash-only. `mtime` is retained as a separate, non-identity metadata column. |
| 2 | Multi-person split detection was speced as a regex-on-`employee_id` heuristic, but that requires extracted text, which doesn't exist until Phase 5–7. The module had a hidden dependency on downstream work, and skipped the roadmap's own instruction to manually inspect the (currently small) PDF set first. | Manual inspection is now the mandatory first step of WP-3. Automated split detection is built only if that inspection finds a real case; otherwise it's explicitly deferred to Phase 7+, where extracted text actually exists. |
| 3 | "Read the embedded XObject resolution" isn't a defined operation — most scanned PDFs don't store DPI as metadata. | Effective DPI is now specified as a computed value: pixels-per-inch of the dominant embedded raster (`max(px) / displayed_inches`, images covering ≥50% of the page area), and it drives **adaptive rendering** — each page renders at `min(effective_dpi, render_dpi cap)`, so scans are never upscaled and vector pages always render at the cap. |
| 4 | Contract tests used PNG file size (`>500KB` / `<1MB`) as a proxy for resolution — sparse handwritten pages can compress well below threshold, noisy pages can exceed it. Size is not resolution. | Contract tests now open each image and assert actual pixel dimensions against the expected DPI / long-edge target, with tolerance. |
| 5 | No mention of access control on `data/raw/` or `data/interim/high_res/`, despite full medical scans (names, IDs, sometimes DOB) landing there in Phase 3–4 — well before Phase 10's encryption-at-rest. | Added an interim filesystem-permissions requirement in Phase 1 and the interface contract, explicitly framed as *not* a substitute for Phase 10. |
| 6 | "Overwrite in place, or save to a `cleaned/` subfolder" was left ambiguous, undermining the roadmap's own debugging guidance ("suspect this stage first" when downstream accuracy is bad across the board — you need the pre-cleaning image to diff against). | Raw high-res is now immutable. Cleaned output goes to a separate path. Both are tracked in the manifest. |
| 7 | "<2 sec/page, CPU-bound" was stated as a hard success metric without validation — bilateral filtering a full 2480×3508 image is one of the pricier OpenCV ops in this pipeline. | Added an early benchmark task in Phase 4; the metric is now explicitly provisional pending that benchmark. |

---

## 1. Strategic Overview

### 1.1 Purpose of this Group
The "Foundation" group builds the absolute ground truth of the system—not the medical data, but the physical and digital infrastructure.

By the end of this group, raw PDFs must be transformed into two clean, validated, resolution-governed image sets, accompanied by an immutable machine-readable schema. Crucially, we establish the strict file-based contracts that insulate later extraction teams from changes in rendering or preprocessing — and the identity of every document must be stable across any future re-run of this group's own code.

### 1.2 Upstream Dependencies (Inputs)
- Raw multi-page PDF files (scanned medical reports).
- A shared network drive or local folder containing the raw PDFs.

### 1.3 Downstream Commitment (Outputs for Group 2)
- **Strict Interface:** Group 2 (Extraction) will only read from `data/interim/vlm_res/` for VLM inputs and `data/metadata/manifest.parquet` for page attributes.
- **Zero Tolerance:** No downstream module (Group 2+) will ever read raw PDFs or the high-res (adaptive, ≤300 DPI) renders directly. This enforces the "Two-Resolution Rule" at the filesystem level.
- **Identity Stability:** `document_id` must be reproducible from raw file *content* alone. Re-running Group 1's pipeline against the same PDFs — for a bugfix, a deskew improvement, anything — must never change an existing `document_id`, or every downstream extraction JSON keyed to it silently orphans.

---

## 2. Parallel Work Packages (Team Self-Assigns)

The work naturally splits into four parallel streams, plus an early-start annotation track. Your team can pick up any combination:

| Work Package | Description | Parallel Opportunity |
|---|---|---|
| WP-1 | Project Scaffolding, Docker, GPU verification | Can run independently from day 1. |
| WP-2 | Schema & Region Class Definition (requires 3-5 sample pages) | Can run in parallel with WP-1; needs sample PDFs. |
| WP-3 | Manual PDF inspection → Document Assembly & Source Quality Pre-flight (PDF → adaptive-DPI PNGs, ≤300) | Depends on WP-1 being complete (for config paths). Can run in parallel with WP-2. **Starts with manual inspection, not code.** |
| WP-4 | Image Preprocessing & Dual-Resolution Generation | Depends on WP-3 (needs the high-res renders). Can run in parallel with WP-2. |
| WP-5 (Parallel Prep) | Ground Truth Annotation (Phase 9 prep) | Can be started immediately using the raw PDFs and the draft schema from WP-2. Not a formal Group 1 deliverable, but starting it early prevents a bottleneck later. |

---

## 3. Phase-by-Phase Detailed Roadmap

---

### Phase 1 — Project Scaffolding & GPU Passthrough
**Duration:** 2-3 days
**Work Package:** WP-1

**Objective:** Establish the codebase structure, dependency management, and hardware validation so that all team members work in the exact same environment.

**Inputs:**
- Blank Git repository.
- Target hardware: 2× RTX 4500 Ada (44GB combined VRAM).

**Core Modules / Tasks:**

1. **Repository Structure:**
   - Create `src/` (core logic), `configs/` (YAML configs), `data/` (raw, interim, ground_truth), `tests/`, and `docker/`.
   - Enforce a naming convention: all internal file paths must be relative to the project root.

2. **Filesystem Access Control (interim, ahead of Phase 10):**
   - `data/` is added to `.gitignore` in full — raw scans must never enter version control.
   - Document required filesystem permissions for `data/raw/` and `data/interim/` (e.g., `chmod 700` / equivalent ACL restricted to the project team) in the repo README.
   - This is a stopgap, not a substitute for Phase 10's encryption-at-rest — but PII lands on disk starting Phase 3, and Phase 10 is weeks away.

3. **Package Management:**
   - Initialize `uv` (`pyproject.toml`). Pin strict versions: `pymupdf>=1.23.0`, `opencv-python`, `pillow`, `pydantic`, `pyyaml`, `numpy`, `label-studio` (for parallel annotation), `psycopg2-binary` (for future DB), `streamlit` (for future review UI).
   - Generate a `uv.lock` file.

4. **Config-Driven Architecture:**
   - Implement a `ConfigLoader` class in `src/utils/config_loader.py` that reads `configs/pipeline.yaml` (global paths, preprocessing parameters like DPI, long-edge target) and `configs/models.yaml` (currently a dummy placeholder for Phases 5-7 models).
   - Enforce that no hardcoded paths exist in `src/` outside of reading this config. Use `pathlib.Path` throughout.

5. **Docker Base:**
   - Write a `Dockerfile` based on `nvidia/cuda:12.x-base`.
   - Add `nvidia-container-toolkit` to the `docker-compose.yml`.
   - Write a `Makefile` or shell script for common commands: `make build`, `make shell`, `make test`.

6. **GPU Verification Script:**
   - Write `src/verify_gpu.py` that prints GPU info via `torch.cuda.is_available()` and `nvidia-smi` output. This is the first thing run in any new environment.

**Outputs:**
- Repository with a `uv.lock` file and a working `Dockerfile`.
- `docker-compose.yml` with GPU passthrough configured.
- `src/utils/config_loader.py` ready to parse YAML.
- Documented filesystem permission requirements for `data/`.

**Verification (Sub-Gate 1.1):**
- Every team member runs `docker-compose up` and sees GPU memory stats on their machine.
- The empty pipeline (`python src/run_pipeline.py --dummy`) executes without errors on a dummy PDF.
- The config loader successfully reads both YAML files without throwing validation errors.

---

### Phase 2 — Schema and Region Class Definition
**Duration:** 2-3 days
**Work Package:** WP-2 (Can run in parallel with WP-1 and WP-3)

**Objective:** Create the fixed, auditable data contract. This file determines the database structure later and the extraction prompts later. This must be frozen before Phase 7 begins.

**Inputs:**
- 3-5 sample pages (physical scans) pulled from the raw PDF set.
- Domain knowledge of the occupational health check form.

**Core Modules / Tasks:**

1. **Field Schema (`configs/schema.yaml`):**
   - Define top-level fields: `employee_id`, `patient_name`, `exam_date`, `date_of_birth` (critical disambiguator), `clinic_name`, `examiner_name`.
   - Define Table Fields as structured objects, e.g.:
     ```yaml
     - field_name: "vision_left"
       data_type: "string"
       source_type: "handwritten"   # vs "typed"
       printed_row_label: "Vision (L)"  # EXACT text as it appears on form
     - field_name: "blood_pressure_systolic"
       data_type: "integer"
       source_type: "handwritten"
       printed_row_label: "B.P."
     ```
   - For every table field, explicitly capture the printed row label as it appears on the physical form. This is how the extraction layer anchors values later.

2. **Region Class Schema (`configs/regions.yaml`):**
   - Extraction Classes: `typed_text`, `handwritten_text`, `data_table_typed`, `data_table_handwritten`.
   - Discard Classes (must be detected to avoid extraction): `photo`, `thumbprint`, `signature`, `stamp_seal`.

3. **Pydantic Models for Validation:**
   - Write Python dataclass/pydantic models in `src/models/schemas.py` that strictly validate these YAML files on load.
   - If the YAML doesn't match the expected structure, the pipeline halts immediately with a clear error message.

**Outputs:**
- `configs/schema.yaml` and `configs/regions.yaml` checked into Git.
- `src/models/schemas.py` with validation logic.
- A small validation script `src/validate_schema.py` that reads the YAML and prints a pass/fail summary.

**Verification (Sub-Gate 1.2):**
- Run `python src/validate_schema.py` against the 3-5 annotated samples. The validation script must parse every field type correctly. If a field cannot be assigned to a category, revise the YAML now.
- Ensure every table field has a non-empty `printed_row_label`.

---

### Phase 3 — Document Assembly & Source Quality Pre-flight
**Duration:** 2-3 days
**Work Package:** WP-3 (Depends on WP-1; can run in parallel with WP-2)

**Objective:** Convert PDFs to adaptive-DPI images (native source resolution, capped at 300 — never upscaled), assign immutable IDs, and flag fundamentally poor source scans before any ML touches them.

**Inputs:**
- Raw PDFs placed in `data/raw/` (e.g., `data/raw/2025/batch_01/`).
- `configs/pipeline.yaml` (containing the input/output directory paths).

**Core Modules / Tasks:**

0. **Manual Inspection — do this before writing any assembly code:**
   - Manually open the current (small) batch of raw PDFs.
   - For each, confirm it contains exactly one person's report. Note any file that doesn't.
   - Eyeball scan legibility as a sanity check against the automated DPI estimate you'll compute next.
   - Record the outcome per file — this decision gates whether automated split-detection gets built at all (see step 3 below).

1. **Hash-based ID Generation:**
   - Write a function in `src/assembly/id_generator.py` that generates `document_id = sha256(file_content_bytes)` — **content only, no `mtime`.**
   - `mtime` is still recorded, but as a separate metadata column (`file_mtime`), never mixed into identity. This guarantees `document_id` is reproducible from the same file regardless of when/where it was copied or synced.

2. **Intrinsic Source Quality Check (Critical):**
   - DPI is rarely stored as PDF metadata directly — it has to be computed. For each page: get the embedded image's pixel width via `page.get_images()`, and the page's physical width in points via `page.rect.width`. Then:
     ```
     effective_dpi = image_pixel_width_px / (page_width_pts / 72)
     ```
   - If `effective_dpi < 150`, set `low_source_quality_flag = True` in the manifest.
   - **Do not upsample to fix** — just log the warning and flag it.

3. **Multi-Person-Per-File Check (conditional on step 0's findings):**
   - Automated detection here would require reading `employee_id` off the page, which needs extraction — and extraction doesn't exist until Phase 5-7. Building an OCR-dependent module now would create a hidden forward dependency and solve a problem that hasn't been confirmed to exist.
   - **If manual inspection (step 0) found zero multi-person files:** defer automated detection entirely. Record `split_check_status = "manually_cleared"` in the manifest for every document in this batch. Revisit only once Phase 7 extraction exists, where a new `employee_id` detected mid-document can raise a genuine "possible new report" review signal.
   - **If manual inspection found real cases:** do not build the full regex-on-OCR pipeline yet either. Build the lightest interim check needed to keep bad documents out of the pipeline (e.g., a page-count anomaly heuristic, or simply routing the affected files to manual pre-split before assembly), and record `split_check_status = "flagged"` with a note. Full automated detection is still deferred to Phase 7+.

4. **Rendering Engine:**
   - Write `src/assembly/renderer.py` that renders each page to 24-bit PNG at `min(source effective DPI, 300 cap)` using PyMuPDF's per-page `zoom=dpi/72` (never upscales scans).
   - Save to `data/interim/high_res/{document_id}/page_{idx:04d}.png`.

5. **Manifest Builder:**
   - Write a module that aggregates the above metadata and writes `data/metadata/manifest.parquet` (or `.jsonl`) with the following strict contract columns:
     ```json
     {
       "document_id": "a1b2c3...",
       "page_index": 0,
       "high_res_path": "data/interim/high_res/a1b2c3.../page_0000.png",
       "file_mtime": "2026-08-14T10:22:00Z",
       "raw_page_width_pts": 595,
       "effective_dpi_estimate": 75,
       "low_source_quality_flag": true,
       "split_check_status": "manually_cleared"
     }
     ```

**Outputs:**
- `data/interim/high_res/` populated with PNGs.
- `data/metadata/manifest.parquet` (the single source of truth for page-level attributes).
- A short written record of the manual inspection outcome (step 0) — feeds directly into the Gate 1 checklist.

**Verification (Sub-Gate 1.3):**
- Run `python src/verify_manifest.py`. Query for any row with a null `document_id` or null `high_res_path`. Must return 0.
- **ID stability check:** regenerate the manifest from the same raw PDFs a second time. Confirm every `document_id` is byte-identical to the first run.
- Manually open 3 rendered PNGs. Confirm they are legible at their native resolution (≤300 DPI).
- If a low-quality source exists, confirm the flag is raised before opening the image.
- Confirm every document has a non-null `split_check_status`.

---

### Phase 4 — Image Preprocessing & Resolution Governance
**Duration:** 2-3 days
**Work Package:** WP-4 (Depends on WP-3; can run in parallel with WP-2)

**Objective:** Clean the high-res images and generate the downsampled VLM copy. This is the final preprocessing step. No further image manipulation occurs downstream.

**Inputs:**
- `data/interim/high_res/` from Phase 3.
- `data/metadata/manifest.parquet` (read-only).

**Core Modules / Tasks:**

1. **High-Res Cleanup (non-destructive):**
   - Write `src/preprocessing/cleaner.py` that applies OpenCV: deskew (Hough Line Transform), crop to page content bounds (remove black borders), adaptive histogram equalization (contrast), mild bilateral filter (denoise without blurring text).
   - **Original raw renders are never overwritten.** Cleaned output is written to `data/interim/high_res_clean/{document_id}/page_{idx:04d}.png`. The roadmap's own debugging guidance — "suspect this stage first when downstream accuracy is bad across the board" — requires the pre-cleaning image to diff against; overwriting removes that option.
   - Manifest carries both: `high_res_path` (points at the cleaned version — this is what review/detection actually consume) and `high_res_raw_path` (original, retained for debugging only, not exposed across the Group 2 firewall).

2. **VLM Input Generation (The Critical Split):**
   - Write `src/preprocessing/vlm_resizer.py` that loads the **cleaned** high-res (≤300 DPI) image, generates a separate copy resized to long edge = 1280px (configurable via `configs/pipeline.yaml` down to 1024 if VRAM benchmarks require), and saves to `data/interim/vlm_res/{document_id}/page_{idx:04d}.png`.
   - **Crucial:** aspect ratio strictly preserved (e.g., 2480×3508 → ~885×1280).

3. **Manifest Regeneration:**
   - Add `vlm_res_path` and `vlm_res_width` columns. Since Parquet is columnar and not append-in-place, this means **regenerating** `manifest.parquet` with the full column set — not an incremental write. `document_id`/`page_index` values must remain identical to the Phase 3 run (see ID stability check above).

4. **Early Runtime Benchmark (do this before treating <2s/page as fixed):**
   - Run the full Phase 4 pipeline (deskew + crop + contrast + bilateral filter + resize) against 5-10 representative pages and measure wall-clock time per page. Bilateral filtering a full 2480×3508 image is one of the more expensive OpenCV operations in this chain — confirm the target is achievable before it's locked in as a Gate 1 success metric. If it isn't, either tune filter parameters or revise the target now rather than discovering it during a full-batch run.

**Outputs:**
- `data/interim/high_res_clean/` (cleaned versions, used downstream).
- `data/interim/high_res/` (untouched originals, retained for debugging).
- `data/interim/vlm_res/` (populated with downsampled copies).
- Fully populated `manifest.parquet` mapping every page to both resolutions.
- Benchmark result for per-page runtime.

**Verification (Sub-Gate 1.4 - Final Check):**
- Write `src/test_contracts.py` that, for every manifest row:
  - Asserts `high_res_path` exists and its **actual pixel dimensions** match the expected per-page render size (computed from `raw_page_width_pts × render_dpi_used / 72`), within a small tolerance — not a file-size proxy.
  - Asserts `vlm_res_path` exists and its **long edge is within the configured target range** (e.g., 1024-1280px ± tolerance), with aspect ratio preserved within tolerance.
  - Asserts `low_source_quality_flag` matches the `effective_dpi_estimate` logic from Phase 3.
- Visually spot-check 10 random pages in both resolutions side-by-side.

---

## 4. The Interface Contract (The "Firewall" for Group 2)

To ensure Group 2 (Extraction) can improve or swap models without disturbing Foundation, and vice-versa, the following absolute constraints are enforced and must be documented in `docs/group1_contract.md`:

| Contract Element | Specification |
|---|---|
| Input for Group 2 | Group 2 reads exclusively from `data/interim/vlm_res/` and `data/metadata/manifest.parquet`. It never touches raw PDFs, `high_res/`, or `high_res_clean/` directly. |
| Output from Group 2 | Group 2 must write its cropped regions to `data/processed/regions/` and extraction JSON to `data/processed/extractions/`, referencing `document_id` and `page_index` from this manifest. |
| Config Isolation | Group 2's extraction models are defined in `configs/models.yaml`. Group 1's preprocessing parameters (deskew, DPI, long-edge target) are in `configs/pipeline.yaml`. Neither group reads the other's config section. |
| ID Immutability | `document_id` is a content hash only (no `mtime`). If Group 1 regenerates `manifest.parquet` — e.g., fixing a deskew bug — `document_id` and `page_index` must remain identical for the same raw file, so Group 2's previously extracted JSON remains valid and traceable. Verified by the Phase 3 ID stability check on every regeneration. |
| Filesystem Permissions | `data/raw/`, `data/interim/`, and `data/processed/` are access-restricted to the project team (e.g., `chmod 700` / equivalent ACL). This is an interim control ahead of Phase 10's encryption-at-rest, not a replacement for it. |

---

## 5. Parallel Workstream: Ground Truth Annotation (Phase 9 Prep)

Since this work can start immediately and does not block Group 1's formal completion, it is highly recommended to launch this in parallel.

**Objective:** Generate the hand-typed ground truth for Phases 5-9 evaluation.

**Action Items:**
- Set up Label Studio locally (Dockerized) pointed at the high-res (≤300 DPI) images (for reviewer clarity). Apply the same filesystem access restrictions as `data/raw/` — this environment handles the same PII.
- Select 10-15 complete multi-page reports and physically move a copy to `data/ground_truth/eval_holdout/` to prevent evaluation leakage.
- Using the draft `schema.yaml` from Phase 2, annotate the typed and handwritten fields into a flat JSON structure per page.
- Save this as `data/ground_truth/manual_annotations.json` (to be used by Group 2's Phase 9 harness).

**Leakage Prevention:**
- Append the held-out document IDs to a `.gitignore`-ed blacklist file `configs/holdout_ids.txt`.
- Write a simple pre-flight script `src/check_holdout_leakage.py` that greps every prompt template and config file for these IDs. This script will be run by Group 2 before any extraction run.

---

## 6. Gate 1 (Foundation Exit Criteria)

Before moving to Group 2 (Extraction), the team must pass the following formal review:

- [ ] **GPU Check:** `docker run --gpus all ... nvidia-smi` passes on all team machines.
- [ ] **Schema Stable:** Phase 2 schema has been reviewed against 5 real reports; no "TBD" fields remain. `validate_schema.py` passes.
- [ ] **Manifest Completeness:** The Parquet contains entries for every page of every PDF. Count matches `sum(pdf_pages)`.
- [ ] **ID Stability:** Regenerating `manifest.parquet` from the same raw PDFs twice produces byte-identical `document_id`s.
- [ ] **Manual Inspection Recorded:** Multi-person-per-file check has been done manually on the current batch; `split_check_status` is non-null for every document, and the decision (manually cleared / flagged / deferred to Phase 7) is documented.
- [ ] **Source Flags:** At least 1 low-quality PDF has been identified and flagged in the manifest, using the computed `effective_dpi_estimate`.
- [ ] **Resolution Separation:** `vlm_res` images confirmed ~1024-1280px long edge via actual pixel-dimension checks (not file size); `high_res_clean` confirmed at its per-page render DPI (≤300); original `high_res` untouched.
- [ ] **Contract Test:** `test_contracts.py` passes with 100% success rate on the current batch, using pixel-dimension assertions.
- [ ] **Leakage Check:** `eval_holdout/` contains at least 2 complete reports, and those IDs are not present in the `vlm_res` training pool (verified by `check_holdout_leakage.py`).
- [ ] **Access Control:** `data/raw/`, `data/interim/`, and the Label Studio annotation store are confirmed access-restricted.
- [ ] **Runtime Benchmark:** Phase 4 per-page runtime measured against the <2s target; target revised now if the benchmark shows it's unrealistic.

---

## 7. Non-Goals (What is Explicitly NOT in Group 1)

To prevent scope creep, the following are strictly forbidden in this sub-project:

- No YOLO or Object Detection models (Phase 6).
- No VLM / OCR inference (Phase 5 & 7).
- No automated OCR-based multi-person split detection — this stays manual/deferred until Phase 7 unless manual inspection surfaces real cases (see Phase 3, step 3).
- No PostgreSQL setup or ORM (Phase 10).
- No Streamlit or Review UI (Phase 12).
- No RAG or Text-to-SQL (Phases 13-14).
- No full encryption-at-rest implementation (Phase 10) — Group 1 only applies interim filesystem permissions.

Any improvements to preprocessing (e.g., a better deskew algorithm) must be contained within Phase 4 modules and must not alter the file structure or manifest column names, ensuring Group 2's interface remains untouched.

---

## 8. Success Metrics for Group 1

| Metric | Target |
|---|---|
| Pipeline Runtime | < 2 seconds per PDF page (CPU-bound) — **provisional, pending Phase 4 early benchmark; revise if unachievable.** |
| Disk Footprint | High-res (~5MB/page) + high-res-clean (~5MB/page) + VLM-res (~200KB/page) ≈ ~10.2MB/page. |
| Annotation Progress | By the end of this group, the parallel annotation workstream has completed at least 5 out of 15 ground-truth reports. |
| Zero Failures | `test_contracts.py` passes with 100% success rate on the current batch. |
| ID Stability | 0 changed `document_id`s across a manifest regeneration on unchanged raw files. |

---

## 9. Handoff Checklist for Group 2

When handing over to the team building Group 2 (Extraction), provide them with:

- The exact Git commit hash of the Group 1 codebase.
- A tarball or pointer to `data/interim/vlm_res/` (the downsampled images).
- The final `data/metadata/manifest.parquet`.
- The frozen `configs/schema.yaml` and `configs/regions.yaml`.
- The `configs/holdout_ids.txt` file.
- The partially completed `data/ground_truth/manual_annotations.json` (even if not finished, it's useful for dry-runs).
- The documented manual multi-person-inspection outcome and `split_check_status` decision, so Group 2 knows whether split detection is still an open item for Phase 7.
- Confirmation that `document_id` generation is content-hash-only and verified stable across regeneration.

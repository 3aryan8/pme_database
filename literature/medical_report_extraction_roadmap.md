# Medical Examination Report Digitization & Query System
## Project Roadmap v4 (Final)

---

## 1. Project Description

### 1.1 Problem Statement

This project digitizes scanned periodic medical examination reports for a population of individuals (e.g., employees undergoing occupational health checks). No digital record of this data currently exists anywhere — the only source of truth is physical/scanned paper reports, delivered as **multi-page PDFs**, mixing:

- **Typed fields** (employee ID, name, exam date, clinic name, examiner name, table row labels)
- **Handwritten fields**, including Hindi-language handwriting, often in **tabular form** (vision test values, blood pressure readings, findings, remarks)
- **Non-textual regions** to be identified and discarded (thumbprints, photographs, signatures, stamps/seals) — which sometimes **overlap** the text regions that must be extracted
- **Multiple pages per report**, all belonging to one person's one exam

The data is **highly sensitive** and this system is intended to become the **system of record**, replacing paper entirely. A silently corrupted patient identity (two people's histories merged, or one person split into two) is worse than any individual wrong field, because it corrupts trust in the whole record without necessarily being visible.

### 1.2 Goal

1. **Extract** structured data from scanned PDF reports, correctly separating typed text, handwritten text, tabular structure, and discardable image regions — including where discard regions physically overlap extractable text.
2. **Assemble** multi-page PDFs into single coherent reports, and **resolve** each report to the correct, stable patient identity across years and across reports.
3. **Store** this data in a structured, traceable, auditable database.
4. **Expose** the data through a natural-language interface for retrieval and analysis, with citations, and a schema description that never goes stale as fields are added.

### 1.3 Constraints That Shape the Design

| Constraint | Design Consequence |
|---|---|
| Data is medical + personally identifiable | Everything runs **locally**. No cloud VLM/LLM APIs. |
| Hardware = 2× RTX 4500 Ada (20GB each, ~44GB total) | Model choices capped at ~7B VLMs comfortably, up to ~32B quantized LLMs split across both cards. VLM inputs must be resolution-managed to avoid VRAM exhaustion during batched inference. |
| Currently few reports available | Pipeline improves incrementally as volume grows — detector and fine-tuning stages are explicitly staged around this. |
| Mixed typed + handwritten + Hindi handwriting | No single model assumed sufficient; extraction-relevant stages are swappable and A/B testable, including mixed VLM/OCR hybrids behind one output contract. |
| Reports are multi-page PDFs, per-report not per-page | Requires explicit document assembly — the pipeline cannot be page-independent. |
| Same person appears across many reports over years | Requires explicit entity resolution — patient identity is not a free byproduct of extracting an ID field. |
| Source scan quality is unknown and uncontrolled | The pipeline must detect and flag low-quality source scans rather than silently pretending higher rendering resolution fixes them. |
| No digital record exists — this becomes the system of record | Traceability, auditability, and evaluation integrity are mandatory from day one. |

### 1.4 Design Philosophy

- **Gated progression.** Every phase ends with a measurable pass/fail test.
- **Modularity by design.** Detection, extraction, and query models are swappable behind fixed input/output contracts, benchmarked against the same ground truth — including OCR engines, which must be adapted to the same contract as VLMs.
- **Measure, don't assume.** No accuracy number is promised in advance for handwriting or for scan quality; both are measured and either contained (human review) or flagged as unfixable by design.
- **Everything traceable.** No value exists in the database without provenance back to source page, bounding box, model, and confidence.
- **Never merge or guess silently.** Wherever an automated decision risks corrupting identity or data — entity matching, overlapping regions, low-quality scans, missed detections — the default is to route to human review, not proceed.

---

## 2. Pipeline Architecture Overview

```
 1          2          3          4          5          6          7          8          9         10         11         12         13         14         15
Setup → Schema → Doc → Preproc → Baseline → Detect → Extract → Entity → GroundTruth → Database → Pipeline+ → Review → Text-to- → RAG → Fine-
                Assembly            (Gate1)         (+Adapter) Resolve   (Gate2)                  Docker      Loop      SQL              Tuning
```

Each arrow is a file-based or database-based handoff with a fixed JSON schema, so any stage can be re-run or have its model swapped independently. A config file controls which model is active at each stage and is also the live source of truth for the database schema description fed to the Text-to-SQL layer.

**Two resolutions exist in this pipeline, deliberately, from Phase 4 onward — this distinction matters throughout:**
- **Render resolution (adaptive, capped at 300 DPI):** used for human review display and the YOLO detector. 300 is a CAP, not a floor — each page renders at `min(source effective DPI, 300)`, so scans are never upscaled.
- **VLM input resolution (downsampled, ~1024-1280px long edge):** a separate copy generated specifically for extraction-stage inference, to keep batched VRAM usage bounded. The high-resolution render is never fed directly into the VLM.

---

## 3. Detailed Phase-by-Phase Roadmap

---

### Phase 1 — Project Scaffolding
**Duration:** 2-3 days (realistic: up to a week) | **Feasibility:** Trivial

Repository structure, `uv` environment, config-driven architecture (`configs/models.yaml`, `configs/schema.yaml`, `configs/regions.yaml`), Docker groundwork.

**Verify GPU passthrough now:** confirm `nvidia-container-toolkit` works inside Docker with a one-line `docker run --gpus all nvidia-smi` test — a commonly late-discovered blocker, cheap to catch here instead of at Phase 11.

**Verification:** Repo builds; empty pipeline runs end-to-end on a dummy PDF; GPU visible inside a test container.

---

### Phase 2 — Schema and Region Class Definition
**Duration:** 2-3 days | **Feasibility:** Trivial (thinking work)

Field schema (types, formats, typed-vs-handwritten source, and each table field's **printed row label** as it appears on the physical form) and region classes (extraction classes + explicit discard classes: `photo`, `thumbprint`, `signature`, `stamp_seal`).

**Date of birth**, if present anywhere on the physical report, is added to the schema now — the strongest available patient disambiguator, cheap to add now, a migration to add later.

**Verification:** Manually annotate 3-5 sample pages against the schema; revise before writing extraction code if categories don't fit.

---

### Phase 3 — Document Assembly
**Duration:** 2-3 days | **Feasibility:** Mostly free, given PDF input

- Render each PDF's pages to images (PyMuPDF) at **min(source effective DPI, 300)** — 300 is the render-resolution CAP referenced throughout the roadmap; scans render at native resolution and are never upscaled.
- Assign `document_id` = filename or file content hash; preserve PDF page order as page index.
- Every page/crop produced downstream carries `document_id` forward.

**Source-quality pre-flight check, run here:** read each raw PDF's intrinsic page width/resolution *before* rendering. Upsampling a low-quality source (e.g., originally scanned at ~72-150 DPI) to 300 DPI does not add real detail — it produces a larger, still-blurry image, and rendering at 300 DPI does not fix this. If a raw page's intrinsic width indicates it was scanned below roughly 150 DPI, log a `WARNING`, tag the `document_id` with a `low_source_quality` flag, and route it to **mandatory human review** in Phase 12 regardless of what confidence score extraction later produces. This sets an honest expectation: the pipeline cannot manufacture detail that was never captured in the original scan.

**Multi-person-per-file check:** manually inspect your current PDFs — confirm none of them is a stack containing more than one person's report. If any are, assembly needs a split rule: a new `employee_id` detected mid-document raises a "possible new report — flag for review" signal rather than silent appending.

**Verification:** After loading a test batch, query for any `findings` row with a null `document_id` or null `patient_id` — must return zero. Run this check after every pipeline change.

---

### Phase 4 — Image Preprocessing & Resolution Governance
**Duration:** 2-3 days | **Feasibility:** Trivial, easy to skip and regret

Deskew, crop to page bounds, contrast/brightness normalization, denoising — applied to the high-res (adaptive, ≤300 DPI) renders from Phase 3.

**VLM input resolution, defined here:** in addition to the high-res render (adaptive, ≤300 DPI) used for human review and detection, generate a **separate, downsampled copy for VLM extraction** — long edge resized to ~1024-1280px, aspect ratio preserved. A full A4 page at 300 DPI (~2480×3508px) fed natively into a VLM like Qwen2.5-VL tokenizes into 1,500+ image tokens; batching even a handful of such images in vLLM will exhaust 44GB of VRAM. This downsampled copy — not the high-resolution render — is what Phase 7's extraction stage and Phase 11's batched inference actually consume. The two resolutions are generated once here and used by different downstream consumers for the rest of the pipeline.

**Verification:** Visually spot-check 10 processed pages (both resolutions) against raw originals.

**If something's wrong:** Suspect this stage first, before suspecting the model, whenever downstream accuracy is poor across the board rather than isolated to handwriting.

---

### Phase 5 — Baseline Full-Page Extraction Experiment (GATE 1)
**Duration:** 1 week | **Feasibility:** Verified

Run Qwen2.5-VL 7B on the downsampled full-page images from Phase 4, prompted to output the Phase 2 schema with an explicit "if unsure, output null" instruction. Test whether the VLM can self-locate regions (decides if Phase 6's dedicated detector is needed).

**Verification:** Hand-check 10-15 pages, error table per field, split by error type (wrong / hallucinated / missed / correctly nulled).

**Gate 1:** Typed fields >90% → simple pipeline viable for those; handwritten tables failing → scope Phase 6 to only the failing region classes.

**Modularity note:** Run the same pages through any alternative candidate VLM using the same prompt and scoring script.

---

### Phase 6 — Region Detection (only if Gate 1 requires it)
**Duration:** 2-3 weeks | **Feasibility:** Verified, with a data-volume caveat

**Sub-phase A — prototype now** on your current small page set (Label Studio annotation, YOLO fine-tune). **Sub-phase B — recalibrate later**, as report volume grows toward the ~150-200 annotated pages needed for reliability. Recurring maintenance, not a redesign.

**Overlapping region handling:** signatures/stamps routinely overlap handwritten findings or typed exam dates.
- Compute overlap between every discard-class box and every extraction-class box using one consistent, explicitly-defined metric (e.g., intersection-area-over-extraction-box-area — not interchangeable with IoU).
- Do not skip VLM inference on overlapped crops — run extraction anyway, but **force-flag the result for human review regardless of confidence score**, so the Phase 12 reviewer corrects a pre-filled guess rather than typing from a blank field.
- Tune the overlap threshold empirically against real review-log outcomes, not a guessed number.

**Verification:** Recall ≥95% per region class. Precision tracked per class (a low-precision detector floods Phase 7 with junk crops even at high recall).

**Interaction with next stage:** Outputs `{document_id, page_index, region_class, bounding_box, confidence, overlap_flag}` per region — `overlap_flag` feeds Phase 12's routing logic directly.

---

### Phase 7 — Region-Wise Extraction
**Duration:** 2 weeks | **Feasibility:** Mostly verified; contains the project's biggest known risk

Each detected (non-discard) region crop — taken from the **downsampled VLM-resolution copy**, per Phase 4 — is sent to a VLM with a region-specific prompt, using **structured/constrained decoding** to guarantee valid JSON shape (not correctness, which is measured in Phase 9).

**Table structure:** for `data_table_handwritten` regions, the prompt demands output keyed on the **printed row label** (e.g., `{"row_label": "vision_left", "value": "6/6"}`), not positional order — row labels are typically typed even when values are handwritten, and this survives layout variation across clinics.

**Hybrid OCR / Parser Adapter, defined here:** if a pure OCR engine (Surya/Sarvam) is used instead of a VLM for a specific region class — because Phase 5/9 measurement shows it performs better on Hindi handwriting — its raw output (unstructured text blobs with bounding boxes) must pass through a **deterministic rule-based adapter** before entering the rest of the pipeline. This adapter anchors OCR text to the printed row-label coordinates on the crop (finds the label's position, grabs the nearest text blob) and outputs the **same JSON schema contract as the VLM path**. No downstream stage — Phase 9's comparison harness, Phase 10's database load, Phase 12's review UI — should ever need to know whether a given value came from a VLM or an OCR engine; the adapter's job is to make that distinction invisible past this point.

**Dynamic few-shot retrieval, replacing static examples:** static, hand-picked few-shot examples in a prompt file do not self-update as Phase 12 accumulates corrections, and manually maintaining them will not happen reliably at scale. Instead, Phase 7 implements a **retriever**: each incoming crop is embedded (reusing a vision encoder already available from the VLM, or a lightweight CLIP-style model), and the *k* most visually similar corrected examples are pulled from the `corrections` table (populated by Phase 12) and injected into the prompt at inference time. This turns human corrections into an ever-improving, automatically-sourced example bank rather than a static file someone has to remember to edit — functionally a small retrieval system feeding Phase 7, distinct from Phase 14's RAG over findings text.

**Evaluation leakage guard:** 2-3 complete reports are physically moved to `data/ground_truth/eval_holdout/` and must never appear in any prompt, few-shot pool, or config, anywhere. This is enforced by an automated check — grep every prompt template and config file for held-out `document_id`s — run as a standing pre-flight before any extraction run, not just once.

**Verification:** Spot-check a held-out batch of crops directly, isolating extraction errors from Phase 6 crop-quality errors. Full formal scoring in Phase 9.

**Modularity note:** File-based, per-model-named output folders make this the primary A/B testing point for candidate VLMs and OCR-adapter combinations against the same ground truth.

---

### Phase 8 — Entity Resolution
**Duration:** 1-2 weeks | **Feasibility:** Verified pattern, but the single highest-consequence design decision in the roadmap

The end goal is longitudinal analysis across years of reports for the same person. Treating patient identity as a free byproduct of extracting an ID field produces two silent failure modes — a typo'd ID splitting one person into two "patients," or an auto-merge on name alone blending two different people's histories into one record. The second is worse than any individual wrong field, because it corrupts trust in the whole record.

**Design:**
- A `patients` table with a stable, system-generated `patient_id`. Every report/exam links to exactly one `patient_id`, never directly to a raw extracted name/ID.
- Normalize `employee_id` (strip whitespace, uppercase) and `name` (lowercase, collapse whitespace) before any comparison.
- **Exact ID match** → auto-link, but still sanity-check the associated name; if wildly different, route to review rather than trusting the ID. Define "wildly different" numerically (e.g., an edit-distance or phonetic-similarity threshold) before Phase 10 is built, so this isn't an inconsistent judgment call.
- **Name-similar, no ID match** → always route to review. **Never auto-merge on name alone** — transliteration variance ("Geeta"/"Gita"), surname order flips, and initials-vs-full-name make exact name matching unreliable; fuzzy matching is a *candidate generator for human review*, not an auto-merge trigger.
- If DOB is available (per the Phase 2 schema addition), use it as the strongest disambiguator. If not, ID + fuzzy name matching is the operating reality, with a correspondingly higher expected review-queue rate.

**Verification:** After loading your current small report set, manually count the number of genuinely distinct people you know are represented, and compare against `patients` row count. Individually inspect every auto-merge performed during this initial pass.

**Interaction with next stage:** `patient_id` — not raw extracted name/ID — is the foreign key used everywhere downstream (Phase 10's schema, Phase 12's review UI, Phase 13/14's query layer), so later corrections to resolution logic propagate cleanly.

**If something's wrong:** A wrongly auto-merged patient discovered after the fact triggers a review of every other auto-merge performed under the same matching rule, not just a fix to the one case found.

---

### Phase 9 — Ground Truth & Evaluation Harness (GATE 2)
**Duration:** 1 week (realistic: budget more) | **Feasibility:** Trivial to build, highest value in the project

10-15 hand-typed complete reports as ground truth, including the physically separated `eval_holdout/` set from Phase 7. Table-field ground truth is typed in the same **row-labeled** form as extraction output, so the comparison script can detect a column swap rather than falsely passing a shuffled table.

Comparison script producing a per-field accuracy table, rerun on every prompt/model/detector/adapter change.

**Gate 2:** Typed fields ≥95%. Handwritten fields at an explicitly written-down "good enough, flagged for review" threshold that Phase 12's routing logic reads directly.

---

### Phase 10 — Database & Traceability
**Duration:** 1 week | **Feasibility:** Standard engineering, verified

PostgreSQL: `patients` (keyed by `patient_id` from Phase 8), `documents` (keyed by `document_id` from Phase 3), `exams`, `findings`, `sources` (page image reference, bounding box, model+version, confidence, timestamp, `overlap_flag`, `low_source_quality` flag). `corrections` table (from Phase 12) doubles as the retrieval pool for Phase 7's dynamic few-shot system.

**Data governance:** `access_log`/`accessed_by`/`accessed_at` on sensitive tables; encryption at rest for the database and raw scan store; retention policy field present even if the period is still pending decision.

**Verification:** Insert a test record end-to-end; confirm full provenance traceable via `sources` alone; enforce `NOT NULL` on `patient_id`/`document_id` foreign keys at the schema level, not just via application-side checks.

---

### Phase 11 — Full Pipeline Assembly, Docker & Batched Inference
**Duration:** 1-2 weeks (realistic: budget more given GPU/container setup) | **Feasibility:** Standard engineering, verified

Full chain: ingest → assemble → preprocess → detect → crop → extract → resolve entity → validate → load. Per-page logging; failures flagged and skipped, never crash the batch. Dockerized, with GPU passthrough already confirmed back in Phase 1.

**Schema-drift fix:** a utility function regenerates the Text-to-SQL system prompt's schema description **directly from the live database schema (or `schema.yaml`) every time a query runs**, so a newly added field is immediately queryable without a prompt-engineering update.

**Batched inference:** Phase 7 consumes crops as batches through **vLLM's offline `generate()` API**, batch size set in config, using the **downsampled VLM-resolution images from Phase 4** — never the high-res (≤300 DPI) render, which would exhaust VRAM at batch sizes above a handful. vLLM's scheduler handles variable-length requests internally; this is a request-batching interface decision, not a manual image-padding task. At current scale this isn't an urgent bottleneck, but deciding the interface now avoids a rewrite later.

**Verification:** Full container run against a fresh batch, per-page pass/fail logging confirmed, corrupted/unreadable page skipped without halting the run.

---

### Phase 12 — Human Review Loop
**Duration:** 1 week | **Feasibility:** Verified — the standard containment strategy for irreducible handwriting and scan-quality risk

Streamlit UI (using `streamlit-drawable-canvas`). Fields routed here from: Phase 9's confidence threshold, Phase 6's `overlap_flag`, Phase 3's `low_source_quality` flag, or Phase 8's entity-resolution review queue.

**Missed-region recovery:** the reviewer can **draw a new bounding box directly on the original page image and type in the missing value**, not just edit an already-extracted value — closing the detector-recall blind spot where YOLO misses a region entirely. That correction becomes a database update **and** a new row in the `corrections` table, which is consumed both by Phase 6's Sub-phase B retraining and — critically, per Phase 7's dynamic retrieval design — becomes immediately available as a live few-shot example for future extractions, without any manual prompt-file editing.

**Verification:** Deliberately delete one region from a test detector output; confirm the reviewer can recover it end-to-end through the drawing tool — a standing regression test, not a one-time check.

**Policy decision:** decide explicitly whether a field that never clears the automated confidence threshold after repeated correction is acceptable to leave as permanently manual, or must hit an automated bar before deployment is considered complete.

---

### Phase 13 — Text-to-SQL Layer
**Duration:** 2 weeks | **Feasibility:** Verified for small, known schemas like this one

Local LLM (Qwen2.5 32B quantized, split across both GPUs) converts natural language to read-only SQL against the Phase 10 schema, using the live-generated schema prompt from Phase 11. Results returned with source citations from `sources`.

**Safety:** DB connection is read-only at the permission level; generated SQL always shown to the user.

**Verification:** Test questions with known answers derived from ground-truth reports; adversarial-phrasing tests confirm the system asks for clarification or returns an empty/flagged result rather than guessing on ambiguous input.

---

### Phase 14 — RAG Layer
**Duration:** 2-3 weeks | **Feasibility:** Verified, standard RAG

Findings embedded into **pgvector** (same Postgres instance). Free-text questions answered with citations to exact source pages via `sources`.

**Expectation set correctly:** "insights across all reports" requires **SQL aggregation + RAG combined**, not RAG alone.

**Verification:** Test questions against known findings; confirm citations resolve to correct source pages through the Phase 10 traceability chain.

---

### Phase 15 — Fine-Tuning (much later, gated on data volume)
**Duration:** Ongoing | **Feasibility:** QLoRA fits the GPU budget, but needs ~500+ corrected examples not currently available

Undertaken only once Phase 9 proves prompting plateaus below an acceptable bar, and Phase 12 has accumulated sufficient corrected examples. Evaluated against the Phase 9 harness before replacing the prompted baseline in `configs/models.yaml`.

**If fine-tuning doesn't beat the baseline:** a valid outcome, not a failed phase — it confirms Phase 12's human review remains the correct permanent containment strategy.

---

## 4. Cross-Cutting Notes

### 4.1 The Two-Resolution Rule
Every page exists downstream in two forms after Phase 4: a high-res render (adaptive DPI, ≤300 — human review, detection) and a downsampled ~1024-1280px copy (VLM extraction, batched inference). No stage after Phase 4 should feed the high-resolution render directly into a VLM.

### 4.2 The One-Contract Rule
Regardless of whether a region is extracted by a VLM or by an OCR engine + adapter, its output must conform to the same JSON schema before entering Phase 9's comparison, Phase 10's database, or Phase 12's review UI. No downstream stage should need to know which extractor produced a given value.

### 4.3 Data Governance Checklist (finalized before Phase 10 build)
- [ ] Database access logged (`access_log`, `accessed_by`, `accessed_at`)
- [ ] Raw scans encrypted at rest
- [ ] Retention policy field present, period TBD if not yet decided
- [ ] Query system access restricted and logged

### 4.4 Standing Automated Checks (run on every pipeline change, not just once)
- [ ] Zero `findings` rows with null `document_id` or null `patient_id`
- [ ] Zero held-out `document_id`s present in any prompt/config file
- [ ] Detector recall ≥95% per region class, tracked per run
- [ ] Phase 9 accuracy table regenerated and diffed against the previous run on every model/prompt/adapter change
- [ ] No source-flagged (`low_source_quality`) document bypasses mandatory human review

### 4.5 What Remains Genuinely Uncertain
1. **Handwritten Hindi table accuracy** — measured honestly, contained by Phase 12.
2. **Entity resolution edge cases** — fuzzy name matching without DOB will always produce some review-queue load; inherent to the data, not a solvable bug.
3. **Source scan quality** — some documents may be fundamentally below the quality needed for reliable automated extraction; the pipeline flags these rather than pretending to fix them.
4. **Annotation/data volume as the project scales** — Phase 6 Sub-phase A/B split, solved by time and continued intake.

### 4.6 Realistic Planning Adjustments
- Double time estimates involving hand-typing ground truth against messy handwritten tables.
- Confirm `nvidia-container-toolkit` GPU passthrough in Docker during Phase 1, not Phase 11.
- Render each PDF page at `min(source effective DPI, 300)` — 300 is a **CAP, not a floor**: rendering resolution must never exceed source information content, so low-res scans render at native resolution and are never upscaled (no fake pixels for OCR/VLM); digital-native pages render at the cap.

---

## 5. Immediate Next Steps
1. Manually inspect your current PDFs for the multi-person-per-file edge case and for likely low-source-quality scans (Phase 3) — do this first.
2. Finish Phase 2 schema, including DOB (if available) and printed row labels for table fields.
3. Build Phase 3 document assembly + Phase 4 dual-resolution preprocessing alongside Phase 1 scaffolding.
4. Run Phase 5's baseline experiment.

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
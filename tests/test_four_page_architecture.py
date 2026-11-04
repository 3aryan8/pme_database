"""Synthetic integration tests for the four-page examination data model."""
from __future__ import annotations

import json
import os
import sqlite3

import pytest
import pymupdf
from cryptography.fernet import Fernet
from PIL import Image
from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.orm import Session

from src.database import importer
from src.database import doctor_assets
from src.database.database import SCHEMA_REVISION, init_db
from src.database.lifecycle import transition_examination_status, transition_page_status
from src.database.models import (
    Base,
    Candidate,
    DocumentAccessEvent,
    ExaminationAuthentication,
    ExaminationDocument,
    ExaminationPageStatus,
    ExaminationStatusEvent,
    ExtractedFieldValue,
    MedicalExamination,
    SourceDocument,
    SourceDocumentPage,
)
from src.database.repository import get_examination_by_id
from src.database.schemas import PMEExtraction
from src.database.security import (
    decrypt_contact,
    encrypt_contact,
    link_original_pdf,
    mask_contact,
    read_private_asset,
    retrieve_document,
    register_source_manifest,
    store_evidence,
    store_original_pdf,
)


@pytest.fixture()
def db_session(monkeypatch):
    monkeypatch.setenv("PME_FIELD_ENCRYPTION_KEY", Fernet.generate_key().decode())
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


def _record(
    document_id: str,
    roll_number: str,
    candidate_name: str,
    candidate_class: str,
    source_document_id: int | None = None,
):
    return PMEExtraction(
        document_id=document_id,
        source_pdf_sha256="a" * 64,
        source_pdf_pages={0: 11, 1: 12, 2: 13, 3: 14},
        source_packet_index=0,
        source_document_id=source_document_id,
        pages_covered=[0, 1, 2, 3],
        fields={
            "page_1_basic_info": {
                "general_details": {
                    "candidate_name": candidate_name,
                    "father_name": "SYNTHETIC FATHER",
                    "date_of_birth": "1990-01-02",
                    "dv_date": "2024-02-03",
                    "medical_examination_date": "2024-02-04",
                },
                "narrative_details": {
                    "roll_number": roll_number,
                    "class": candidate_class,
                    "recruitment_cen": "TEST-CEN",
                },
                "physical_traits": {
                    "permanent_physical_identification_marks": "SYNTHETIC MARK"
                },
            },
            "page_2_medical_metrics": {
                "pme_case": {"urine": "RAW NORMAL", "sugar": None, "alb": None},
                "right_side_table": [
                    {"row": "K1", "side_r": "12.5", "side_l": "13.0"}
                ],
                "handwritten_remarks": "unclear handwritten text",
            },
            "page_3_fitness_classification": {
                "fit_in_class": "FIT IN A3",
                "unfit_in_class": None,
                "accuracy_of_vision": {
                    "right_eye": {"distance_uncorrected": "6/6"},
                    "left_eye": {"distance_uncorrected": "6/9"},
                },
            },
            "page_4_declarations": {
                "repeated_candidate_particulars": {
                    "candidate_name": f"{candidate_name} SNAPSHOT",
                    "father_name": "SYNTHETIC FATHER",
                    "roll_number": roll_number,
                    "mobile_number": "5550001234",
                    "email": "synthetic@example.test",
                },
                "part_one": [{"question_no": "1a", "answer": "No"}],
            },
        },
        provenance={
            "page_2_medical_metrics.handwritten_remarks": {
                "page_index": 1,
                "model": "synthetic-test",
                "raw_value": "unclear handwritten text",
                "confidence": 0.41,
                "validation_status": "AMBIGUOUS",
                "human_verification_status": "PENDING",
                "source_pdf_page_number": 12,
                "bounding_box": [0.1, 0.2, 0.8, 0.3],
            }
        },
    )


def _import(session, monkeypatch, tmp_path, record):
    monkeypatch.setattr(
        importer,
        "find_report_images",
        lambda *_args, **_kwargs: [
            (page, tmp_path / f"page-{page}.png") for page in range(1, 5)
        ],
    )
    with session.begin_nested():
        examination, created = importer.import_one(session, record)
    session.flush()
    return examination, created


def test_import_creates_four_sections_statuses_and_page_mapping(
    db_session, monkeypatch, tmp_path
):
    examination, created = _import(
        db_session, monkeypatch, tmp_path,
        _record("synthetic-doc-1", "SYNTH-001", "SYNTHETIC CANDIDATE", "A3"),
    )
    loaded = get_examination_by_id(db_session, examination.id)

    assert created is True
    assert loaded.page_1.candidate_class == "A3"
    assert loaded.medical_class is None
    assert loaded.dv_date.isoformat() == "2024-02-03"
    assert loaded.medical_examination_date.isoformat() == "2024-02-04"
    assert loaded.pme_case.urine == "RAW NORMAL"
    assert loaded.vision.right_distance_uncorrected == "6/6"
    assert loaded.fitness.fit_in_class == "FIT IN A3"
    assert loaded.fitness.unfit_in_class is None
    assert loaded.page_4.mobile_number_encrypted
    assert loaded.page_4.email_encrypted
    raw_fields = loaded.extraction_runs[0].raw_json["fields"]
    assert raw_fields["page_4_declarations"]["repeated_candidate_particulars"][
        "mobile_number"
    ] == "[ENCRYPTED]"
    assert raw_fields["page_4_declarations"]["repeated_candidate_particulars"][
        "email"
    ] == "[ENCRYPTED]"
    assert len(loaded.page_statuses) == 4
    assert {page.status for page in loaded.page_statuses} == {"PENDING_REVIEW"}
    assert {image.source_pdf_page_number for image in loaded.report_images} == {11, 12, 13, 14}
    assert len(loaded.authentication_records) == 4
    assert all(row.signature_status == "UNVERIFIED" for row in loaded.authentication_records)


def test_second_examination_preserves_candidate_master_and_page_snapshots(
    db_session, monkeypatch, tmp_path
):
    first, _ = _import(
        db_session, monkeypatch, tmp_path,
        _record("synthetic-doc-1", "SYNTH-002", "ORIGINAL MASTER NAME", "A3"),
    )
    second, created = _import(
        db_session, monkeypatch, tmp_path,
        _record("synthetic-doc-2", "SYNTH-002", "LATER FORM NAME", "B2"),
    )
    candidate = db_session.scalar(
        select(Candidate).where(Candidate.roll_number == "SYNTH-002")
    )

    assert created is True
    assert first.id != second.id
    assert candidate.candidate_name == "ORIGINAL MASTER NAME"
    assert first.page_1.candidate_name == "ORIGINAL MASTER NAME"
    assert second.page_1.candidate_name == "LATER FORM NAME"
    assert second.page_1.candidate_class == "B2"
    assert second.page_4.candidate_name == "LATER FORM NAME SNAPSHOT"
    assert db_session.scalar(select(MedicalExamination).where(
        MedicalExamination.candidate_id == candidate.id
    )) is not None


def test_duplicate_import_does_not_duplicate_exam_or_pages(db_session, monkeypatch, tmp_path):
    record = _record("synthetic-duplicate", "SYNTH-003", "SYNTHETIC NAME", "A3")
    first, created = _import(db_session, monkeypatch, tmp_path, record)
    second, created_again = _import(db_session, monkeypatch, tmp_path, record)

    assert created and not created_again
    assert first.id == second.id
    assert db_session.query(MedicalExamination).count() == 1
    assert db_session.query(ExaminationPageStatus).count() == 4


def test_incomplete_extraction_remains_partial_and_unprocessed_pages_stay_open(
    db_session, monkeypatch, tmp_path
):
    record = _record(
        "synthetic-partial", "SYNTH-010", "SYNTHETIC NAME", "A3"
    )
    record.pages_covered = [0, 1]
    examination, _ = _import(db_session, monkeypatch, tmp_path, record)

    assert examination.overall_status == "PARTIALLY_EXTRACTED"
    assert {page.page_number for page in examination.page_statuses if page.status == "PENDING_REVIEW"} == {1, 2}
    assert {page.page_number for page in examination.page_statuses if page.status == "NOT_STARTED"} == {3, 4}


def test_field_provenance_keeps_ambiguous_raw_value_for_review(
    db_session, monkeypatch, tmp_path
):
    examination, _ = _import(
        db_session, monkeypatch, tmp_path,
        _record("synthetic-provenance", "SYNTH-004", "SYNTHETIC NAME", "A3"),
    )
    field = db_session.scalar(
        select(ExtractedFieldValue).where(
            ExtractedFieldValue.examination_id == examination.id,
            ExtractedFieldValue.field_name.endswith("handwritten_remarks"),
        )
    )

    assert field.extracted_value == "unclear handwritten text"
    assert field.normalized_value is None
    assert field.confidence == 0.41
    assert field.validation_status == "AMBIGUOUS"
    assert field.human_verification_status == "PENDING"
    assert field.form_page_number == 2
    assert field.source_pdf_page_number == 12
    assert field.bounding_box == [0.1, 0.2, 0.8, 0.3]


def test_status_transition_requires_four_verified_pages(db_session, monkeypatch, tmp_path):
    examination, _ = _import(
        db_session, monkeypatch, tmp_path,
        _record("synthetic-status", "SYNTH-005", "SYNTHETIC NAME", "A3"),
    )
    transition_examination_status(
        db_session, examination.id, "VERIFIED", actor="synthetic-reviewer"
    )
    with pytest.raises(ValueError, match="All four page sections"):
        transition_examination_status(
            db_session, examination.id, "COMPLETED", actor="synthetic-reviewer"
        )
    for page_number in range(1, 5):
        transition_page_status(
            db_session, examination.id, page_number, "VERIFIED"
        )
    transition_examination_status(
        db_session, examination.id, "COMPLETED", actor="synthetic-reviewer"
    )
    assert examination.overall_status == "COMPLETED"
    assert db_session.query(ExaminationStatusEvent).filter_by(
        examination_id=examination.id
    ).count() == 3


def test_encrypted_contact_and_document_access_audit(
    db_session, monkeypatch, tmp_path
):
    monkeypatch.setenv("PME_FIELD_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("PME_DOCUMENT_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("PME_PRIVATE_DOCUMENT_ROOT", str(tmp_path / "private"))
    encrypted = encrypt_contact("synthetic@example.test")
    assert b"synthetic@example.test" not in encrypted
    assert decrypt_contact(encrypted) == "synthetic@example.test"
    assert mask_contact("5550001234") == "***-***-1234"
    assert mask_contact("synthetic@example.test") == "s***@example.test"

    candidate = Candidate(roll_number="SYNTH-006", candidate_name="SYNTHETIC NAME")
    examination = MedicalExamination(candidate=candidate)
    db_session.add(examination)
    db_session.flush()
    asset = b"synthetic image evidence only"
    evidence = store_evidence(
        db_session,
        examination_id=examination.id,
        content=asset,
        asset_type="SIGNATURE",
        form_page_number=3,
        source_pdf_page_number=13,
        media_type="image/png",
    )
    db_session.commit()
    encrypted_path = tmp_path / "private" / evidence.storage_key
    assert encrypted_path.read_bytes() != asset
    assert retrieve_document(
        db_session,
        evidence.id,
        actor="synthetic-reviewer",
        authorize=lambda *_: True,
    ) == asset
    db_session.commit()
    assert read_private_asset(
        db_session,
        evidence.storage_key,
        actor="synthetic-reviewer",
        authorize=lambda *_: True,
    ) == asset
    db_session.commit()

    denied = retrieve_document(
        db_session,
        evidence.id,
        actor="synthetic-denied-user",
        authorize=lambda *_: False,
    )
    db_session.commit()
    assert denied is None
    assert db_session.query(DocumentAccessEvent).count() == 3
    assert db_session.query(DocumentAccessEvent).filter_by(allowed=False).count() == 1


def test_visual_assets_are_separate_and_keep_actual_page_numbers(
    db_session, monkeypatch, tmp_path
):
    monkeypatch.setenv("PME_DOCUMENT_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("PME_PRIVATE_DOCUMENT_ROOT", str(tmp_path / "private"))
    region_root = tmp_path / "regions"
    document_id = "synthetic-visual-evidence"
    region_dir = region_root / document_id
    region_dir.mkdir(parents=True)
    image_paths = {}
    detections = {
        0: [{"region_class": "photo", "box_norm": [0.1, 0.1, 0.8, 0.8]}],
        1: [{"region_class": "thumbprint", "box_norm": [0.1, 0.1, 0.8, 0.8]}],
        2: [
            {"region_class": "signature", "box_norm": [0.1, 0.1, 0.8, 0.8]},
            {"region_class": "stamp_seal", "box_norm": [0.1, 0.1, 0.8, 0.8]},
        ],
        3: [
            {"region_class": "signature", "box_norm": [0.1, 0.1, 0.8, 0.8]},
            {"region_class": "stamp_seal", "box_norm": [0.1, 0.1, 0.8, 0.8]},
        ],
    }
    for page_index, regions in detections.items():
        image_path = tmp_path / f"render-{page_index}.png"
        Image.new("RGB", (100, 100), (page_index * 30, 80, 120)).save(image_path)
        image_paths[page_index + 1] = image_path
        (region_dir / f"page_{page_index:04d}.json").write_text(json.dumps({
            "page_index": page_index,
            "detections": regions,
        }))
    monkeypatch.setattr(
        doctor_assets,
        "find_report_images",
        lambda _document_id: list(image_paths.items()),
    )
    candidate = Candidate(roll_number="SYNTH-009", candidate_name="SYNTHETIC")
    examination = MedicalExamination(candidate=candidate)
    db_session.add(examination)
    db_session.flush()

    records = doctor_assets.save_examination_visual_evidence(
        db_session,
        examination.id,
        document_id,
        {0: 11, 1: 12, 2: 13, 3: 14},
        region_root=region_root,
    )
    db_session.commit()
    assets = list(db_session.scalars(
        select(ExaminationDocument)
        .where(ExaminationDocument.examination_id == examination.id)
        .order_by(ExaminationDocument.form_page_number, ExaminationDocument.asset_type)
    ))

    assert {asset.asset_type for asset in assets} == {
        "CANDIDATE_PHOTO", "CANDIDATE_THUMBPRINT", "SIGNATURE", "STAMP_SEAL"
    }
    assert {(asset.form_page_number, asset.source_pdf_page_number) for asset in assets} == {
        (1, 11), (2, 12), (3, 13), (4, 14)
    }
    assert len(records) == 4
    assert records[2].signature_status == "UNVERIFIED"
    assert records[3].stamp_status == "UNVERIFIED"
    assert records[0].signature_status == "MISSING"


def test_source_manifest_keeps_supplemental_pages_unassigned(
    db_session, monkeypatch, tmp_path
):
    monkeypatch.setenv("PME_DOCUMENT_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("PME_PRIVATE_DOCUMENT_ROOT", str(tmp_path / "private"))
    pdf_path = tmp_path / "synthetic-source.pdf"
    pdf_path.write_bytes(b"%PDF-synthetic-only")
    source = store_original_pdf(db_session, pdf_path)
    supplemental = SourceDocumentPage(
        source_document_id=source.id,
        source_pdf_page_number=9,
        page_kind="SUPPLEMENTAL",
        supplemental_kind="synthetic_attachment",
    )
    db_session.add(supplemental)
    db_session.commit()

    stored = db_session.scalar(select(SourceDocumentPage))
    assert stored.page_kind == "SUPPLEMENTAL"
    assert stored.examination_id is None
    assert db_session.scalar(select(SourceDocument)).sha256 == source.sha256


def test_reviewed_manifest_registers_forms_and_supplemental_pages(
    db_session, monkeypatch, tmp_path
):
    monkeypatch.setenv("PME_DOCUMENT_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("PME_PRIVATE_DOCUMENT_ROOT", str(tmp_path / "private"))
    source_path = tmp_path / "synthetic-packet.pdf"
    pdf = pymupdf.open()
    for _ in range(5):
        pdf.new_page()
    pdf.save(source_path)
    pdf.close()
    import hashlib
    import yaml

    config_path = tmp_path / "split.yaml"
    config_path.write_text(yaml.safe_dump({
        "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "confirmed": True,
        "persons": [{"pages": [1, 4]}],
        "supplemental_documents": [{"kind": "synthetic_attachment", "pages": [5]}],
    }))

    source = register_source_manifest(db_session, source_path, config_path)
    db_session.commit()
    pages = list(db_session.scalars(
        select(SourceDocumentPage)
        .where(SourceDocumentPage.source_document_id == source.id)
        .order_by(SourceDocumentPage.source_pdf_page_number)
    ))

    assert len(pages) == 5
    assert [(page.page_kind, page.form_page_number) for page in pages[:4]] == [
        ("CANDIDATE_FORM", 1),
        ("CANDIDATE_FORM", 2),
        ("CANDIDATE_FORM", 3),
        ("CANDIDATE_FORM", 4),
    ]
    assert all(page.examination_id is None and page.packet_index == 0 for page in pages[:4])
    assert pages[4].page_kind == "SUPPLEMENTAL"
    assert pages[4].examination_id is None


def test_import_links_only_the_reviewed_packet_pages(
    db_session, monkeypatch, tmp_path
):
    source = SourceDocument(
        sha256="b" * 64,
        storage_key="source/synthetic.fernet",
        original_filename="synthetic.pdf",
        media_type="application/pdf",
        file_size_bytes=20,
    )
    db_session.add(source)
    db_session.flush()
    for form_page, source_page in enumerate((11, 12, 13, 14), start=1):
        db_session.add(
            SourceDocumentPage(
                source_document_id=source.id,
                source_pdf_page_number=source_page,
                page_kind="CANDIDATE_FORM",
                packet_index=2,
                form_page_number=form_page,
            )
        )
    db_session.add(
        SourceDocumentPage(
            source_document_id=source.id,
            source_pdf_page_number=15,
            page_kind="SUPPLEMENTAL",
            supplemental_kind="synthetic_attachment",
        )
    )
    db_session.flush()

    record = _record(
        "synthetic-linked-doc", "SYNTH-008", "SYNTHETIC CANDIDATE", "A3",
        source_document_id=source.id,
    )
    record.source_packet_index = 2
    examination, _ = _import(db_session, monkeypatch, tmp_path, record)
    pages = list(db_session.scalars(
        select(SourceDocumentPage)
        .where(SourceDocumentPage.source_document_id == source.id)
        .order_by(SourceDocumentPage.source_pdf_page_number)
    ))

    assert [page.examination_id for page in pages[:4]] == [examination.id] * 4
    assert pages[4].examination_id is None
    assert pages[4].page_kind == "SUPPLEMENTAL"
    assert db_session.query(ExaminationDocument).filter_by(
        examination_id=examination.id, asset_type="ORIGINAL_PDF"
    ).count() == 1


def test_import_failure_rolls_back_related_rows(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(
        importer,
        "find_report_images",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(FileNotFoundError("synthetic failure")),
    )
    with pytest.raises(FileNotFoundError, match="synthetic failure"):
        with db_session.begin_nested():
            importer.import_one(
                db_session,
                _record("synthetic-rollback", "SYNTH-007", "SYNTHETIC NAME", "A3"),
            )
    assert db_session.query(Candidate).count() == 0
    assert db_session.query(MedicalExamination).count() == 0
    assert db_session.query(ExaminationPageStatus).count() == 0


def test_import_failure_output_does_not_expose_candidate_values(
    db_session, capsys, tmp_path
):
    record = _record(
        "synthetic-log-record",
        "SYNTHETIC-ROLL-PRIVATE",
        "SYNTHETIC NAME PRIVATE",
        "A3",
    )
    folder = tmp_path / "synthetic-log-record"
    folder.mkdir()
    (folder / "record.json").write_text(record.model_dump_json())

    assert importer.import_directory(db_session, tmp_path) == (0, 1)
    output = capsys.readouterr().out
    assert "SYNTHETIC-ROLL-PRIVATE" not in output
    assert "SYNTHETIC NAME PRIVATE" not in output
    assert "FileNotFoundError" in output


def test_foreign_keys_are_valid(db_session):
    assert db_session.connection().exec_driver_sql("PRAGMA foreign_key_check").all() == []


def test_init_db_stamps_only_a_new_empty_database():
    engine = create_engine("sqlite:///:memory:")
    init_db(engine)
    with engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one() == SCHEMA_REVISION
        assert "examination_page_status" in inspect(connection).get_table_names()
    engine.dispose()


def test_init_db_refuses_to_mutate_existing_unstamped_database():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE legacy_marker (id INTEGER PRIMARY KEY)")
    with pytest.raises(RuntimeError, match="has not been migrated"):
        init_db(engine)
    with engine.connect() as connection:
        assert inspect(connection).get_table_names() == ["legacy_marker"]
    engine.dispose()
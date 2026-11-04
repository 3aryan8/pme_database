"""Add four-page examination data structures without deleting legacy data.

Revision ID: 20261104_01
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "20261104_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "medical_examinations",
        sa.Column(
            "overall_status",
            sa.String(length=32),
            server_default="PENDING_REVIEW",
            nullable=False,
        ),
    )
    op.create_index(
        "ix_medical_examinations_medical_examination_date",
        "medical_examinations",
        ["medical_examination_date"],
    )
    op.create_table(
        "examination_page_status",
        sa.Column("examination_id", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="NOT_STARTED", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.CheckConstraint("page_number BETWEEN 1 AND 4", name="ck_page_status_number"),
        sa.CheckConstraint(
            "status IN ('NOT_STARTED','PROCESSING','PARTIALLY_EXTRACTED','PENDING_REVIEW','VERIFIED','FAILED')",
            name="ck_page_status_value",
        ),
        sa.ForeignKeyConstraint(["examination_id"], ["medical_examinations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("examination_id", "page_number"),
    )

    op.create_table(
        "examination_page_1",
        sa.Column("examination_id", sa.Integer(), nullable=False),
        sa.Column("roll_number", sa.String(length=50), nullable=True),
        sa.Column("candidate_name", sa.String(length=200), nullable=True),
        sa.Column("father_name", sa.String(length=200), nullable=True),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("dv_date", sa.Date(), nullable=True),
        sa.Column("medical_examination_date", sa.Date(), nullable=True),
        sa.Column("recruitment_cen", sa.String(length=50), nullable=True),
        sa.Column("post_name", sa.String(length=200), nullable=True),
        sa.Column("candidate_class", sa.String(length=100), nullable=True),
        sa.Column("age_raw", sa.String(length=50), nullable=True),
        sa.Column("memo_number", sa.String(length=100), nullable=True),
        sa.Column("addressee_or_hospital", sa.Text(), nullable=True),
        sa.Column("permanent_identification_marks", sa.Text(), nullable=True),
        sa.Column("station", sa.String(length=200), nullable=True),
        sa.Column("station_date", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["examination_id"], ["medical_examinations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("examination_id"),
    )
    op.create_index(
        "ix_examination_page_1_candidate_class",
        "examination_page_1",
        ["candidate_class"],
    )
    op.create_table(
        "examination_page_4",
        sa.Column("examination_id", sa.Integer(), nullable=False),
        sa.Column("candidate_name", sa.String(length=200), nullable=True),
        sa.Column("father_name", sa.String(length=200), nullable=True),
        sa.Column("roll_number", sa.String(length=50), nullable=True),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("mobile_number_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("email_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("permanent_identification_marks", sa.Text(), nullable=True),
        sa.Column("declaration_date", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["examination_id"], ["medical_examinations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("examination_id"),
    )

    with op.batch_alter_table("report_images") as batch_op:
        batch_op.add_column(sa.Column("source_pdf_page_number", sa.Integer(), nullable=True))

    op.create_table(
        "source_document_pages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_document_id", sa.Integer(), nullable=False),
        sa.Column("source_pdf_page_number", sa.Integer(), nullable=False),
        sa.Column("page_kind", sa.String(length=24), nullable=False),
        sa.Column("examination_id", sa.Integer(), nullable=True),
        sa.Column("packet_index", sa.Integer(), nullable=True),
        sa.Column("form_page_number", sa.Integer(), nullable=True),
        sa.Column("supplemental_kind", sa.String(length=80), nullable=True),
        sa.CheckConstraint("source_pdf_page_number >= 1", name="ck_source_page_number"),
        sa.CheckConstraint("page_kind IN ('CANDIDATE_FORM','SUPPLEMENTAL','UNCLASSIFIED')", name="ck_source_page_kind"),
        sa.CheckConstraint(
            "(page_kind = 'CANDIDATE_FORM' AND form_page_number BETWEEN 1 AND 4 AND "
            "(examination_id IS NOT NULL OR packet_index IS NOT NULL)) OR "
            "(page_kind != 'CANDIDATE_FORM' AND examination_id IS NULL AND "
            "packet_index IS NULL AND form_page_number IS NULL)",
            name="ck_source_page_assignment",
        ),
        sa.ForeignKeyConstraint(["source_document_id"], ["source_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["examination_id"], ["medical_examinations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_document_id", "source_pdf_page_number", name="uq_source_document_page"),
        sa.UniqueConstraint("examination_id", "form_page_number", name="uq_exam_form_page"),
    )
    op.create_index("ix_source_document_pages_source_document_id", "source_document_pages", ["source_document_id"])
    op.create_index("ix_source_document_pages_examination_id", "source_document_pages", ["examination_id"])

    op.create_table(
        "source_documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("media_type", sa.String(length=100), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("file_size_bytes >= 0", name="ck_source_document_size"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sha256"),
        sa.UniqueConstraint("storage_key"),
    )

    op.create_table(
        "examination_documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("examination_id", sa.Integer(), nullable=False),
        sa.Column("source_document_id", sa.Integer(), nullable=True),
        sa.Column("form_page_number", sa.Integer(), nullable=True),
        sa.Column("source_pdf_page_number", sa.Integer(), nullable=True),
        sa.Column("asset_type", sa.String(length=40), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("media_type", sa.String(length=100), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("verification_status", sa.String(length=32), server_default="UNVERIFIED", nullable=False),
        sa.CheckConstraint("form_page_number IS NULL OR form_page_number BETWEEN 1 AND 4", name="ck_document_form_page"),
        sa.CheckConstraint("source_pdf_page_number IS NULL OR source_pdf_page_number >= 1", name="ck_document_source_page"),
        sa.CheckConstraint("file_size_bytes >= 0", name="ck_examination_document_size"),
        sa.CheckConstraint("verification_status IN ('MISSING','UNVERIFIED','PENDING_REVIEW','VERIFIED','REJECTED')", name="ck_document_verification_status"),
        sa.ForeignKeyConstraint(["examination_id"], ["medical_examinations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_document_id"], ["source_documents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("examination_id", "asset_type", "form_page_number", "sha256", name="uq_examination_document_evidence"),
    )
    op.create_index("ix_examination_documents_examination_id", "examination_documents", ["examination_id"])
    op.create_index("ix_examination_documents_source_document_id", "examination_documents", ["source_document_id"])
    op.create_index("ix_examination_documents_sha256", "examination_documents", ["sha256"])

    op.create_table(
        "examination_authentication",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("examination_id", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("source_pdf_page_number", sa.Integer(), nullable=True),
        sa.Column("actor_role", sa.String(length=32), server_default="UNKNOWN", nullable=False),
        sa.Column("doctor_id", sa.Integer(), nullable=True),
        sa.Column("observed_name", sa.String(length=200), nullable=True),
        sa.Column("designation", sa.String(length=200), nullable=True),
        sa.Column("registration_number", sa.String(length=100), nullable=True),
        sa.Column("signed_date", sa.Date(), nullable=True),
        sa.Column("signature_status", sa.String(length=24), server_default="UNVERIFIED", nullable=False),
        sa.Column("stamp_status", sa.String(length=24), server_default="UNVERIFIED", nullable=False),
        sa.Column("signature_document_id", sa.Integer(), nullable=True),
        sa.Column("stamp_document_id", sa.Integer(), nullable=True),
        sa.CheckConstraint("page_number BETWEEN 1 AND 4", name="ck_auth_form_page"),
        sa.CheckConstraint("source_pdf_page_number IS NULL OR source_pdf_page_number >= 1", name="ck_auth_source_page"),
        sa.CheckConstraint("actor_role IN ('MEDICAL_EXAMINER','ISSUING_OFFICIAL','CANDIDATE','UNKNOWN')", name="ck_auth_actor_role"),
        sa.CheckConstraint("signature_status IN ('MISSING','UNVERIFIED','PENDING_REVIEW','VERIFIED','REJECTED')", name="ck_auth_signature_status"),
        sa.CheckConstraint("stamp_status IN ('MISSING','UNVERIFIED','PENDING_REVIEW','VERIFIED','REJECTED')", name="ck_auth_stamp_status"),
        sa.ForeignKeyConstraint(["doctor_id"], ["doctors.id"]),
        sa.ForeignKeyConstraint(["examination_id"], ["medical_examinations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["signature_document_id"], ["examination_documents.id"]),
        sa.ForeignKeyConstraint(["stamp_document_id"], ["examination_documents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_examination_authentication_examination_id", "examination_authentication", ["examination_id"])

    op.create_table(
        "extracted_field_values",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("examination_id", sa.Integer(), nullable=False),
        sa.Column("extraction_run_id", sa.Integer(), nullable=False),
        sa.Column("field_name", sa.String(length=200), nullable=False),
        sa.Column("form_page_number", sa.Integer(), nullable=False),
        sa.Column("source_pdf_page_number", sa.Integer(), nullable=True),
        sa.Column("extracted_value", sa.JSON(), nullable=True),
        sa.Column("normalized_value", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("validation_status", sa.String(length=24), server_default="PENDING", nullable=False),
        sa.Column("human_verification_status", sa.String(length=24), server_default="PENDING", nullable=False),
        sa.Column("bounding_box", sa.JSON(), nullable=True),
        sa.Column("supersedes_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("form_page_number BETWEEN 1 AND 4", name="ck_field_form_page"),
        sa.CheckConstraint("source_pdf_page_number IS NULL OR source_pdf_page_number >= 1", name="ck_field_source_page"),
        sa.CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="ck_field_confidence"),
        sa.CheckConstraint("validation_status IN ('PENDING','VALID','INVALID','AMBIGUOUS')", name="ck_field_validation_status"),
        sa.CheckConstraint("human_verification_status IN ('PENDING','VERIFIED','REJECTED','NOT_REQUIRED')", name="ck_field_human_status"),
        sa.ForeignKeyConstraint(["examination_id"], ["medical_examinations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["extraction_run_id"], ["extraction_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supersedes_id"], ["extracted_field_values.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_extracted_field_values_examination_id", "extracted_field_values", ["examination_id"])
    op.create_index("ix_extracted_field_values_extraction_run_id", "extracted_field_values", ["extraction_run_id"])
    op.create_index("ix_field_review", "extracted_field_values", ["human_verification_status", "validation_status"])

    op.create_table(
        "examination_status_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("examination_id", sa.Integer(), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=True),
        sa.Column("to_status", sa.String(length=32), nullable=False),
        sa.Column("actor", sa.String(length=100), server_default="system", nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["examination_id"], ["medical_examinations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_examination_status_events_examination_id", "examination_status_events", ["examination_id"])

    op.create_table(
        "document_access_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("examination_document_id", sa.Integer(), nullable=False),
        sa.Column("actor", sa.String(length=100), nullable=False),
        sa.Column("action", sa.String(length=24), nullable=False),
        sa.Column("allowed", sa.Boolean(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["examination_document_id"], ["examination_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_access_events_examination_document_id", "document_access_events", ["examination_document_id"])

    with op.batch_alter_table("pme_vision_rows") as batch_op:
        batch_op.add_column(sa.Column("right_normalized_value", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("left_normalized_value", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("unit", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("source_pdf_page_number", sa.Integer(), nullable=True))
    with op.batch_alter_table("pme_case_measurements") as batch_op:
        batch_op.add_column(sa.Column("normalized_value", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("unit", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("source_pdf_page_number", sa.Integer(), nullable=True))

    connection = op.get_bind()
    connection.execute(
        sa.text("""
            INSERT INTO examination_page_1
                (examination_id, roll_number, candidate_name, father_name, date_of_birth,
                 dv_date, medical_examination_date, recruitment_cen, candidate_class,
                 permanent_identification_marks)
            SELECT e.id, c.roll_number, c.candidate_name, c.father_name, c.date_of_birth,
                   e.dv_date, e.medical_examination_date, c.recruitment_cen,
                   e.medical_class, e.identification_marks
            FROM medical_examinations e JOIN candidates c ON c.id = e.candidate_id
        """)
    )
    connection.execute(
        sa.text("""
            INSERT INTO examination_page_4 (examination_id, declaration_date)
            SELECT id, candidate_declaration_date FROM medical_examinations
        """)
    )
    connection.execute(
        sa.text("""
            INSERT INTO examination_page_status (examination_id, page_number, status)
            SELECT e.id, p.page_number, 'PENDING_REVIEW'
            FROM medical_examinations e
            CROSS JOIN (
                SELECT 1 AS page_number UNION ALL SELECT 2 UNION ALL
                SELECT 3 UNION ALL SELECT 4
            ) p
        """)
    )
    connection.execute(
        sa.text("""
            INSERT INTO examination_status_events (examination_id, from_status, to_status, actor, reason)
            SELECT id, NULL, 'PENDING_REVIEW', 'migration:20261104_01',
                   'Legacy examination imported before lifecycle tracking'
            FROM medical_examinations
        """)
    )
    connection.execute(
        sa.text("""
            INSERT INTO examination_authentication
                (examination_id, page_number, actor_role, signature_status, stamp_status)
            SELECT e.id, p.page_number, 'UNKNOWN', 'UNVERIFIED', 'UNVERIFIED'
            FROM medical_examinations e
            CROSS JOIN (
                SELECT 1 AS page_number UNION ALL SELECT 2 UNION ALL
                SELECT 3 UNION ALL SELECT 4
            ) p
        """)
    )


def downgrade() -> None:
    raise RuntimeError(
        "This migration is forward-only. Restore the timestamped pre-migration backup to roll back."
    )
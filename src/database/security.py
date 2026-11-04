from __future__ import annotations

import hashlib
import mimetypes
import os
import tempfile
from collections.abc import Callable
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    DocumentAccessEvent,
    ExaminationDocument,
    SourceDocument,
    SourceDocumentPage,
)


def _cipher(environment_variable: str) -> Fernet:
    key = os.environ.get(environment_variable)
    if not key:
        raise RuntimeError(f"Required encryption key is not configured: {environment_variable}")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as error:
        raise RuntimeError(f"Invalid Fernet key configuration: {environment_variable}") from error


def encrypt_contact(value: str | None) -> bytes | None:
    if value is None or value == "":
        return None
    return _cipher("PME_FIELD_ENCRYPTION_KEY").encrypt(value.encode("utf-8"))


def decrypt_contact(value: bytes | None) -> str | None:
    if value is None:
        return None
    try:
        return _cipher("PME_FIELD_ENCRYPTION_KEY").decrypt(value).decode("utf-8")
    except InvalidToken as error:
        raise RuntimeError("Contact data could not be decrypted with the configured key") from error


def mask_contact(value: str | None) -> str | None:
    if not value:
        return value
    if "@" in value:
        local, domain = value.rsplit("@", 1)
        return f"{local[:1]}***@{domain}"
    digits = "".join(character for character in value if character.isdigit())
    return f"***-***-{digits[-4:]}" if len(digits) >= 4 else "***"


def private_storage_root() -> Path:
    configured = os.environ.get("PME_PRIVATE_DOCUMENT_ROOT")
    root = Path(configured).expanduser() if configured else (
        Path.home() / ".local" / "share" / "pme_database" / "private_documents"
    )
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root = root.resolve()
    root.chmod(0o700)
    return root


def _write_encrypted(
    storage_key: str,
    plaintext: bytes,
    root: Path | None = None,
) -> None:
    root = (root or private_storage_root()).resolve()
    target = (root / storage_key).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Storage key escapes the private document root")
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    target.parent.chmod(0o700)
    encrypted = _cipher("PME_DOCUMENT_ENCRYPTION_KEY").encrypt(plaintext)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".upload-", dir=target.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(encrypted)
            output.flush()
            os.fsync(output.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            return
    finally:
        temporary.unlink(missing_ok=True)


def store_original_pdf(session: Session, source_path: str | Path) -> SourceDocument:
    path = Path(source_path)
    content = path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    existing = session.scalar(select(SourceDocument).where(SourceDocument.sha256 == digest))
    if existing is not None:
        return existing
    storage_key = f"source/{digest}.fernet"
    _write_encrypted(storage_key, content)
    document = SourceDocument(
        sha256=digest,
        storage_key=storage_key,
        original_filename=path.name,
        media_type=mimetypes.guess_type(path.name)[0] or "application/pdf",
        file_size_bytes=len(content),
    )
    session.add(document)
    session.flush()
    return document


def register_source_manifest(
    session: Session,
    source_path: str | Path,
    split_config_path: str | Path,
) -> SourceDocument:
    """Store a source PDF and record supplemental pages from a reviewed split map."""
    from src.assembly.splitter import load_split_map

    split_map = load_split_map(source_path, split_config_path)
    if not split_map.confirmed:
        raise ValueError("Source page manifest must be confirmed before registration")
    source = store_original_pdf(session, source_path)
    for packet_index, first_page, last_page in split_map.persons:
        for source_page_number in range(first_page, last_page + 1):
            existing = session.scalar(
                select(SourceDocumentPage).where(
                    SourceDocumentPage.source_document_id == source.id,
                    SourceDocumentPage.source_pdf_page_number == source_page_number,
                )
            )
            form_page = source_page_number - first_page + 1
            if existing is not None:
                if existing.page_kind != "CANDIDATE_FORM":
                    raise ValueError(
                        f"Source page {source_page_number} has a conflicting recorded assignment"
                    )
                existing.packet_index = packet_index
                existing.form_page_number = form_page
                continue
            session.add(
                SourceDocumentPage(
                    source_document_id=source.id,
                    source_pdf_page_number=source_page_number,
                    page_kind="CANDIDATE_FORM",
                    packet_index=packet_index,
                    form_page_number=form_page,
                )
            )

    for document in split_map.supplemental_documents:
        kind = str(document.get("kind") or "supplemental")[:80]
        for page_number in document.get("pages", []):
            existing = session.scalar(
                select(SourceDocumentPage).where(
                    SourceDocumentPage.source_document_id == source.id,
                    SourceDocumentPage.source_pdf_page_number == page_number,
                )
            )
            if existing is not None:
                if existing.page_kind != "SUPPLEMENTAL" or existing.supplemental_kind != kind:
                    raise ValueError(
                        f"Source page {page_number} has a conflicting recorded assignment"
                    )
                continue
            session.add(
                SourceDocumentPage(
                    source_document_id=source.id,
                    source_pdf_page_number=page_number,
                    page_kind="SUPPLEMENTAL",
                    supplemental_kind=kind,
                )
            )
    session.flush()
    return source


def store_evidence(
    session: Session,
    *,
    examination_id: int,
    content: bytes,
    asset_type: str,
    form_page_number: int | None,
    source_pdf_page_number: int | None,
    media_type: str,
    source_document_id: int | None = None,
    storage_root: Path | None = None,
) -> ExaminationDocument:
    digest = hashlib.sha256(content).hexdigest()
    existing = session.scalar(
        select(ExaminationDocument).where(
            ExaminationDocument.examination_id == examination_id,
            ExaminationDocument.asset_type == asset_type,
            ExaminationDocument.form_page_number == form_page_number,
            ExaminationDocument.sha256 == digest,
        )
    )
    if existing is not None:
        return existing
    page_key = str(form_page_number or "source")
    storage_key = f"examinations/{examination_id}/{asset_type.lower()}/page-{page_key}-{digest}.fernet"
    _write_encrypted(storage_key, content, root=storage_root)
    document = ExaminationDocument(
        examination_id=examination_id,
        source_document_id=source_document_id,
        form_page_number=form_page_number,
        source_pdf_page_number=source_pdf_page_number,
        asset_type=asset_type,
        storage_key=storage_key,
        media_type=media_type,
        file_size_bytes=len(content),
        sha256=digest,
        verification_status="UNVERIFIED",
    )
    session.add(document)
    session.flush()
    return document


def link_original_pdf(
    session: Session,
    *,
    examination_id: int,
    source_document: SourceDocument,
) -> ExaminationDocument:
    existing = session.scalar(
        select(ExaminationDocument).where(
            ExaminationDocument.examination_id == examination_id,
            ExaminationDocument.asset_type == "ORIGINAL_PDF",
            ExaminationDocument.source_document_id == source_document.id,
        )
    )
    if existing is not None:
        return existing
    link = ExaminationDocument(
        examination_id=examination_id,
        source_document_id=source_document.id,
        asset_type="ORIGINAL_PDF",
        storage_key=source_document.storage_key,
        media_type=source_document.media_type,
        file_size_bytes=source_document.file_size_bytes,
        sha256=source_document.sha256,
        verification_status="UNVERIFIED",
    )
    session.add(link)
    session.flush()
    return link


def retrieve_document(
    session: Session,
    document_id: int,
    *,
    actor: str,
    authorize: Callable[[str, int, str], bool],
) -> bytes | None:
    document = session.get(ExaminationDocument, document_id)
    if document is None:
        raise LookupError("Document not found")
    allowed = bool(authorize(actor, document.examination_id, document.asset_type))
    session.add(
        DocumentAccessEvent(
            examination_document_id=document.id,
            actor=actor,
            action="READ",
            allowed=allowed,
        )
    )
    session.flush()
    if not allowed:
        return None

    root = private_storage_root()
    storage_key = document.storage_key
    if document.source_document_id is not None and document.asset_type == "ORIGINAL_PDF":
        source = session.get(SourceDocument, document.source_document_id)
        if source is None:
            raise LookupError("Original source document not found")
        storage_key = source.storage_key
    path = (root / storage_key).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise FileNotFoundError("Private document asset is unavailable")
    try:
        return _cipher("PME_DOCUMENT_ENCRYPTION_KEY").decrypt(path.read_bytes())
    except InvalidToken as error:
        raise RuntimeError("Document could not be decrypted with the configured key") from error


def read_private_asset(
    session: Session,
    storage_key: str,
    *,
    actor: str,
    authorize: Callable[[str, int, str], bool],
) -> bytes | None:
    document = session.scalar(
        select(ExaminationDocument).where(
            ExaminationDocument.storage_key == storage_key
        )
    )
    if document is None:
        raise FileNotFoundError("Private document asset is unavailable")
    return retrieve_document(
        session,
        document.id,
        actor=actor,
        authorize=authorize,
    )
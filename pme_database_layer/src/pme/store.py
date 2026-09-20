"""Generic database handler: any validated Pydantic instance -> committed row.

One generic table stores records for ANY schema class:

    extraction_records(id, schema_name, payload JSON, created_at)

`payload` is the validated instance itself (JSON-serializable), so adding,
removing, or modifying fields in a schema class requires zero changes here —
the schema class is the single source of truth, and this store never changes
shape when it does. (A typed per-schema table can never gain columns on an
existing database — `create_all` does not alter — the payload avoids that
class of bug entirely.)
"""
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import JSON, DateTime, String, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .database import SessionLocal, engine, init_db
from .models import Base


class ExtractionRecord(Base):
    """One row per stored Pydantic instance (any schema class)."""

    __tablename__ = "extraction_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    schema_name: Mapped[str] = mapped_column(
        String(150), nullable=False, index=True
    )
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


def create_all() -> None:
    """Create all tables, including the generic extraction_records one."""
    init_db()


def save(instance: BaseModel, session: Session | None = None) -> int:
    """Commit any validated Pydantic instance; returns the new record id.

    Works for any schema class — the payload is the instance itself.
    Pass a session to share a transaction (tests, batches); otherwise one
    is opened and closed here.
    """
    if not isinstance(instance, BaseModel):
        raise TypeError(
            f"save() expects a validated Pydantic instance, got {type(instance)}"
        )
    own_session = session is None
    session = session or SessionLocal()
    try:
        row = ExtractionRecord(
            schema_name=type(instance).__name__,
            payload=instance.model_dump(mode="json"),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id
    finally:
        if own_session:
            session.close()


def get(
    schema_cls: type[BaseModel], record_id: int, session: Session | None = None
) -> BaseModel | None:
    """Read one record back as a validated instance of `schema_cls`."""
    own_session = session is None
    session = session or SessionLocal()
    try:
        row = session.get(ExtractionRecord, record_id)
        return None if row is None else schema_cls.model_validate(row.payload)
    finally:
        if own_session:
            session.close()


def all_rows(schema_cls: type[BaseModel], session: Session | None = None) -> list[BaseModel]:
    """All records of `schema_cls`, each validated back into the class."""
    own_session = session is None
    session = session or SessionLocal()
    try:
        rows = session.scalars(
            select(ExtractionRecord).where(
                ExtractionRecord.schema_name == schema_cls.__name__
            )
        )
        return [schema_cls.model_validate(row.payload) for row in rows]
    finally:
        if own_session:
            session.close()

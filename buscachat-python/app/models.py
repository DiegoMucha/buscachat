from datetime import UTC, datetime
from typing import Any

from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(UTC)


class MissingPerson(SQLModel, table=True):
    __tablename__ = "missing_people"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_missing_people_source_external"),
        Index("ix_missing_people_full_name", "full_name"),
        Index("ix_missing_people_status", "status"),
        Index("ix_missing_people_source_date", "source_date"),
    )

    id: int | None = Field(
        default=None,
        sa_column=Column(BigInteger, primary_key=True, autoincrement=True),
    )
    source: str = Field(max_length=100)
    external_id: str = Field(max_length=200)
    full_name: str = Field(max_length=500)
    status: str = Field(
        default="unknown",
        sa_column=Column(String(50), nullable=False, server_default=text("'unknown'")),
    )
    raw_status: str | None = Field(default=None, max_length=100)
    cedula_masked: str | None = Field(default=None, max_length=50)
    municipio: str | None = Field(default=None, max_length=255)
    parroquia: str | None = Field(default=None, max_length=500)
    hospital_name: str | None = Field(default=None, max_length=500)
    last_known_location: str | None = Field(default=None, max_length=1000)
    photo_url: str | None = Field(default=None, max_length=2000)
    source_date: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=text("now()")),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=text("now()")),
    )


class SourceRecord(SQLModel, table=True):
    __tablename__ = "source_records"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_source_records_source_external"),
        Index("ix_source_records_source_date", "source_date"),
    )

    id: int | None = Field(
        default=None,
        sa_column=Column(BigInteger, primary_key=True, autoincrement=True),
    )
    source: str = Field(max_length=100)
    external_id: str = Field(max_length=200)
    raw_payload: dict[str, Any] = Field(sa_column=Column(JSONB, nullable=False))
    source_date: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    synced_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=text("now()")),
    )


class SyncState(SQLModel, table=True):
    __tablename__ = "sync_state"

    source: str = Field(primary_key=True, max_length=100)
    last_success_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    last_source_date: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    last_records_seen: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default=text("0")),
    )
    last_records_upserted: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default=text("0")),
    )
    last_error: str | None = Field(default=None, max_length=2000)
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=text("now()")),
    )

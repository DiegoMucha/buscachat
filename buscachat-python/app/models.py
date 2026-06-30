from datetime import UTC, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

FACE_EMBEDDING_DIM = 512


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


class BotReport(SQLModel, table=True):
    """Missing-person report collected through the conversational bot.

    Holds the bot-specific data that does not fit in ``MissingPerson`` (age,
    description, the reporter's contact, the conversation snapshot and the face
    embedding) and links back to the ``missing_people`` row so registered people
    stay searchable through the existing endpoints.
    """

    __tablename__ = "bot_reports"
    __table_args__ = (
        Index("ix_bot_reports_chat_id", "chat_id"),
        Index("ix_bot_reports_status", "status"),
    )

    id: int | None = Field(
        default=None,
        sa_column=Column(BigInteger, primary_key=True, autoincrement=True),
    )
    missing_person_id: int | None = Field(
        default=None,
        sa_column=Column(
            BigInteger,
            ForeignKey("missing_people.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    channel: str = Field(max_length=50)
    chat_id: str = Field(max_length=200)
    sender: str | None = Field(default=None, max_length=200)
    reporter_name: str | None = Field(default=None, max_length=300)
    contact: str | None = Field(default=None, max_length=300)

    full_name: str = Field(max_length=500)
    age: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    location: str | None = Field(default=None, max_length=1000)
    photo_url: str | None = Field(default=None, max_length=2000)

    face_embedding: list[float] | None = Field(
        default=None,
        sa_column=Column(Vector(FACE_EMBEDDING_DIM), nullable=True),
    )
    status: str = Field(
        default="missing",
        sa_column=Column(String(50), nullable=False, server_default=text("'missing'")),
    )
    found_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    notified_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    conversation: Any | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
    )
    datos_raw: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=text("now()")),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=text("now()")),
    )


class WebhookEventLog(SQLModel, table=True):
    __tablename__ = "webhook_event_logs"
    __table_args__ = (Index("ix_webhook_event_logs_created_at", "created_at"),)

    id: int | None = Field(
        default=None,
        sa_column=Column(BigInteger, primary_key=True, autoincrement=True),
    )
    method: str = Field(max_length=20)
    url: str = Field(max_length=4000)
    path: str = Field(max_length=1000)
    source_ip: str | None = Field(default=None, max_length=100)
    headers: dict[str, Any] = Field(sa_column=Column(JSONB, nullable=False))
    query_params: dict[str, Any] = Field(sa_column=Column(JSONB, nullable=False))
    body: Any | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=text("now()")),
    )


class MetaWebhookMessage(SQLModel, table=True):
    __tablename__ = "meta_webhook_messages"
    __table_args__ = (
        Index("ix_meta_webhook_messages_chat_hash", "chat_hash"),
        Index("ix_meta_webhook_messages_status", "status"),
        Index("ix_meta_webhook_messages_received_at", "received_at"),
    )

    message_id: str = Field(sa_column=Column(String(255), primary_key=True))
    chat_hash: str = Field(max_length=64)
    status: str = Field(
        default="queued",
        sa_column=Column(String(50), nullable=False, server_default=text("'queued'")),
    )
    error: str | None = Field(default=None, max_length=2000)
    received_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=text("now()")),
    )
    started_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    processed_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
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

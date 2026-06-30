"""drop sync tables

Revision ID: 006_drop_sync_tables
Revises: 005_meta_webhook_messages
Create Date: 2026-06-30 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "006_drop_sync_tables"
down_revision: str | Sequence[str] | None = "005_meta_webhook_messages"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("sync_state")
    op.drop_index("ix_source_records_source_date", table_name="source_records")
    op.drop_table("source_records")


def downgrade() -> None:
    op.create_table(
        "source_records",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("external_id", sa.String(length=200), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source",
            "external_id",
            name="uq_source_records_source_external",
        ),
    )
    op.create_index("ix_source_records_source_date", "source_records", ["source_date"])

    op.create_table(
        "sync_state",
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_source_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_records_seen",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "last_records_upserted",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("last_error", sa.String(length=2000), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("source"),
    )

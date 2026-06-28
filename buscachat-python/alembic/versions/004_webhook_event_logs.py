"""webhook event logs

Revision ID: 004_webhook_event_logs
Revises: 003_face_embedding_vector
Create Date: 2026-06-28 00:00:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "004_webhook_event_logs"
down_revision: str | Sequence[str] | None = "003_face_embedding_vector"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "webhook_event_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("method", sa.String(length=20), nullable=False),
        sa.Column("url", sa.String(length=4000), nullable=False),
        sa.Column("path", sa.String(length=1000), nullable=False),
        sa.Column("source_ip", sa.String(length=100), nullable=True),
        sa.Column("headers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("query_params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("body", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_webhook_event_logs_created_at",
        "webhook_event_logs",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_webhook_event_logs_created_at", table_name="webhook_event_logs")
    op.drop_table("webhook_event_logs")

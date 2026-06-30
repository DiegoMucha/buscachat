"""drop webhook event logs

Revision ID: 007_drop_webhook_event_logs
Revises: 006_drop_sync_tables
Create Date: 2026-06-30 00:00:01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "007_drop_webhook_event_logs"
down_revision: str | Sequence[str] | None = "006_drop_sync_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_webhook_event_logs_created_at", table_name="webhook_event_logs")
    op.drop_table("webhook_event_logs")


def downgrade() -> None:
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
    op.create_index("ix_webhook_event_logs_created_at", "webhook_event_logs", ["created_at"])

"""meta webhook message dedupe

Revision ID: 005_meta_webhook_messages
Revises: 004_webhook_event_logs
Create Date: 2026-06-29 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "005_meta_webhook_messages"
down_revision: str | Sequence[str] | None = "004_webhook_event_logs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "meta_webhook_messages",
        sa.Column("message_id", sa.String(length=255), nullable=False),
        sa.Column("chat_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=50),
            server_default=sa.text("'queued'"),
            nullable=False,
        ),
        sa.Column("error", sa.String(length=2000), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("message_id"),
    )
    op.create_index(
        "ix_meta_webhook_messages_chat_hash",
        "meta_webhook_messages",
        ["chat_hash"],
    )
    op.create_index(
        "ix_meta_webhook_messages_received_at",
        "meta_webhook_messages",
        ["received_at"],
    )
    op.create_index(
        "ix_meta_webhook_messages_status",
        "meta_webhook_messages",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_meta_webhook_messages_status", table_name="meta_webhook_messages")
    op.drop_index("ix_meta_webhook_messages_received_at", table_name="meta_webhook_messages")
    op.drop_index("ix_meta_webhook_messages_chat_hash", table_name="meta_webhook_messages")
    op.drop_table("meta_webhook_messages")

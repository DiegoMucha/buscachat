"""bot_reports table

Revision ID: 002_bot_reports
Revises: 001_initial
Create Date: 2026-06-27 00:00:01
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "002_bot_reports"
down_revision: str | Sequence[str] | None = "001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bot_reports",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("missing_person_id", sa.BigInteger(), nullable=True),
        sa.Column("channel", sa.String(length=50), nullable=False),
        sa.Column("chat_id", sa.String(length=200), nullable=False),
        sa.Column("sender", sa.String(length=200), nullable=True),
        sa.Column("reporter_name", sa.String(length=300), nullable=True),
        sa.Column("contact", sa.String(length=300), nullable=True),
        sa.Column("full_name", sa.String(length=500), nullable=False),
        sa.Column("age", sa.String(length=100), nullable=True),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("location", sa.String(length=1000), nullable=True),
        sa.Column("photo_url", sa.String(length=2000), nullable=True),
        sa.Column("face_embedding", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "status",
            sa.String(length=50),
            server_default=sa.text("'missing'"),
            nullable=False,
        ),
        sa.Column("found_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("conversation", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("datos_raw", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["missing_person_id"],
            ["missing_people.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bot_reports_chat_id", "bot_reports", ["chat_id"])
    op.create_index("ix_bot_reports_status", "bot_reports", ["status"])


def downgrade() -> None:
    op.drop_index("ix_bot_reports_status", table_name="bot_reports")
    op.drop_index("ix_bot_reports_chat_id", table_name="bot_reports")
    op.drop_table("bot_reports")

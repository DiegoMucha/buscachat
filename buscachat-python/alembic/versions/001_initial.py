"""initial schema

Revision ID: 001_initial
Revises:
Create Date: 2026-06-27 00:00:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "001_initial"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "missing_people",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("external_id", sa.String(length=200), nullable=False),
        sa.Column("full_name", sa.String(length=500), nullable=False),
        sa.Column(
            "status",
            sa.String(length=50),
            server_default=sa.text("'unknown'"),
            nullable=False,
        ),
        sa.Column("raw_status", sa.String(length=100), nullable=True),
        sa.Column("cedula_masked", sa.String(length=50), nullable=True),
        sa.Column("municipio", sa.String(length=255), nullable=True),
        sa.Column("parroquia", sa.String(length=500), nullable=True),
        sa.Column("hospital_name", sa.String(length=500), nullable=True),
        sa.Column("last_known_location", sa.String(length=1000), nullable=True),
        sa.Column("photo_url", sa.String(length=2000), nullable=True),
        sa.Column("source_date", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source",
            "external_id",
            name="uq_missing_people_source_external",
        ),
    )
    op.create_index("ix_missing_people_full_name", "missing_people", ["full_name"])
    op.create_index("ix_missing_people_source_date", "missing_people", ["source_date"])
    op.create_index("ix_missing_people_status", "missing_people", ["status"])

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


def downgrade() -> None:
    op.drop_table("sync_state")
    op.drop_index("ix_source_records_source_date", table_name="source_records")
    op.drop_table("source_records")
    op.drop_index("ix_missing_people_status", table_name="missing_people")
    op.drop_index("ix_missing_people_source_date", table_name="missing_people")
    op.drop_index("ix_missing_people_full_name", table_name="missing_people")
    op.drop_table("missing_people")

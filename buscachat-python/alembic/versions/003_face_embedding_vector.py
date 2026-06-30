"""face_embedding as pgvector column

Revision ID: 003_face_embedding_vector
Revises: 002_bot_reports
Create Date: 2026-06-27 00:00:02
"""

from collections.abc import Sequence

from alembic import op

revision: str = "003_face_embedding_vector"
down_revision: str | Sequence[str] | None = "002_bot_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # A JSONB array literal (e.g. [0.1, 0.2]) is a valid vector input, so the
    # text cast converts any existing rows in place. Empty/early-stage tables
    # convert trivially.
    op.execute(
        "ALTER TABLE bot_reports ALTER COLUMN face_embedding TYPE vector(512) USING face_embedding::text::vector"
    )
    op.execute(
        "CREATE INDEX ix_bot_reports_face_embedding ON bot_reports USING hnsw (face_embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_bot_reports_face_embedding")
    op.execute("ALTER TABLE bot_reports ALTER COLUMN face_embedding TYPE jsonb USING face_embedding::text::jsonb")

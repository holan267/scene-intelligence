"""scene.scene_document + scene_embedding (Story 1.6 — describe/embed/index, AD-4/AD-5/AD-7/AD-16)

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-03
"""
from __future__ import annotations

from alembic import op
from pgvector.sqlalchemy import Vector
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

# BGE-M3 dense embedding dim — [ASSUMPTION: xác nhận lại khi chạy model thật]
SCENE_EMBEDDING_DIM = 1024


def upgrade() -> None:
    op.add_column("scene", sa.Column("scene_document", sa.Text(), nullable=True))
    op.create_table(
        "scene_embedding",
        sa.Column("scene_id", sa.String(64), sa.ForeignKey("scene.scene_id"), primary_key=True),
        sa.Column("embedding", Vector(SCENE_EMBEDDING_DIM), nullable=False),
        sa.Column("fts_text", sa.Text(), nullable=False),
        sa.Column("doc_version", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("scene_embedding")
    op.drop_column("scene", "scene_document")

"""scene_embedding: GIN functional index cho full-text search (Story 2.2, FR-8, AD-8)

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-04
"""
from __future__ import annotations

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Functional/expression index trên to_tsvector('simple', fts_text) — không phải cột generated
    # mới (không đụng shared/models.py/Base.metadata, tránh vỡ create_all trên sqlite fixture).
    # Query ở search/fts_candidates.py phải dùng ĐÚNG biểu thức + config 'simple' để Postgres
    # planner khớp được với index này. CONCURRENTLY (cùng lý do migration 0008): tránh khoá
    # exclusive chặn ghi ingest suốt thời gian build index trên bảng đang được ghi liên tục.
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_scene_embedding_fts "
            "ON scene_embedding USING gin (to_tsvector('simple', fts_text))"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_scene_embedding_fts")

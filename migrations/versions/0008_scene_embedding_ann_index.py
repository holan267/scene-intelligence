"""scene_embedding: HNSW ANN index (Story 2.1, AD-8)

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-03
"""
from __future__ import annotations

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Raw SQL (không khai báo Index() ở shared/models.py) — cột dùng chung Base.metadata với
    # sqlite fixture test (tests/conftest.py); postgresql_using="hnsw" sẽ vỡ create_all trên sqlite.
    # CONCURRENTLY (Review fix): tránh khoá exclusive chặn ghi ingest suốt thời gian build index
    # trên bảng đang được ghi liên tục; CREATE INDEX CONCURRENTLY không chạy được trong
    # transaction block nên cần autocommit_block(). IF NOT EXISTS: idempotent khớp downgrade.
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_scene_embedding_ann "
            "ON scene_embedding USING hnsw (embedding vector_cosine_ops)"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_scene_embedding_ann")

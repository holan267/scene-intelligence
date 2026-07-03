"""base schema: extension vector + bảng video, scene (Story 1.1)

Revision ID: 0001
Revises:
Create Date: 2026-07-03
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # pgvector sẵn sàng cho embedding ở story sau (AC-1)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "video",
        sa.Column("video_id", sa.String(64), primary_key=True),  # id ổn định (AD-1)
        sa.Column("framerate", sa.Float(), nullable=True),  # fps cấp Video (AD-12), set lúc detect
        sa.Column("source_key", sa.String(512), nullable=False),  # media-key (AD-23)
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "scene",
        sa.Column("scene_id", sa.String(64), primary_key=True),  # bất biến, không positional (AD-1)
        sa.Column("video_id", sa.String(64), sa.ForeignKey("video.video_id"), nullable=False),
        sa.Column("start_ms", sa.BigInteger(), nullable=False),  # timecode ms (AD-12)
        sa.Column("end_ms", sa.BigInteger(), nullable=False),
        sa.Column("search_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_scene_video_id", "scene", ["video_id"])


def downgrade() -> None:
    op.drop_index("ix_scene_video_id", table_name="scene")
    op.drop_table("scene")
    op.drop_table("video")

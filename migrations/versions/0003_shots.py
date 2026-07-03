"""shot table (Story 1.3 — Scene→Shot→Keyframe, AD-1/AD-6/AD-12)

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-03
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shot",
        sa.Column("shot_id", sa.String(64), primary_key=True),  # bất biến (AD-1)
        sa.Column("scene_id", sa.String(64), sa.ForeignKey("scene.scene_id"), nullable=False),
        sa.Column("video_id", sa.String(64), nullable=False),
        sa.Column("start_ms", sa.BigInteger(), nullable=False),  # timecode ms (AD-12)
        sa.Column("end_ms", sa.BigInteger(), nullable=False),
        sa.Column("keyframe_key", sa.String(512), nullable=True),  # media-key (AD-23)
        sa.Column("phash", sa.String(64), nullable=True),  # perceptual hash hex (AD-6)
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_shot_scene_id", "shot", ["scene_id"])
    op.create_index("ix_shot_video_id", "shot", ["video_id"])


def downgrade() -> None:
    op.drop_index("ix_shot_video_id", table_name="shot")
    op.drop_index("ix_shot_scene_id", table_name="shot")
    op.drop_table("shot")

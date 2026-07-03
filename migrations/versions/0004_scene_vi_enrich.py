"""scene transcript + ocr_text (Story 1.4 — làm giàu tiếng Việt, AD-5/AD-9)

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-03
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scene", sa.Column("transcript", sa.Text(), nullable=True))
    op.add_column("scene", sa.Column("ocr_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("scene", "ocr_text")
    op.drop_column("scene", "transcript")

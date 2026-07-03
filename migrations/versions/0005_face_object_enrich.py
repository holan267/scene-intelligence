"""person + face_appearance + scene.objects (Story 1.5 — làm giàu thị giác, AD-5/AD-11)

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-03
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "person",
        sa.Column("person_id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(256), nullable=False, unique=True),
        sa.Column("reference_embedding", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "face_appearance",
        sa.Column("appearance_id", sa.String(64), primary_key=True),
        sa.Column("scene_id", sa.String(64), sa.ForeignKey("scene.scene_id"), nullable=False, index=True),
        sa.Column("person_id", sa.String(64), sa.ForeignKey("person.person_id"), nullable=True, index=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.add_column("scene", sa.Column("objects", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("scene", "objects")
    op.drop_table("face_appearance")
    op.drop_table("person")

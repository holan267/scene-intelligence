"""ingest_task: crash-recovery + metrics columns (Story 1.7, NFR-2/NFR-8, AD-18)

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-03
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ingest_task", sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "ingest_task",
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("ingest_task", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "ix_ingest_task_status_claimed_at", "ingest_task", ["status", "claimed_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_ingest_task_status_claimed_at", table_name="ingest_task")
    op.drop_column("ingest_task", "finished_at")
    op.drop_column("ingest_task", "attempts")
    op.drop_column("ingest_task", "claimed_at")

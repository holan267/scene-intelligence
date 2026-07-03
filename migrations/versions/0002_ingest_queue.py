"""ingest queue: job + ingest_task (Story 1.2, AD-10/AD-18/AD-5)

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-03
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job",
        sa.Column("job_id", sa.String(64), primary_key=True),
        sa.Column("kind", sa.String(32), nullable=False, server_default="ingest_batch"),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "ingest_task",
        sa.Column("task_id", sa.String(64), primary_key=True),
        sa.Column("job_id", sa.String(64), sa.ForeignKey("job.job_id"), nullable=False),
        sa.Column("source_key", sa.String(512), nullable=False, unique=True),  # idempotent (AD-5)
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("reason", sa.String(256), nullable=True),
        sa.Column("video_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_ingest_task_job_id", "ingest_task", ["job_id"])
    op.create_index("ix_ingest_task_status", "ingest_task", ["status"])


def downgrade() -> None:
    op.drop_index("ix_ingest_task_status", table_name="ingest_task")
    op.drop_index("ix_ingest_task_job_id", table_name="ingest_task")
    op.drop_table("ingest_task")
    op.drop_table("job")

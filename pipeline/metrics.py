"""Metrics vận hành toàn cục (Story 1.7, NFR-8): thông lượng ingest, độ sâu hàng đợi, tỷ lệ lỗi.

Thống kê toàn kho (không gắn 1 Job/Scene cụ thể) — song song pipeline/noise.py về phạm vi tính toán.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import IngestTask


async def collect_metrics(session: AsyncSession, *, window_seconds: int) -> dict:
    """Độ sâu hàng đợi (hiện tại) + thông lượng/tỷ lệ lỗi (task done/error trong cửa sổ gần đây).

    Task 'skipped' (bị từ chối ở enqueue_batch, chưa từng qua claim) không tính vào
    throughput/error-rate — đó là lỗi tệp nguồn, không phải lỗi worker xử lý.
    """
    queue_depth = (
        await session.execute(
            select(func.count())
            .select_from(IngestTask)
            .where(IngestTask.status.in_(("queued", "claimed")))
        )
    ).scalar_one()

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
    done_count = (
        await session.execute(
            select(func.count())
            .select_from(IngestTask)
            .where(IngestTask.status == "done", IngestTask.finished_at >= cutoff)
        )
    ).scalar_one()
    errored = (
        await session.execute(
            select(func.count())
            .select_from(IngestTask)
            .where(IngestTask.status == "error", IngestTask.finished_at >= cutoff)
        )
    ).scalar_one()
    completed = done_count + errored  # mẫu số job_error_rate: mọi task đã xử lý xong (thành/bại)

    return {
        "queue_depth": queue_depth,
        # Chỉ tính task 'done' (đúng nghĩa "hoàn tất" — AC #1), KHÔNG gồm 'error'
        "ingest_throughput_per_min": done_count / (window_seconds / 60),
        "job_error_rate": (errored / completed) if completed else 0.0,
        "window_seconds": window_seconds,
    }

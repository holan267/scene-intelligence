"""Worker tiêu thụ hàng đợi (AD-18): worker CHỈ đụng task của mình, không ghi job.status.

Story 1.2: process_task chỉ **đăng ký Video** (chưa detect/enrich — Story 1.3+).
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from pipeline.ingest import claim_next_task
from shared.ids import new_video_id
from shared.models import IngestTask, Video


async def process_task(session: AsyncSession, task: IngestTask) -> None:
    """Đăng ký Video từ task; framerate để null (xác định lúc detect - Story 1.3)."""
    try:
        vid = new_video_id()
        session.add(Video(video_id=vid, framerate=None, source_key=task.source_key))
        task.video_id = vid
        task.status = "done"
        task.reason = None
    except Exception as exc:  # noqa: BLE001 - lỗi task không được làm sập worker
        task.status = "error"
        task.reason = str(exc)[:256]
    await session.flush()


async def run_once(session: AsyncSession, *, skip_locked: bool = True) -> bool:
    """Xử lý 1 task nếu có. Trả True nếu đã xử lý, False nếu hàng đợi rỗng."""
    task = await claim_next_task(session, skip_locked=skip_locked)
    if task is None:
        return False
    await process_task(session, task)
    return True

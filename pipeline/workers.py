"""Worker tiêu thụ hàng đợi (AD-18): worker CHỈ đụng task của mình, không ghi job.status.

Story 1.2: process_task đăng ký Video (idempotent). drain() nối orchestrator: xử hết
hàng đợi rồi finalize job (AD-18) — wiring runtime thật, không chỉ trong test.
Story 1.7 (NFR-2): drain() reclaim task 'claimed' quá lease (worker crash) trước khi
xử hàng đợi — task cứu được có thể claim lại ngay trong cùng lượt drain().
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pipeline.ingest import claim_next_task, finalize_job, reclaim_stale_tasks
from shared.config import get_settings
from shared.ids import new_video_id
from shared.models import IngestTask, Video


async def process_task(session: AsyncSession, task: IngestTask) -> None:
    """Đăng ký Video từ task (idempotent — không đúc Video trùng, AD-5). Lỗi -> task 'error'."""
    try:
        if task.video_id is not None:  # đã xử lý trước đó
            task.status = "done"
            task.finished_at = datetime.now(timezone.utc)
            await session.flush()
            return
        existing = (
            await session.execute(select(Video).where(Video.source_key == task.source_key))
        ).scalars().first()
        if existing is not None:
            task.video_id = existing.video_id
        else:
            vid = new_video_id()
            session.add(Video(video_id=vid, framerate=None, source_key=task.source_key))
            task.video_id = vid
        task.status = "done"
        task.reason = None
        task.finished_at = datetime.now(timezone.utc)
        await session.flush()
    except Exception as exc:  # noqa: BLE001 - lỗi task không được làm sập worker
        task.status = "error"
        task.reason = str(exc)[:256]
        task.finished_at = datetime.now(timezone.utc)
        try:
            await session.flush()
        except Exception:  # noqa: BLE001
            pass


async def run_once(session: AsyncSession, *, skip_locked: bool = True) -> bool:
    """Xử lý 1 task nếu có. True nếu đã xử lý, False nếu hàng đợi rỗng."""
    task = await claim_next_task(session, skip_locked=skip_locked)
    if task is None:
        return False
    await process_task(session, task)
    return True


async def drain(session: AsyncSession, *, skip_locked: bool = True) -> dict:
    """Xử hết task queued rồi finalize các job bị ảnh hưởng (orchestrator wiring, AD-18).

    Reclaim task 'claimed' quá lease trước (worker crash, NFR-2) — task cứu được về
    'queued' có thể bị claim lại ngay trong cùng lượt drain() này. Job của task bị
    reclaim expire (hết task_max_attempts) không bao giờ được claim lại nữa, nên
    job_id của nó phải được đưa vào tập finalize ngay từ đây (không thể chỉ dựa vào
    vòng claim bên dưới — nếu không job sẽ kẹt 'running' vĩnh viễn).
    """
    settings = get_settings()
    reclaim_result = await reclaim_stale_tasks(
        session,
        lease_seconds=settings.task_lease_seconds,
        max_attempts=settings.task_max_attempts,
        skip_locked=skip_locked,
    )
    job_ids: set[str] = set(reclaim_result["job_ids"])
    processed = 0
    while True:
        task = await claim_next_task(session, skip_locked=skip_locked)
        if task is None:
            break
        job_ids.add(task.job_id)
        await process_task(session, task)
        processed += 1
    for jid in job_ids:
        await finalize_job(session, jid)
    return {"processed": processed, "jobs_finalized": len(job_ids)}

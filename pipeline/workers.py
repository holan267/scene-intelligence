"""Worker tiêu thụ hàng đợi (AD-18): worker CHỈ đụng task của mình, không ghi job.status.

Story 1.2: process_task đăng ký Video (idempotent). drain() nối orchestrator: xử hết
hàng đợi rồi finalize job (AD-18) — wiring runtime thật, không chỉ trong test.
Story 1.7 (NFR-2): drain() reclaim task 'claimed' quá lease (worker crash) trước khi
xử hàng đợi — task cứu được có thể claim lại ngay trong cùng lượt drain().
Story 1.3 wiring: sau khi đăng ký Video, chạy detect -> persist_detection nếu CÓ
detector/extractor được truyền vào. Inject qua tham số (không tự dựng backend ở đây) để
test logic hàng đợi vẫn chạy trên sqlite mà không cần video/OpenCV; worker_main dựng
adapter thật. Không truyền => giữ nguyên hành vi cũ (chỉ đăng ký Video).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pipeline.detect import KeyframeExtractor, SceneDetector, persist_detection
from pipeline.ingest import claim_next_task, finalize_job, reclaim_stale_tasks
from shared.config import get_settings
from shared.ids import new_video_id
from shared.models import IngestTask, Video
from shared.storage import StoragePort


async def process_task(
    session: AsyncSession,
    task: IngestTask,
    *,
    detector: SceneDetector | None = None,
    extractor: KeyframeExtractor | None = None,
    storage: StoragePort | None = None,
) -> None:
    """Đăng ký Video từ task (idempotent — không đúc Video trùng, AD-5). Lỗi -> task 'error'.

    Có đủ detector+extractor+storage thì chạy luôn detect cho video vừa đăng ký.
    persist_detection upsert theo id tất định (AD-1) nên chạy lại là idempotent: re-ingest
    cùng ranh giới ánh xạ về đúng Scene/Shot cũ, không đúc row mới.
    """
    try:
        if task.video_id is None:  # chưa gắn Video -> tra theo source_key hoặc đúc mới
            existing = (
                await session.execute(select(Video).where(Video.source_key == task.source_key))
            ).scalars().first()
            if existing is not None:
                task.video_id = existing.video_id
            else:
                vid = new_video_id()
                session.add(Video(video_id=vid, framerate=None, source_key=task.source_key))
                task.video_id = vid
            await session.flush()

        # KHÔNG return sớm khi đã có video_id: task được xử lý lại nghĩa là lượt trước
        # lỗi hoặc bị reclaim giữa chừng (enqueue_batch re-queue task error/skipped mà
        # KHÔNG xoá video_id) — return sớm sẽ đánh dấu 'done' mà detect chẳng bao giờ
        # chạy. Chạy lại an toàn: Video tra theo source_key, Scene/Shot upsert theo id
        # tất định (AD-1). Task 'done' không bao giờ bị claim lại nên không có chuyện
        # decode thừa.
        if detector is not None and extractor is not None and storage is not None:
            await _detect_video(session, storage, task.video_id, task.source_key,
                                detector, extractor)

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


async def _detect_video(
    session: AsyncSession,
    storage: StoragePort,
    video_id: str,
    source_key: str,
    detector: SceneDetector,
    extractor: KeyframeExtractor,
) -> dict:
    """Decode + tách scene/shot rồi persist. Decode chạy trong thread (blocking, CPU-bound).

    Chỉ `detect()` được đẩy sang thread; `persist_detection` phải ở event loop vì nó dùng
    AsyncSession. Trích keyframe nằm trong persist_detection nên vẫn chặn loop — chấp nhận
    được với worker đơn tiến trình (MVP), tách ra khi cần chạy song song nhiều video.
    """
    detection = await asyncio.to_thread(detector.detect, source_key)
    return await persist_detection(session, storage, video_id, detection, extractor)


async def run_once(
    session: AsyncSession,
    *,
    skip_locked: bool = True,
    detector: SceneDetector | None = None,
    extractor: KeyframeExtractor | None = None,
    storage: StoragePort | None = None,
) -> bool:
    """Xử lý 1 task nếu có. True nếu đã xử lý, False nếu hàng đợi rỗng."""
    task = await claim_next_task(session, skip_locked=skip_locked)
    if task is None:
        return False
    await process_task(session, task, detector=detector, extractor=extractor, storage=storage)
    return True


async def drain(
    session: AsyncSession,
    *,
    skip_locked: bool = True,
    detector: SceneDetector | None = None,
    extractor: KeyframeExtractor | None = None,
    storage: StoragePort | None = None,
) -> dict:
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
        await process_task(session, task, detector=detector, extractor=extractor, storage=storage)
        processed += 1
    for jid in job_ids:
        await finalize_job(session, jid)
    return {"processed": processed, "jobs_finalized": len(job_ids)}

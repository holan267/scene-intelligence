"""Worker tiêu thụ hàng đợi (AD-18): worker CHỈ đụng task của mình, không ghi job.status.

Story 1.2: process_task đăng ký Video (idempotent). drain() nối orchestrator: xử hết
hàng đợi rồi finalize job (AD-18) — wiring runtime thật, không chỉ trong test.
Story 1.7 (NFR-2): drain() reclaim task 'claimed' quá lease (worker crash) trước khi
xử hàng đợi — task cứu được có thể claim lại ngay trong cùng lượt drain().
Story 1.3 wiring: sau khi đăng ký Video, chạy detect -> persist_detection nếu CÓ
detector/extractor được truyền vào. Inject qua tham số (không tự dựng backend ở đây) để
test logic hàng đợi vẫn chạy trên sqlite mà không cần video/OpenCV; worker_main dựng
adapter thật. Không truyền => giữ nguyên hành vi cũ (chỉ đăng ký Video).
Story 1.4 wiring: sau detect, chạy ASR (PhoWhisper-large) + OCR (VietOCR) cho mọi scene
của video nếu CÓ transcriber/ocr. Cùng cách tiêm: fake trong test, adapter thật ở
worker_main. Hai stage độc lập nhau — enrich chạy được cả khi tắt detect (scene đã có
từ lượt trước).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pipeline.detect import KeyframeExtractor, SceneDetector, persist_detection
from pipeline.enrich import (
    OcrReader,
    Transcriber,
    assert_vietnamese_models,
    enrich_scene_vietnamese,
)
from pipeline.ingest import claim_next_task, finalize_job, reclaim_stale_tasks
from shared.config import get_settings
from shared.ids import new_video_id
from shared.models import IngestTask, Scene, Video
from shared.storage import StoragePort


async def process_task(
    session: AsyncSession,
    task: IngestTask,
    *,
    detector: SceneDetector | None = None,
    extractor: KeyframeExtractor | None = None,
    storage: StoragePort | None = None,
    transcriber: Transcriber | None = None,
    ocr: OcrReader | None = None,
) -> None:
    """Đăng ký Video từ task (idempotent — không đúc Video trùng, AD-5). Lỗi -> task 'error'.

    Có đủ detector+extractor+storage thì chạy luôn detect cho video vừa đăng ký.
    persist_detection upsert theo id tất định (AD-1) nên chạy lại là idempotent: re-ingest
    cùng ranh giới ánh xạ về đúng Scene/Shot cũ, không đúc row mới.

    Có đủ transcriber+storage thì chạy tiếp ASR cho các scene vừa tách; `ocr` là tuỳ chọn
    (None => ASR-only). Thứ tự detect -> enrich là bắt buộc: enrich đọc Scene/Shot.keyframe_key
    do detect đúc ra.
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

        if transcriber is not None and storage is not None:
            await _enrich_video(session, storage, task.video_id, transcriber, ocr)

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


async def _enrich_video(
    session: AsyncSession,
    storage: StoragePort,
    video_id: str,
    transcriber: Transcriber,
    ocr: OcrReader | None,
) -> dict:
    """ASR + OCR cho MỌI scene của video; mỗi scene chỉ ghi cột của stage mình (AD-5).

    `ocr=None` => ASR-only, `scene.ocr_text` giữ nguyên (xem enrich_scene_vietnamese).

    Ghi đè cột riêng nên chạy lại là idempotent (Story 1.4) — task bị reclaim/retry
    enrich lại từ đầu mà không cộng dồn.

    Lời gọi model là blocking và chạy thẳng trên event loop, giống phần trích keyframe
    trong persist_detection: worker MVP đơn tiến trình không có việc khác để làm xen kẽ.
    Đẩy sang thread khi worker phải chạy song song nhiều video.

    Một scene hỏng KHÔNG chặn các scene còn lại (video tin tức có hàng trăm scene; mất
    cả video vì một lỗi ASR là quá đắt) nhưng cũng KHÔNG bị nuốt: gom lại rồi raise ở
    cuối -> process_task đánh dấu task 'error' và lượt sau chạy lại, ghi đè.
    """
    assert_vietnamese_models(transcriber, ocr)  # AD-9: fail ngay, không lặp lỗi từng scene
    scene_ids = (
        await session.execute(
            select(Scene.scene_id).where(Scene.video_id == video_id).order_by(Scene.start_ms)
        )
    ).scalars().all()

    failures: list[str] = []
    for sid in scene_ids:
        try:
            await enrich_scene_vietnamese(session, storage, sid, transcriber, ocr)
        except Exception as exc:  # noqa: BLE001 - gom lỗi, báo sau khi chạy hết scene
            failures.append(f"{sid}: {exc}")
    if failures:
        raise RuntimeError(
            f"enrich lỗi {len(failures)}/{len(scene_ids)} scene — vd {failures[0]}"
        )
    return {"scenes_enriched": len(scene_ids)}


async def run_once(
    session: AsyncSession,
    *,
    skip_locked: bool = True,
    detector: SceneDetector | None = None,
    extractor: KeyframeExtractor | None = None,
    storage: StoragePort | None = None,
    transcriber: Transcriber | None = None,
    ocr: OcrReader | None = None,
) -> bool:
    """Xử lý 1 task nếu có. True nếu đã xử lý, False nếu hàng đợi rỗng."""
    task = await claim_next_task(session, skip_locked=skip_locked)
    if task is None:
        return False
    await process_task(session, task, detector=detector, extractor=extractor, storage=storage,
                       transcriber=transcriber, ocr=ocr)
    return True


async def drain(
    session: AsyncSession,
    *,
    skip_locked: bool = True,
    detector: SceneDetector | None = None,
    extractor: KeyframeExtractor | None = None,
    storage: StoragePort | None = None,
    transcriber: Transcriber | None = None,
    ocr: OcrReader | None = None,
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
        await process_task(session, task, detector=detector, extractor=extractor,
                           storage=storage, transcriber=transcriber, ocr=ocr)
        processed += 1
    for jid in job_ids:
        await finalize_job(session, jid)
    return {"processed": processed, "jobs_finalized": len(job_ids)}

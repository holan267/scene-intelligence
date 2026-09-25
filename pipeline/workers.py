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
Story 1.6 wiring: sau enrich, chạy describe (Qwen3-VL -> scene_document) rồi embed+index
(BGE-M3 -> scene_embedding + FTS) cho mọi scene nếu CÓ describer+embedder. Đây là đường
DUY NHẤT đưa Scene sang `search_status='indexed'` (AD-17) — thiếu nó thì scene nằm mãi ở
'pending' và search trả rỗng. Cùng cách tiêm như hai stage trên; chạy được cả khi tắt
detect/enrich (làm giàu từ lượt trước).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pipeline.describe import SceneDescriber, describe_scene
from pipeline.detect import KeyframeExtractor, SceneDetector, persist_detection
from pipeline.embed_index import TextEmbedder, index_scene
from pipeline.enrich import (
    OcrReader,
    Transcriber,
    assert_vietnamese_models,
    enrich_scene_vietnamese,
)
from pipeline.ingest import claim_next_task, finalize_job, reclaim_stale_tasks
from pipeline.noise import corpus_stopwords
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
    describer: SceneDescriber | None = None,
    embedder: TextEmbedder | None = None,
) -> None:
    """Đăng ký Video từ task (idempotent — không đúc Video trùng, AD-5). Lỗi -> task 'error'.

    Có đủ detector+extractor+storage thì chạy luôn detect cho video vừa đăng ký.
    persist_detection upsert theo id tất định (AD-1) nên chạy lại là idempotent: re-ingest
    cùng ranh giới ánh xạ về đúng Scene/Shot cũ, không đúc row mới.

    Có đủ transcriber+storage thì chạy tiếp ASR cho các scene vừa tách; `ocr` là tuỳ chọn
    (None => ASR-only). Thứ tự detect -> enrich là bắt buộc: enrich đọc Scene/Shot.keyframe_key
    do detect đúc ra.

    Có đủ describer+embedder+storage thì chạy tiếp describe -> embed/index, đưa scene sang
    `search_status='indexed'` (AD-17). Thứ tự enrich -> describe cũng bắt buộc: describe đọc
    transcript/ocr_text/objects làm hints (và siết nhiễu FR-13 trên chính corpus đó).
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

        if describer is not None and embedder is not None and storage is not None:
            await _index_video(session, storage, task.video_id, describer, embedder)

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
    """ASR MỘT lần cho cả video + OCR từng scene; mỗi scene chỉ ghi cột của stage mình (AD-5).

    `ocr=None` => ASR-only, `scene.ocr_text` giữ nguyên (xem enrich_scene_vietnamese).

    ASR chạy đúng một lần (`transcriber.transcribe`) rồi cắt theo timecode từng scene:
    mỗi lần gọi model trả giá trọn một encoder pass Whisper (pad lên cửa sổ 30s), nên gọi
    theo scene là O(số scene × 30s). Lỗi ASR hỏng cả video (raise trước vòng lặp scene);
    lỗi OCR/ghi của MỘT scene không chặn các scene còn lại.

    Ghi đè cột riêng nên chạy lại là idempotent (Story 1.4) — task bị reclaim/retry
    enrich lại từ đầu mà không cộng dồn.

    Lời gọi model là blocking và chạy thẳng trên event loop, giống phần trích keyframe
    trong persist_detection: worker MVP đơn tiến trình không có việc khác để làm xen kẽ.
    Đẩy sang thread khi worker phải chạy song song nhiều video.

    Một scene hỏng KHÔNG chặn các scene còn lại (video tin tức có hàng trăm scene; mất
    cả video vì một lỗi OCR là quá đắt) nhưng cũng KHÔNG bị nuốt: gom lại rồi raise ở
    cuối -> process_task đánh dấu task 'error' và lượt sau chạy lại, ghi đè.
    """
    assert_vietnamese_models(transcriber, ocr)  # AD-9: fail ngay, không lặp lỗi từng scene
    video = await session.get(Video, video_id)
    if video is None:
        raise ValueError(f"video không tồn tại: {video_id}")
    scene_ids = (
        await session.execute(
            select(Scene.scene_id).where(Scene.video_id == video_id).order_by(Scene.start_ms)
        )
    ).scalars().all()

    # Không có scene thì khỏi transcribe: decode/encode cả video chỉ để cắt ra rỗng là vô ích.
    segments = transcriber.transcribe(video.source_key) if scene_ids else []

    failures: list[str] = []
    for sid in scene_ids:
        try:
            await enrich_scene_vietnamese(session, storage, sid, segments, ocr)
        except Exception as exc:  # noqa: BLE001 - gom lỗi, báo sau khi chạy hết scene
            failures.append(f"{sid}: {exc}")
    if failures:
        raise RuntimeError(
            f"enrich lỗi {len(failures)}/{len(scene_ids)} scene — vd {failures[0]}"
        )
    return {"scenes_enriched": len(scene_ids)}


async def _index_video(
    session: AsyncSession,
    storage: StoragePort,
    video_id: str,
    describer: SceneDescriber,
    embedder: TextEmbedder,
) -> dict:
    """describe -> embed/index cho MỌI scene của video; scene qua trọn hai bước mới 'indexed'.

    Stopword corpus (FR-13) tính MỘT lần cho cả lượt: `corpus_stopwords` quét toàn kho
    (logo/ticker lặp qua nhiều video), tính lại theo từng scene vừa tốn query vừa cho ra
    cùng một tập.

    Cổng AD-17 nằm trong `index_scene`: `search_status='indexed'` chỉ được set sau khi
    scene_embedding đã flush. Nửa chừng (describe xong, embed hỏng) để lại `scene_document`
    mới cạnh `search_status` cũ — đúng ý đồ: search không phục vụ scene chưa index đủ, lượt
    chạy sau describe+index lại từ đầu và ghi đè.

    Gọi model đồng bộ trên event loop, một scene hỏng không chặn scene còn lại nhưng cũng
    không bị nuốt — cùng cách xử lý như `_enrich_video`.
    """
    stopwords = await corpus_stopwords(session)
    scene_ids = (
        await session.execute(
            select(Scene.scene_id).where(Scene.video_id == video_id).order_by(Scene.start_ms)
        )
    ).scalars().all()

    failures: list[str] = []
    indexed = 0
    for sid in scene_ids:
        try:
            await describe_scene(session, storage, sid, describer, stopwords)
            await index_scene(session, sid, embedder)
            indexed += 1
        except Exception as exc:  # noqa: BLE001 - gom lỗi, báo sau khi chạy hết scene
            failures.append(f"{sid}: {exc}")
    if failures:
        raise RuntimeError(
            f"index lỗi {len(failures)}/{len(scene_ids)} scene — vd {failures[0]}"
        )
    return {"scenes_indexed": indexed}


async def run_once(
    session: AsyncSession,
    *,
    skip_locked: bool = True,
    detector: SceneDetector | None = None,
    extractor: KeyframeExtractor | None = None,
    storage: StoragePort | None = None,
    transcriber: Transcriber | None = None,
    ocr: OcrReader | None = None,
    describer: SceneDescriber | None = None,
    embedder: TextEmbedder | None = None,
) -> bool:
    """Xử lý 1 task nếu có. True nếu đã xử lý, False nếu hàng đợi rỗng."""
    task = await claim_next_task(session, skip_locked=skip_locked)
    if task is None:
        return False
    await process_task(session, task, detector=detector, extractor=extractor, storage=storage,
                       transcriber=transcriber, ocr=ocr, describer=describer, embedder=embedder)
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
    describer: SceneDescriber | None = None,
    embedder: TextEmbedder | None = None,
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
                           storage=storage, transcriber=transcriber, ocr=ocr,
                           describer=describer, embedder=embedder)
        processed += 1
    for jid in job_ids:
        await finalize_job(session, jid)
    return {"processed": processed, "jobs_finalized": len(job_ids)}

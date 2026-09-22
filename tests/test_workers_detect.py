"""Worker chạy detect sau khi đăng ký Video (wiring Story 1.2 + 1.3).

Detector/extractor là fake -> không cần video thật/OpenCV. Adapter thật đã có test riêng
ở tầng logic (test_detect.py); ở đây chỉ kiểm tra dây nối trong process_task.
"""
from __future__ import annotations

from sqlalchemy import func, select

from pipeline.detect import DetectedScene, DetectedShot, Detection
from pipeline.workers import process_task
from shared.models import IngestTask, Job, Scene, Shot, Video
from shared.storage import FilesystemStorage

PIX = bytes([0] * 32 + [255] * 32)


class FakeDetector:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def detect(self, media_key: str) -> Detection:
        self.calls.append(media_key)
        return Detection(
            framerate=25.0,
            scenes=(DetectedScene(0, 2000, (DetectedShot(0, 1000), DetectedShot(1000, 2000))),),
        )


class FakeExtractor:
    def extract(self, media_key: str, at_ms: int) -> tuple[bytes, bytes]:
        return f"img-{at_ms}".encode(), PIX


class BoomDetector:
    def detect(self, media_key: str) -> Detection:
        raise RuntimeError("decode hỏng")


async def _seed_task(session) -> IngestTask:
    session.add(Job(job_id="j1", kind="ingest_batch", status="running"))
    task = IngestTask(task_id="t1", job_id="j1", source_key="a.mp4", status="claimed")
    session.add(task)
    await session.flush()
    return task


async def test_process_task_runs_detect_when_ports_given(tmp_path, async_session):
    task = await _seed_task(async_session)
    detector = FakeDetector()

    await process_task(
        async_session, task,
        detector=detector, extractor=FakeExtractor(), storage=FilesystemStorage(tmp_path),
    )

    assert task.status == "done"
    assert detector.calls == ["a.mp4"]  # detect nhận media-key, không phải path tuyệt đối
    video = (await async_session.execute(select(Video))).scalars().one()
    assert video.framerate == 25.0
    assert (await async_session.execute(select(func.count()).select_from(Scene))).scalar() == 1
    assert (await async_session.execute(select(func.count()).select_from(Shot))).scalar() == 2


async def test_process_task_skips_detect_when_ports_missing(async_session):
    task = await _seed_task(async_session)

    await process_task(async_session, task)  # không truyền port -> chỉ đăng ký Video

    assert task.status == "done"
    assert (await async_session.execute(select(func.count()).select_from(Video))).scalar() == 1
    assert (await async_session.execute(select(func.count()).select_from(Scene))).scalar() == 0


async def test_detect_failure_marks_task_error_without_crashing(tmp_path, async_session):
    task = await _seed_task(async_session)

    await process_task(
        async_session, task,
        detector=BoomDetector(), extractor=FakeExtractor(), storage=FilesystemStorage(tmp_path),
    )

    assert task.status == "error"
    assert "decode hỏng" in task.reason


async def test_retry_after_detect_failure_still_detects(tmp_path, async_session):
    """Task lỗi ở bước detect giữ nguyên video_id; lượt thử lại PHẢI chạy detect lại.

    enqueue_batch re-queue task 'error' mà không xoá video_id — nếu process_task return
    sớm khi thấy video_id thì task hoá 'done' với 0 Scene, hỏng ngầm.
    """
    task = await _seed_task(async_session)
    storage = FilesystemStorage(tmp_path)

    await process_task(
        async_session, task,
        detector=BoomDetector(), extractor=FakeExtractor(), storage=storage,
    )
    assert task.status == "error" and task.video_id is not None

    task.status = "claimed"  # enqueue_batch re-queue rồi worker claim lại
    await process_task(
        async_session, task,
        detector=FakeDetector(), extractor=FakeExtractor(), storage=storage,
    )

    assert task.status == "done"
    assert (await async_session.execute(select(func.count()).select_from(Scene))).scalar() == 1
    assert (await async_session.execute(select(func.count()).select_from(Video))).scalar() == 1

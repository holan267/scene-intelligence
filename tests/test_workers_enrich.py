"""Worker chạy ASR+OCR sau detect (wiring Story 1.4 vào pipeline worker).

Transcriber/OCR là fake -> không cần PhoWhisper/VietOCR/GPU. Logic stage đã có test
riêng ở test_enrich.py; ở đây chỉ kiểm tra dây nối trong process_task/drain.
"""
from __future__ import annotations

from sqlalchemy import select

from pipeline.detect import DetectedScene, DetectedShot, Detection
from pipeline.enrich import TranscriptSegment
from pipeline.workers import drain, process_task
from shared.ids import scene_id as make_scene_id
from shared.ids import shot_id as make_shot_id
from shared.models import IngestTask, Job, Scene, Shot, Video
from shared.storage import FilesystemStorage

PIX = bytes([0] * 32 + [255] * 32)


class FakeDetector:
    def detect(self, media_key: str) -> Detection:
        return Detection(
            framerate=25.0,
            scenes=(
                DetectedScene(0, 2000, (DetectedShot(0, 2000),)),
                DetectedScene(2000, 4000, (DetectedShot(2000, 4000),)),
            ),
        )


class FakeExtractor:
    def extract(self, media_key: str, at_ms: int) -> tuple[bytes, bytes]:
        # phash đảo bit theo timecode -> hamming = 64 > ngưỡng dedupe: mỗi scene giữ
        # keyframe riêng, nếu không cả hai scene sẽ OCR chung một ảnh
        bits = at_ms // 1000
        pixels = bytes([255 if (bits >> (i % 8)) & 1 else 0 for i in range(64)])
        return f"img-{at_ms}".encode(), pixels


class FakeTranscriber:
    language = "vi"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def transcribe(self, media_key: str) -> list[TranscriptSegment]:
        self.calls.append(media_key)
        return [
            TranscriptSegment(0, 2000, "lời thoại 0"),
            TranscriptSegment(2000, 4000, "lời thoại 2000"),
        ]


class FakeOcr:
    language = "vi"

    def read_text(self, image: bytes) -> str:
        return image.decode()


class BoomOcr:
    """Hỏng ở scene đầu (keyframe img-0), chạy được ở các scene sau."""

    language = "vi"

    def __init__(self) -> None:
        self.calls = 0

    def read_text(self, image: bytes) -> str:
        self.calls += 1
        if image == b"img-0":
            raise RuntimeError("OCR hỏng")
        return image.decode()


class EnglishOnlyTranscriber:
    language = "en"

    def transcribe(self, media_key: str) -> list[TranscriptSegment]:
        return []


class BoomTranscriber:
    """ASR hỏng: theo hợp đồng mới model chạy MỘT lần/video nên hỏng cả video."""

    language = "vi"

    def __init__(self) -> None:
        self.calls = 0

    def transcribe(self, media_key: str) -> list[TranscriptSegment]:
        self.calls += 1
        raise RuntimeError("ASR hỏng")


async def _seed_task(session, source_key: str = "a.mp4") -> IngestTask:
    session.add(Job(job_id="j1", kind="ingest_batch", status="running"))
    task = IngestTask(task_id="t1", job_id="j1", source_key=source_key, status="claimed")
    session.add(task)
    await session.flush()
    return task


async def test_process_task_enriches_every_scene_after_detect(tmp_path, async_session):
    task = await _seed_task(async_session)
    transcriber = FakeTranscriber()

    await process_task(
        async_session, task,
        detector=FakeDetector(), extractor=FakeExtractor(),
        storage=FilesystemStorage(tmp_path),
        transcriber=transcriber, ocr=FakeOcr(),
    )

    assert task.status == "done"
    scenes = (
        await async_session.execute(select(Scene).order_by(Scene.start_ms))
    ).scalars().all()
    assert [s.transcript for s in scenes] == ["lời thoại 0", "lời thoại 2000"]
    assert [s.ocr_text for s in scenes] == ["img-0", "img-2000"]
    # ASR nhận media-key của video và chạy MỘT lần cho cả video, không phải mỗi scene
    assert transcriber.calls == ["a.mp4"]


async def test_process_task_skips_enrich_when_ports_missing(tmp_path, async_session):
    task = await _seed_task(async_session)

    await process_task(
        async_session, task,
        detector=FakeDetector(), extractor=FakeExtractor(),
        storage=FilesystemStorage(tmp_path),
    )

    assert task.status == "done"
    scenes = (await async_session.execute(select(Scene))).scalars().all()
    assert scenes and all(s.transcript is None and s.ocr_text is None for s in scenes)


async def test_enrich_runs_without_detect_on_scenes_from_previous_run(tmp_path, async_session):
    # Tắt DETECT_ON_INGEST nhưng bật enrich: scene đã có từ lượt trước vẫn được làm giàu
    storage = FilesystemStorage(tmp_path)
    session = async_session
    session.add(Video(video_id="v1", framerate=25.0, source_key="a.mp4"))
    sid = make_scene_id("v1", 0, 2000)
    session.add(Scene(scene_id=sid, video_id="v1", start_ms=0, end_ms=2000))
    shid = make_shot_id(sid, 0, 2000)
    kf = f"v1/keyframes/{shid}.jpg"
    storage.put(kf, b"chay-chu")
    session.add(Shot(shot_id=shid, scene_id=sid, video_id="v1", start_ms=0, end_ms=2000,
                     keyframe_key=kf, phash="0"))
    task = await _seed_task(session)

    await process_task(session, task, storage=storage,
                       transcriber=FakeTranscriber(), ocr=FakeOcr())

    assert task.status == "done"
    assert task.video_id == "v1"  # tra lại theo source_key, không đúc Video thứ hai
    scene = await session.get(Scene, sid)
    assert scene.transcript == "lời thoại 0"
    assert scene.ocr_text == "chay-chu"


async def test_ad9_guard_marks_task_error_without_touching_scenes(tmp_path, async_session):
    task = await _seed_task(async_session)

    await process_task(
        async_session, task,
        detector=FakeDetector(), extractor=FakeExtractor(),
        storage=FilesystemStorage(tmp_path),
        transcriber=EnglishOnlyTranscriber(), ocr=FakeOcr(),
    )

    assert task.status == "error"
    assert "AD-9" in task.reason
    scenes = (await async_session.execute(select(Scene))).scalars().all()
    assert all(s.transcript is None for s in scenes)  # guard chặn trước khi ghi


async def test_one_bad_scene_does_not_block_the_rest_but_fails_task(tmp_path, async_session):
    task = await _seed_task(async_session)
    transcriber = FakeTranscriber()
    ocr = BoomOcr()

    await process_task(
        async_session, task,
        detector=FakeDetector(), extractor=FakeExtractor(),
        storage=FilesystemStorage(tmp_path),
        transcriber=transcriber, ocr=ocr,
    )

    assert ocr.calls == 2  # scene sau vẫn được thử dù scene đầu hỏng
    assert transcriber.calls == ["a.mp4"]  # ASR một lần/video, không phụ thuộc lỗi OCR
    scenes = (
        await async_session.execute(select(Scene).order_by(Scene.start_ms))
    ).scalars().all()
    # scene 0 hỏng OCR trước khi kịp ghi transcript; scene 1 ghi đủ cả hai cột
    assert [s.transcript for s in scenes] == [None, "lời thoại 2000"]
    assert task.status == "error"  # lỗi không bị nuốt -> lượt sau chạy lại, ghi đè
    assert "1/2 scene" in task.reason


async def test_asr_failure_fails_whole_video(tmp_path, async_session):
    # Hợp đồng mới: model chạy MỘT lần/video nên ASR hỏng là hỏng cả video, không có
    # chuyện "scene sau vẫn chạy" như khi transcribe theo từng scene.
    task = await _seed_task(async_session)
    transcriber = BoomTranscriber()

    await process_task(
        async_session, task,
        detector=FakeDetector(), extractor=FakeExtractor(),
        storage=FilesystemStorage(tmp_path),
        transcriber=transcriber, ocr=FakeOcr(),
    )

    assert transcriber.calls == 1  # gọi đúng một lần rồi bỏ
    scenes = (await async_session.execute(select(Scene))).scalars().all()
    assert all(s.transcript is None for s in scenes)
    assert task.status == "error"
    assert "ASR hỏng" in task.reason


async def test_drain_passes_enrich_ports_through(tmp_path, async_session):
    session = async_session
    session.add(Job(job_id="j1", kind="ingest_batch", status="running"))
    session.add(IngestTask(task_id="t1", job_id="j1", source_key="a.mp4", status="queued"))
    await session.flush()

    result = await drain(
        session, skip_locked=False,
        detector=FakeDetector(), extractor=FakeExtractor(),
        storage=FilesystemStorage(tmp_path),
        transcriber=FakeTranscriber(), ocr=FakeOcr(),
    )

    assert result["processed"] == 1
    scenes = (await async_session.execute(select(Scene))).scalars().all()
    assert scenes and all(s.transcript is not None for s in scenes)


async def test_asr_only_leaves_ocr_text_untouched(tmp_path, async_session):
    # ocr=None (trọng số OCR chưa nạp được): ASR vẫn chạy, ocr_text KHÔNG bị ghi đè
    storage = FilesystemStorage(tmp_path)
    session = async_session
    session.add(Video(video_id="v1", framerate=25.0, source_key="a.mp4"))
    sid = make_scene_id("v1", 0, 2000)
    session.add(Scene(scene_id=sid, video_id="v1", start_ms=0, end_ms=2000,
                      ocr_text="CHỮ TỪ LƯỢT TRƯỚC"))
    task = await _seed_task(session)

    await process_task(session, task, storage=storage, transcriber=FakeTranscriber(), ocr=None)

    assert task.status == "done"
    scene = await session.get(Scene, sid)
    assert scene.transcript == "lời thoại 0"      # ASR có chạy
    assert scene.ocr_text == "CHỮ TỪ LƯỢT TRƯỚC"  # stage OCR không chạy => không ghi gì (AD-5)


async def test_asr_only_through_detect_path(tmp_path, async_session):
    # Đường đầy đủ detect -> enrich nhưng không có OCR port
    task = await _seed_task(async_session)

    await process_task(
        async_session, task,
        detector=FakeDetector(), extractor=FakeExtractor(),
        storage=FilesystemStorage(tmp_path),
        transcriber=FakeTranscriber(), ocr=None,
    )

    assert task.status == "done"
    scenes = (
        await async_session.execute(select(Scene).order_by(Scene.start_ms))
    ).scalars().all()
    assert [s.transcript for s in scenes] == ["lời thoại 0", "lời thoại 2000"]
    assert all(s.ocr_text is None for s in scenes)

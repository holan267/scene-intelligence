"""Worker chạy describe + embed/index sau enrich (wiring Story 1.6 vào pipeline worker).

Describer/Embedder là fake -> không cần model server Qwen3-VL/BGE-M3. Logic hai stage đã
có test riêng (test_describe.py, test_embed_index.py); ở đây chỉ kiểm tra dây nối trong
process_task/drain và cổng AD-17: scene chỉ sang 'indexed' khi qua trọn cả hai bước.
"""
from __future__ import annotations

from sqlalchemy import select

from pipeline.detect import DetectedScene, DetectedShot, Detection
from pipeline.enrich import TranscriptSegment
from pipeline.workers import drain, process_task
from shared.ids import scene_id as make_scene_id
from shared.ids import shot_id as make_shot_id
from shared.models import SCENE_EMBEDDING_DIM, IngestTask, Job, Scene, SceneEmbedding, Shot, Video
from shared.storage import FilesystemStorage


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
        bits = at_ms // 1000
        pixels = bytes([255 if (bits >> (i % 8)) & 1 else 0 for i in range(64)])
        return f"img-{at_ms}".encode(), pixels


class FakeTranscriber:
    language = "vi"

    def transcribe(self, media_key: str) -> list[TranscriptSegment]:
        return [
            TranscriptSegment(0, 2000, "lời thoại 0"),
            TranscriptSegment(2000, 4000, "lời thoại 2000"),
        ]


class FakeDescriber:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def describe(self, keyframe_images: list[bytes], hints: dict) -> str:
        self.calls.append(hints)
        return f"mô tả {hints.get('transcript')}"


class BoomDescriber:
    """Hỏng ở scene mô tả đầu tiên, chạy được ở các scene sau."""

    def __init__(self) -> None:
        self.calls = 0

    def describe(self, keyframe_images: list[bytes], hints: dict) -> str:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("Qwen3-VL hỏng")
        return "mô tả ok"


class FakeEmbedder:
    def embed(self, text: str) -> list[float]:
        return [0.1] + [0.0] * (SCENE_EMBEDDING_DIM - 1)


class BoomEmbedder:
    def embed(self, text: str) -> list[float]:
        raise RuntimeError("BGE-M3 hỏng")


async def _seed_task(session, source_key: str = "a.mp4") -> IngestTask:
    session.add(Job(job_id="j1", kind="ingest_batch", status="running"))
    task = IngestTask(task_id="t1", job_id="j1", source_key=source_key, status="claimed")
    session.add(task)
    await session.flush()
    return task


async def _seed_scene(session, storage, *, transcript: str | None = None) -> str:
    """Video + 1 Scene + 1 Shot có keyframe — đường chạy index khi tắt detect/enrich."""
    session.add(Video(video_id="v1", framerate=25.0, source_key="a.mp4"))
    sid = make_scene_id("v1", 0, 2000)
    session.add(Scene(scene_id=sid, video_id="v1", start_ms=0, end_ms=2000,
                      transcript=transcript))
    shid = make_shot_id(sid, 0, 2000)
    kf = f"v1/keyframes/{shid}.jpg"
    storage.put(kf, b"anh-keyframe")
    session.add(Shot(shot_id=shid, scene_id=sid, video_id="v1", start_ms=0, end_ms=2000,
                     keyframe_key=kf, phash="0"))
    await session.flush()
    return sid


async def test_process_task_indexes_every_scene_after_enrich(tmp_path, async_session):
    task = await _seed_task(async_session)
    describer = FakeDescriber()

    await process_task(
        async_session, task,
        detector=FakeDetector(), extractor=FakeExtractor(),
        storage=FilesystemStorage(tmp_path),
        transcriber=FakeTranscriber(), ocr=None,
        describer=describer, embedder=FakeEmbedder(),
    )

    assert task.status == "done"
    scenes = (
        await async_session.execute(select(Scene).order_by(Scene.start_ms))
    ).scalars().all()
    # AC: mọi scene qua đủ describe + index -> 'indexed' (AD-17), search thấy được
    assert [s.search_status for s in scenes] == ["indexed", "indexed"]
    assert [s.scene_document for s in scenes] == ["mô tả lời thoại 0", "mô tả lời thoại 2000"]
    # describe chạy SAU enrich: transcript của lượt này đã có mặt trong hints (FR-13)
    assert [h["transcript"] for h in describer.calls] == ["lời thoại 0", "lời thoại 2000"]
    rows = (await async_session.execute(select(SceneEmbedding))).scalars().all()
    assert len(rows) == 2


async def test_process_task_skips_index_when_ports_missing(tmp_path, async_session):
    task = await _seed_task(async_session)

    await process_task(
        async_session, task,
        detector=FakeDetector(), extractor=FakeExtractor(),
        storage=FilesystemStorage(tmp_path),
        transcriber=FakeTranscriber(), ocr=None,
    )

    assert task.status == "done"
    scenes = (await async_session.execute(select(Scene))).scalars().all()
    # Không có describer/embedder => scene đứng ở 'pending', KHÔNG lọt vào search
    assert scenes and all(s.search_status == "pending" for s in scenes)
    assert all(s.scene_document is None for s in scenes)


async def test_index_runs_without_detect_or_enrich_on_existing_scenes(tmp_path, async_session):
    # Tắt DETECT/ENRICH_ON_INGEST nhưng bật index: scene làm giàu từ lượt trước vẫn index được
    storage = FilesystemStorage(tmp_path)
    sid = await _seed_scene(async_session, storage, transcript="lời thoại cũ")
    task = await _seed_task(async_session)

    await process_task(async_session, task, storage=storage,
                       describer=FakeDescriber(), embedder=FakeEmbedder())

    assert task.status == "done"
    assert task.video_id == "v1"  # tra lại theo source_key, không đúc Video thứ hai
    scene = await async_session.get(Scene, sid)
    assert scene.search_status == "indexed"
    assert scene.scene_document == "mô tả lời thoại cũ"


async def test_embed_failure_leaves_scene_pending_and_fails_task(tmp_path, async_session):
    # AD-17: embed hỏng sau khi describe đã ghi scene_document -> KHÔNG được sang 'indexed'
    storage = FilesystemStorage(tmp_path)
    sid = await _seed_scene(async_session, storage)
    task = await _seed_task(async_session)

    await process_task(async_session, task, storage=storage,
                       describer=FakeDescriber(), embedder=BoomEmbedder())

    assert task.status == "error"
    assert "index lỗi 1/1 scene" in task.reason
    scene = await async_session.get(Scene, sid)
    assert scene.scene_document is not None  # describe đã chạy
    assert scene.search_status == "pending"  # nhưng cổng hiển thị vẫn đóng
    assert (await async_session.execute(select(SceneEmbedding))).scalars().all() == []


async def test_one_bad_scene_does_not_block_the_rest_but_fails_task(tmp_path, async_session):
    task = await _seed_task(async_session)
    describer = BoomDescriber()

    await process_task(
        async_session, task,
        detector=FakeDetector(), extractor=FakeExtractor(),
        storage=FilesystemStorage(tmp_path),
        describer=describer, embedder=FakeEmbedder(),
    )

    assert describer.calls == 2  # scene sau vẫn được thử dù scene đầu hỏng
    scenes = (
        await async_session.execute(select(Scene).order_by(Scene.start_ms))
    ).scalars().all()
    assert [s.search_status for s in scenes] == ["pending", "indexed"]
    assert task.status == "error"  # lỗi không bị nuốt -> lượt sau chạy lại, ghi đè
    assert "1/2 scene" in task.reason


async def test_drain_passes_index_ports_through(tmp_path, async_session):
    session = async_session
    session.add(Job(job_id="j1", kind="ingest_batch", status="running"))
    session.add(IngestTask(task_id="t1", job_id="j1", source_key="a.mp4", status="queued"))
    await session.flush()

    result = await drain(
        session, skip_locked=False,
        detector=FakeDetector(), extractor=FakeExtractor(),
        storage=FilesystemStorage(tmp_path),
        describer=FakeDescriber(), embedder=FakeEmbedder(),
    )

    assert result["processed"] == 1
    scenes = (await async_session.execute(select(Scene))).scalars().all()
    assert scenes and all(s.search_status == "indexed" for s in scenes)

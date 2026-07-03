from __future__ import annotations

import pytest

from pipeline.enrich import enrich_scene_vietnamese
from shared.ids import scene_id as make_scene_id
from shared.ids import shot_id as make_shot_id
from shared.models import Scene, Shot, Video
from shared.storage import FilesystemStorage


class FakeTranscriber:
    language = "vi"

    def transcribe(self, media_key: str, start_ms: int, end_ms: int) -> str:
        return "Xin chào quý vị"


class FakeOcr:
    language = "vi"

    def __init__(self, text: str = "VTV1") -> None:
        self.text = text

    def read_text(self, image: bytes) -> str:
        return self.text


class EnglishOnlyTranscriber:
    language = "en"

    def transcribe(self, media_key: str, start_ms: int, end_ms: int) -> str:
        return "hello"


async def _seed(session, storage) -> str:
    session.add(Video(video_id="v1", framerate=25.0, source_key="v1/src.mp4"))
    sid = make_scene_id("v1", 0, 2000)
    session.add(Scene(scene_id=sid, video_id="v1", start_ms=0, end_ms=2000))
    shid = make_shot_id(sid, 0, 1000)
    kf = f"v1/keyframes/{shid}.jpg"
    storage.put(kf, b"imgbytes")
    session.add(Shot(shot_id=shid, scene_id=sid, video_id="v1", start_ms=0, end_ms=1000,
                     keyframe_key=kf, phash="0"))
    await session.flush()
    return sid


async def test_enrich_writes_own_columns(tmp_path, async_session):
    # AC-1: ghi transcript + ocr_text vào cột riêng của Scene
    storage = FilesystemStorage(tmp_path)
    sid = await _seed(async_session, storage)
    await enrich_scene_vietnamese(async_session, storage, sid, FakeTranscriber(), FakeOcr())
    scene = await async_session.get(Scene, sid)
    assert scene.transcript == "Xin chào quý vị"
    assert scene.ocr_text == "VTV1"


async def test_enrich_idempotent_overwrite(tmp_path, async_session):
    # AC-3: chạy lại chỉ đè cột của mình
    storage = FilesystemStorage(tmp_path)
    sid = await _seed(async_session, storage)
    await enrich_scene_vietnamese(async_session, storage, sid, FakeTranscriber(), FakeOcr("A"))
    await enrich_scene_vietnamese(async_session, storage, sid, FakeTranscriber(), FakeOcr("B"))
    scene = await async_session.get(Scene, sid)
    assert scene.ocr_text == "B"  # lần sau đè, không cộng dồn


async def test_ad9_guard_rejects_english_only(tmp_path, async_session):
    # AC-2: cấm model English-only trong đường NL
    storage = FilesystemStorage(tmp_path)
    sid = await _seed(async_session, storage)
    with pytest.raises(ValueError):
        await enrich_scene_vietnamese(async_session, storage, sid, EnglishOnlyTranscriber(), FakeOcr())

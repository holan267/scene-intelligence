from __future__ import annotations

import pytest
from sqlalchemy import func, select

from pipeline.detect import (
    DetectedScene,
    DetectedShot,
    Detection,
    average_hash,
    hamming,
    persist_detection,
)
from shared.models import Scene, Shot, Video
from shared.storage import FilesystemStorage

PIX_A = bytes([0] * 32 + [255] * 32)
PIX_B = bytes([255] * 32 + [0] * 32)


class FakeExtractor:
    def __init__(self, pixels_by_ms: dict[int, bytes]) -> None:
        self._m = pixels_by_ms

    def extract(self, media_key: str, at_ms: int) -> tuple[bytes, bytes]:
        return f"img-{at_ms}".encode(), self._m[at_ms]


def _detection() -> Detection:
    scene = DetectedScene(0, 2000, (DetectedShot(0, 1000), DetectedShot(1000, 2000)))
    return Detection(framerate=25.0, scenes=(scene,))


async def _seed_video(session) -> None:
    session.add(Video(video_id="v1", framerate=None, source_key="v1/src.mp4"))
    await session.flush()


def test_average_hash_and_hamming():
    assert average_hash(PIX_A) == average_hash(PIX_A)
    assert hamming(average_hash(PIX_A), average_hash(PIX_A)) == 0
    assert hamming(average_hash(PIX_A), average_hash(PIX_B)) > 0


async def test_persist_creates_scene_shots_and_framerate(tmp_path, async_session):
    await _seed_video(async_session)
    storage = FilesystemStorage(tmp_path)
    res = await persist_detection(
        async_session, storage, "v1", _detection(),
        FakeExtractor({0: PIX_A, 1000: PIX_B}),
    )
    assert res["scenes"] == 1 and res["shots"] == 2
    video = await async_session.get(Video, "v1")
    assert video.framerate == 25.0  # AC-1


async def test_keyframe_dedupe_by_phash(tmp_path, async_session):
    # AC-3: hai keyframe giống nhau -> chỉ lưu 1
    await _seed_video(async_session)
    storage = FilesystemStorage(tmp_path)
    res = await persist_detection(
        async_session, storage, "v1", _detection(),
        FakeExtractor({0: PIX_A, 1000: PIX_A}),
    )
    assert res["keyframes_stored"] == 1 and res["keyframes_deduped"] == 1


async def test_keyframe_stored_via_storage_port(tmp_path, async_session):
    # AC-5: keyframe (dẫn xuất) lưu qua storage-port dưới media-key <video_id>/keyframes/
    await _seed_video(async_session)
    storage = FilesystemStorage(tmp_path)
    await persist_detection(
        async_session, storage, "v1", _detection(),
        FakeExtractor({0: PIX_A, 1000: PIX_B}),
    )
    shots = (await async_session.execute(select(Shot))).scalars().all()
    assert all(s.keyframe_key.startswith("v1/keyframes/") for s in shots)
    assert all(storage.exists(s.keyframe_key) for s in shots)


async def test_redetect_is_idempotent(tmp_path, async_session):
    # AC-4: chạy lại cùng ranh giới -> không nhân đôi
    await _seed_video(async_session)
    storage = FilesystemStorage(tmp_path)
    ext = FakeExtractor({0: PIX_A, 1000: PIX_B})
    await persist_detection(async_session, storage, "v1", _detection(), ext)
    res2 = await persist_detection(async_session, storage, "v1", _detection(), ext)
    assert res2["scenes"] == 0 and res2["shots"] == 0
    n_scene = (await async_session.execute(select(func.count()).select_from(Scene))).scalar_one()
    n_shot = (await async_session.execute(select(func.count()).select_from(Shot))).scalar_one()
    assert n_scene == 1 and n_shot == 2


async def test_reconcile_deletes_stale_scenes(tmp_path, async_session):
    # D2 patch: re-detect ranh giới khác -> xoá scene/shot cũ mồ côi
    await _seed_video(async_session)
    storage = FilesystemStorage(tmp_path)
    ext = FakeExtractor({0: PIX_A, 1000: PIX_B})
    await persist_detection(async_session, storage, "v1", _detection(), ext)
    d2 = Detection(30.0, (DetectedScene(0, 1500, (DetectedShot(0, 500),)),))
    res = await persist_detection(async_session, storage, "v1", d2, ext)
    assert res["scenes_deleted"] >= 1
    n_scene = (await async_session.execute(select(func.count()).select_from(Scene))).scalar_one()
    assert n_scene == 1  # chỉ scene mới còn lại


async def test_invalid_span_raises(tmp_path, async_session):
    # P3.3: start_ms >= end_ms bị từ chối
    await _seed_video(async_session)
    storage = FilesystemStorage(tmp_path)
    bad = Detection(25.0, (DetectedScene(1000, 500, (DetectedShot(1000, 500),)),))
    with pytest.raises(ValueError):
        await persist_detection(async_session, storage, "v1", bad, FakeExtractor({1000: PIX_A}))

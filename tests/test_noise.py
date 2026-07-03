from __future__ import annotations

import json

from pipeline.noise import corpus_stopwords
from shared.ids import scene_id as make_scene_id
from shared.models import Scene, Video


async def _seed_scene(session, *, vid: str, ocr_text: str | None, objects: list[dict] | None) -> str:
    session.add(Video(video_id=vid, framerate=25.0, source_key=f"{vid}/src.mp4"))
    sid = make_scene_id(vid, 0, 1000)
    session.add(Scene(scene_id=sid, video_id=vid, start_ms=0, end_ms=1000,
                      ocr_text=ocr_text,
                      objects=json.dumps(objects) if objects is not None else None))
    await session.flush()
    return sid


async def test_ocr_below_ratio_threshold_is_not_stopword(async_session):
    await _seed_scene(async_session, vid="v1", ocr_text="VTV1", objects=None)
    await _seed_scene(async_session, vid="v2", ocr_text="Tin tức đặc biệt", objects=None)
    await _seed_scene(async_session, vid="v3", ocr_text="Phỏng vấn độc quyền", objects=None)

    # "VTV1" chỉ ở 1/3 scene (~0.33) < 0.6 -> không phải stopword
    stopwords = await corpus_stopwords(async_session, ratio_threshold=0.6)
    assert "VTV1" not in stopwords


async def test_ocr_at_or_above_ratio_threshold_is_stopword(async_session):
    await _seed_scene(async_session, vid="v1", ocr_text="VTV1", objects=None)
    await _seed_scene(async_session, vid="v2", ocr_text="VTV1", objects=None)
    await _seed_scene(async_session, vid="v3", ocr_text="Tin tức đặc biệt", objects=None)

    # "VTV1" ở 2/3 scene (~0.67) >= 0.6 -> stopword
    stopwords = await corpus_stopwords(async_session, ratio_threshold=0.6)
    assert "VTV1" in stopwords


async def test_object_label_repeated_becomes_stopword(async_session):
    await _seed_scene(async_session, vid="v1", ocr_text=None,
                      objects=[{"label": "logo-dai", "confidence": 0.9}])
    await _seed_scene(async_session, vid="v2", ocr_text=None,
                      objects=[{"label": "logo-dai", "confidence": 0.9}])
    await _seed_scene(async_session, vid="v3", ocr_text=None,
                      objects=[{"label": "micro", "confidence": 0.8}])

    stopwords = await corpus_stopwords(async_session, ratio_threshold=0.6)
    assert "logo-dai" in stopwords
    assert "micro" not in stopwords

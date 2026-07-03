from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from pipeline.enrich_vision import (
    FaceDetection,
    ObjectDetection,
    _best_match,
    _cosine_similarity,
    enrich_scene_vision,
)
from pipeline.registry import register_person
from shared.ids import scene_id as make_scene_id
from shared.ids import shot_id as make_shot_id
from shared.models import FaceAppearance, Person, Scene, Shot, Video
from shared.storage import FilesystemStorage


class FakeFaceRecognizer:
    def __init__(self, embeddings: list[list[float]]) -> None:
        self._embeddings = embeddings

    def detect(self, image: bytes) -> list[FaceDetection]:
        return [FaceDetection(embedding=e) for e in self._embeddings]


class FakeObjectDetector:
    def __init__(self, detections: list[ObjectDetection]) -> None:
        self._detections = detections

    def detect(self, image: bytes) -> list[ObjectDetection]:
        return self._detections


class KeyedFaceRecognizer:
    """Trả detection khác nhau theo bytes ảnh keyframe — mô phỏng nhiều Shot/keyframe."""

    def __init__(self, mapping: dict[bytes, list[list[float]]]) -> None:
        self._mapping = mapping

    def detect(self, image: bytes) -> list[FaceDetection]:
        return [FaceDetection(embedding=e) for e in self._mapping.get(image, [])]


class KeyedObjectDetector:
    def __init__(self, mapping: dict[bytes, list[ObjectDetection]]) -> None:
        self._mapping = mapping

    def detect(self, image: bytes) -> list[ObjectDetection]:
        return self._mapping.get(image, [])


async def _seed(session, storage, *, with_transcript: bool = False) -> str:
    session.add(Video(video_id="v1", framerate=25.0, source_key="v1/src.mp4"))
    sid = make_scene_id("v1", 0, 2000)
    session.add(Scene(scene_id=sid, video_id="v1", start_ms=0, end_ms=2000,
                      transcript="Xin chào" if with_transcript else None,
                      ocr_text="VTV1" if with_transcript else None))
    shid = make_shot_id(sid, 0, 1000)
    kf = f"v1/keyframes/{shid}.jpg"
    storage.put(kf, b"imgbytes")
    session.add(Shot(shot_id=shid, scene_id=sid, video_id="v1", start_ms=0, end_ms=1000,
                     keyframe_key=kf, phash="0"))
    await session.flush()
    return sid


async def _seed_multi_shot(session, storage) -> str:
    session.add(Video(video_id="v2", framerate=25.0, source_key="v2/src.mp4"))
    sid = make_scene_id("v2", 0, 4000)
    session.add(Scene(scene_id=sid, video_id="v2", start_ms=0, end_ms=4000))
    shid1 = make_shot_id(sid, 0, 1000)
    kf1 = f"v2/keyframes/{shid1}.jpg"
    storage.put(kf1, b"frame1")
    session.add(Shot(shot_id=shid1, scene_id=sid, video_id="v2", start_ms=0, end_ms=1000,
                     keyframe_key=kf1, phash="0"))
    shid2 = make_shot_id(sid, 1000, 2000)
    kf2 = f"v2/keyframes/{shid2}.jpg"
    storage.put(kf2, b"frame2")
    session.add(Shot(shot_id=shid2, scene_id=sid, video_id="v2", start_ms=1000, end_ms=2000,
                     keyframe_key=kf2, phash="1"))
    await session.flush()
    return sid


def test_cosine_similarity_raises_on_dimension_mismatch():
    # [Review][Patch]: lệch chiều embedding phải raise, không zip-truncate âm thầm
    with pytest.raises(ValueError):
        _cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0])


def test_cosine_similarity_clamps_negative_to_zero():
    # [Review][Patch]: confidence/score = float 0-1 (Consistency Conventions) -> kẹp âm về 0
    assert _cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == 0.0


def test_best_match_skips_malformed_registry_entry():
    # [Review][Patch]: reference_embedding hỏng bị bỏ qua, không phá vỡ cả face-match
    bad = Person(person_id="bad", name="Bad", reference_embedding="not-json")
    good = Person(person_id="good", name="Good", reference_embedding=json.dumps([1.0, 0.0]))
    person_id, score = _best_match([1.0, 0.0], [bad, good])
    assert person_id == "good"
    assert score == 1.0


def test_best_match_empty_registry_returns_none():
    person_id, score = _best_match([1.0, 0.0], [])
    assert person_id is None
    assert score == 0.0


async def test_face_matched_above_threshold_assigns_person(tmp_path, async_session):
    # AC-1: khớp registry + confidence >= ngưỡng -> gán person_id
    storage = FilesystemStorage(tmp_path)
    sid = await _seed(async_session, storage)
    pid = await register_person(async_session, "MC A", [1.0, 0.0])

    face = FakeFaceRecognizer([[1.0, 0.0]])  # trùng khớp tuyệt đối registered person
    obj = FakeObjectDetector([])
    await enrich_scene_vision(async_session, storage, sid, face, obj, face_threshold=0.5)

    rows = (await async_session.execute(select(FaceAppearance).where(FaceAppearance.scene_id == sid))).scalars().all()
    assert len(rows) == 1
    assert rows[0].person_id == pid
    assert rows[0].confidence >= 0.5


async def test_face_below_threshold_is_unidentified(tmp_path, async_session):
    # AC-1: không khớp ai (hoặc dưới ngưỡng) -> person_id=None (AD-11, không bịa)
    storage = FilesystemStorage(tmp_path)
    sid = await _seed(async_session, storage)
    await register_person(async_session, "MC A", [1.0, 0.0])

    face = FakeFaceRecognizer([[0.0, 1.0]])  # trực giao -> similarity ~0
    obj = FakeObjectDetector([])
    await enrich_scene_vision(async_session, storage, sid, face, obj, face_threshold=0.5)

    rows = (await async_session.execute(select(FaceAppearance).where(FaceAppearance.scene_id == sid))).scalars().all()
    assert len(rows) == 1
    assert rows[0].person_id is None


async def test_object_written_with_confidence(tmp_path, async_session):
    # AC-2: đối tượng lưu kèm confidence
    storage = FilesystemStorage(tmp_path)
    sid = await _seed(async_session, storage)

    face = FakeFaceRecognizer([])
    obj = FakeObjectDetector([ObjectDetection(label="micro", confidence=0.9)])
    await enrich_scene_vision(async_session, storage, sid, face, obj, face_threshold=0.5)

    scene = await async_session.get(Scene, sid)
    objects = json.loads(scene.objects)
    assert objects == [{"label": "micro", "confidence": 0.9}]


async def test_rerun_idempotent_no_duplicate_and_no_cross_stage_write(tmp_path, async_session):
    # AC-4: chạy lại không nhân đôi face_appearance, không đụng transcript/ocr_text
    storage = FilesystemStorage(tmp_path)
    sid = await _seed(async_session, storage, with_transcript=True)
    pid = await register_person(async_session, "MC A", [1.0, 0.0])

    face = FakeFaceRecognizer([[1.0, 0.0]])
    obj = FakeObjectDetector([ObjectDetection(label="micro", confidence=0.9)])
    await enrich_scene_vision(async_session, storage, sid, face, obj, face_threshold=0.5)
    await enrich_scene_vision(async_session, storage, sid, face, obj, face_threshold=0.5)

    rows = (await async_session.execute(select(FaceAppearance).where(FaceAppearance.scene_id == sid))).scalars().all()
    assert len(rows) == 1  # không nhân đôi
    assert rows[0].person_id == pid

    scene = await async_session.get(Scene, sid)
    assert scene.transcript == "Xin chào"  # AD-5: stage khác không bị đụng
    assert scene.ocr_text == "VTV1"


async def test_face_score_equal_threshold_is_assigned(tmp_path, async_session):
    # AC-1: ranh giới >= ngưỡng (không phải >) -> score == threshold vẫn được gán
    storage = FilesystemStorage(tmp_path)
    sid = await _seed(async_session, storage)
    pid = await register_person(async_session, "MC A", [1.0, 0.0])

    face = FakeFaceRecognizer([[1.0, 0.0]])  # cosine similarity = 1.0
    obj = FakeObjectDetector([])
    await enrich_scene_vision(async_session, storage, sid, face, obj, face_threshold=1.0)

    rows = (await async_session.execute(select(FaceAppearance).where(FaceAppearance.scene_id == sid))).scalars().all()
    assert rows[0].person_id == pid


async def test_face_no_registered_persons_is_unidentified(tmp_path, async_session):
    # AC-1: registry rỗng -> không có ai để khớp -> person_id=None, confidence=0.0
    storage = FilesystemStorage(tmp_path)
    sid = await _seed(async_session, storage)

    face = FakeFaceRecognizer([[1.0, 0.0]])
    obj = FakeObjectDetector([])
    await enrich_scene_vision(async_session, storage, sid, face, obj, face_threshold=0.5)

    rows = (await async_session.execute(select(FaceAppearance).where(FaceAppearance.scene_id == sid))).scalars().all()
    assert len(rows) == 1
    assert rows[0].person_id is None
    assert rows[0].confidence == 0.0


async def test_face_tie_break_is_deterministic_across_reruns(tmp_path, async_session):
    # [Review][Patch]: order_by ổn định -> tie giữa nhiều person cùng similarity cho
    # kết quả LẶP LẠI được qua các lần chạy (trước đây phụ thuộc thứ tự DB không đảm bảo)
    storage = FilesystemStorage(tmp_path)
    sid = await _seed(async_session, storage)
    await register_person(async_session, "MC A", [1.0, 0.0])
    await register_person(async_session, "MC B", [1.0, 0.0])  # cùng embedding -> cùng similarity

    face = FakeFaceRecognizer([[1.0, 0.0]])
    obj = FakeObjectDetector([])

    await enrich_scene_vision(async_session, storage, sid, face, obj, face_threshold=0.5)
    winner = (
        await async_session.execute(select(FaceAppearance).where(FaceAppearance.scene_id == sid))
    ).scalar_one().person_id

    await enrich_scene_vision(async_session, storage, sid, face, obj, face_threshold=0.5)
    rerun_winner = (
        await async_session.execute(select(FaceAppearance).where(FaceAppearance.scene_id == sid))
    ).scalar_one().person_id

    assert rerun_winner == winner  # cùng dữ liệu -> cùng kết quả mọi lần chạy


async def test_multi_shot_aggregates_faces_and_objects(tmp_path, async_session):
    # Task 3: duyệt nhiều Shot/keyframe của cùng Scene, gộp kết quả face + object
    storage = FilesystemStorage(tmp_path)
    sid = await _seed_multi_shot(async_session, storage)

    face = KeyedFaceRecognizer({b"frame1": [[1.0, 0.0]], b"frame2": [[0.0, 1.0]]})
    obj = KeyedObjectDetector({
        b"frame1": [ObjectDetection(label="micro", confidence=0.9)],
        b"frame2": [ObjectDetection(label="bang-ron", confidence=0.7)],
    })
    await enrich_scene_vision(async_session, storage, sid, face, obj, face_threshold=0.9)

    rows = (await async_session.execute(select(FaceAppearance).where(FaceAppearance.scene_id == sid))).scalars().all()
    assert len(rows) == 2  # 1 face/keyframe, cả 2 keyframe được duyệt

    scene = await async_session.get(Scene, sid)
    objects = json.loads(scene.objects)
    assert {o["label"] for o in objects} == {"micro", "bang-ron"}
    assert len(objects) == 2

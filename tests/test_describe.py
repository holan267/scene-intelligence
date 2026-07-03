from __future__ import annotations

import json

from pipeline.describe import build_hints, describe_scene
from shared.ids import scene_id as make_scene_id
from shared.ids import shot_id as make_shot_id
from shared.models import FaceAppearance, Person, Scene, Shot, Video
from shared.storage import FilesystemStorage


class FakeDescriber:
    def __init__(self, text: str = "Bản tin thời sự") -> None:
        self._text = text
        self.calls: list[tuple[list[bytes], dict]] = []

    def describe(self, keyframe_images: list[bytes], hints: dict) -> str:
        self.calls.append((keyframe_images, hints))
        return self._text


def _make_scene(*, ocr_text=None, objects=None) -> Scene:
    return Scene(scene_id="s1", video_id="v1", start_ms=0, end_ms=1000,
                transcript="Xin chào quý vị", ocr_text=ocr_text,
                objects=json.dumps(objects) if objects is not None else None)


def test_build_hints_includes_transcript():
    scene = _make_scene()
    hints = build_hints(scene, [], {}, set())
    assert hints["transcript"] == "Xin chào quý vị"


def test_build_hints_excludes_ocr_in_stopwords():
    scene = _make_scene(ocr_text="VTV1")
    hints = build_hints(scene, [], {}, {"VTV1"})
    assert hints["ocr_text"] is None


def test_build_hints_includes_ocr_not_in_stopwords():
    scene = _make_scene(ocr_text="Bão số 3")
    hints = build_hints(scene, [], {}, {"VTV1"})
    assert hints["ocr_text"] == "Bão số 3"


def test_build_hints_filters_objects_by_confidence_and_stopwords():
    scene = _make_scene(objects=[
        {"label": "micro", "confidence": 0.9},
        {"label": "ban-do", "confidence": 0.2},  # dưới ngưỡng
        {"label": "logo-dai", "confidence": 0.9},  # trong stopword
    ])
    hints = build_hints(scene, [], {}, {"logo-dai"}, confidence_threshold=0.5)
    assert hints["objects"] == ["micro"]


def test_build_hints_includes_only_identified_faces():
    appearances = [
        FaceAppearance(appearance_id="a1", scene_id="s1", person_id="p1", confidence=0.9),
        FaceAppearance(appearance_id="a2", scene_id="s1", person_id=None, confidence=0.1),
    ]
    persons = {"p1": Person(person_id="p1", name="MC A", reference_embedding="[]")}
    scene = _make_scene()
    hints = build_hints(scene, appearances, persons, set())
    assert hints["faces"] == ["MC A"]


def test_build_hints_dedupes_repeated_face_across_shots():
    # [Review][Patch]: cùng người xuất hiện nhiều Shot -> chỉ liệt kê 1 lần (FR-13)
    appearances = [
        FaceAppearance(appearance_id="a1", scene_id="s1", person_id="p1", confidence=0.9),
        FaceAppearance(appearance_id="a2", scene_id="s1", person_id="p1", confidence=0.8),
    ]
    persons = {"p1": Person(person_id="p1", name="MC A", reference_embedding="[]")}
    scene = _make_scene()
    hints = build_hints(scene, appearances, persons, set())
    assert hints["faces"] == ["MC A"]


def test_build_hints_ignores_malformed_objects_json():
    # [Review][Patch]: JSON hỏng trong scene.objects không được crash cả build_hints
    scene = Scene(scene_id="s1", video_id="v1", start_ms=0, end_ms=1000,
                 transcript="Xin chào", objects="không phải json hợp lệ")
    hints = build_hints(scene, [], {}, set())
    assert hints["objects"] == []


def test_build_hints_skips_object_missing_keys():
    scene = _make_scene(objects=[{"label": "micro"}, {"confidence": 0.9}, "not-a-dict"])
    hints = build_hints(scene, [], {}, set())
    assert hints["objects"] == []


async def _seed(session, storage) -> str:
    session.add(Video(video_id="v1", framerate=25.0, source_key="v1/src.mp4"))
    sid = make_scene_id("v1", 0, 2000)
    session.add(Scene(scene_id=sid, video_id="v1", start_ms=0, end_ms=2000,
                      transcript="Xin chào", ocr_text="Bão số 3",
                      objects=json.dumps([{"label": "micro", "confidence": 0.9}])))
    shid = make_shot_id(sid, 0, 1000)
    kf = f"v1/keyframes/{shid}.jpg"
    storage.put(kf, b"imgbytes")
    session.add(Shot(shot_id=shid, scene_id=sid, video_id="v1", start_ms=0, end_ms=1000,
                     keyframe_key=kf, phash="0"))
    await session.flush()
    return sid


async def test_describe_scene_writes_scene_document_only(tmp_path, async_session):
    # AC-1: sinh scene_document, cột riêng (AD-5) — không đụng transcript/ocr_text/objects
    storage = FilesystemStorage(tmp_path)
    sid = await _seed(async_session, storage)
    describer = FakeDescriber("Phóng viên đưa tin về bão số 3")

    result = await describe_scene(async_session, storage, sid, describer, corpus_stopwords=set())

    scene = await async_session.get(Scene, sid)
    assert scene.scene_document == "Phóng viên đưa tin về bão số 3"
    assert scene.transcript == "Xin chào"
    assert scene.ocr_text == "Bão số 3"
    assert result["scene_id"] == sid

    # keyframe ảnh đã lấy qua storage-port và đưa cho describer
    images, hints = describer.calls[0]
    assert images == [b"imgbytes"]
    assert hints["transcript"] == "Xin chào"


async def test_describe_scene_orders_keyframes_by_shot_start_ms(tmp_path, async_session):
    # [Review][Patch]: thứ tự keyframe ổn định theo start_ms (AC-6 rebuild-equivalence)
    storage = FilesystemStorage(tmp_path)
    session, storage_ = async_session, storage
    session.add(Video(video_id="v1", framerate=25.0, source_key="v1/src.mp4"))
    sid = make_scene_id("v1", 0, 3000)
    session.add(Scene(scene_id=sid, video_id="v1", start_ms=0, end_ms=3000))

    # cố tình chèn Shot sau (start_ms lớn hơn) trước Shot đầu, để kiểm tra ORDER BY không phụ thuộc thứ tự insert
    shid2 = make_shot_id(sid, 1000, 2000)
    kf2 = f"v1/keyframes/{shid2}.jpg"
    storage_.put(kf2, b"frame-second")
    session.add(Shot(shot_id=shid2, scene_id=sid, video_id="v1", start_ms=1000, end_ms=2000,
                     keyframe_key=kf2, phash="1"))

    shid1 = make_shot_id(sid, 0, 1000)
    kf1 = f"v1/keyframes/{shid1}.jpg"
    storage_.put(kf1, b"frame-first")
    session.add(Shot(shot_id=shid1, scene_id=sid, video_id="v1", start_ms=0, end_ms=1000,
                     keyframe_key=kf1, phash="0"))
    await session.flush()

    describer = FakeDescriber()
    await describe_scene(session, storage_, sid, describer, corpus_stopwords=set())

    images, _ = describer.calls[0]
    assert images == [b"frame-first", b"frame-second"]

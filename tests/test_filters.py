from __future__ import annotations

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from shared.filters import SceneFilters, apply_scene_filters
from shared.models import FaceAppearance, Person, Scene, Video


def test_scene_filters_defaults_all_none():
    f = SceneFilters()
    assert f.min_duration_ms is None
    assert f.max_duration_ms is None
    assert f.has_person is None
    assert f.person_id is None


def test_scene_filters_rejects_max_less_than_min():
    with pytest.raises(ValidationError):
        SceneFilters(min_duration_ms=2000, max_duration_ms=1000)


def test_scene_filters_accepts_max_equal_min():
    f = SceneFilters(min_duration_ms=1000, max_duration_ms=1000)
    assert f.min_duration_ms == f.max_duration_ms == 1000


@pytest.mark.parametrize("field", ["min_duration_ms", "max_duration_ms"])
def test_scene_filters_rejects_negative_duration(field):
    with pytest.raises(ValidationError):
        SceneFilters(**{field: -1})


def test_scene_filters_rejects_unknown_field():
    # Review fix: extra="forbid" — client gửi field không tồn tại (vd chính
    # shot_size/has_logo mà story cố tình chưa hỗ trợ) phải báo lỗi, không được
    # âm thầm bỏ qua (client sẽ tưởng filter có tác dụng).
    with pytest.raises(ValidationError):
        SceneFilters(shot_size="close")


def test_scene_filters_rejects_has_person_false_with_person_id():
    # Review fix: has_person=False (không ai) + person_id=<id> (đúng người đó) tự
    # mâu thuẫn, luôn ra rỗng — chặn ngay ở schema thay vì âm thầm trả kết quả rỗng.
    with pytest.raises(ValidationError):
        SceneFilters(has_person=False, person_id="mc-lan")


def test_scene_filters_accepts_has_person_true_with_person_id():
    f = SceneFilters(has_person=True, person_id="mc-lan")
    assert f.has_person is True
    assert f.person_id == "mc-lan"


def test_scene_filters_rejects_empty_person_id():
    # Review fix: chuỗi rỗng lọt qua sẽ tạo "không tìm thấy" âm thầm giống hệt gõ
    # sai id — chặn ngay ở schema.
    with pytest.raises(ValidationError):
        SceneFilters(person_id="")


async def _seed(session):
    """Video + 4 Scene (độ dài khác nhau) + Person + face_appearance đa dạng.

    - s_short: 500ms, không có face nào.
    - s_medium: 2000ms, có face "không xác định" (person_id=None).
    - s_long: 10000ms, có face khớp person đã đăng ký ("mc-lan").
    - s_long_unknown: 10000ms, có face "không xác định" (person_id=None) — cùng
      độ dài với s_long nhưng KHÔNG khớp person_id cụ thể (kiểm tra AND đúng nghĩa).
    """
    session.add(Video(video_id="v1", source_key="v1.mp4"))
    scenes = {
        "s_short": (0, 500),
        "s_medium": (0, 2000),
        "s_long": (0, 10000),
        "s_long_unknown": (0, 10000),
    }
    for scene_id, (start_ms, end_ms) in scenes.items():
        session.add(Scene(scene_id=scene_id, video_id="v1", start_ms=start_ms, end_ms=end_ms))
    session.add(Person(person_id="mc-lan", name="MC Lan", reference_embedding="[]"))
    session.add(
        FaceAppearance(
            appearance_id="fa1", scene_id="s_medium", person_id=None, confidence=0.4
        )
    )
    session.add(
        FaceAppearance(
            appearance_id="fa2", scene_id="s_long", person_id="mc-lan", confidence=0.95
        )
    )
    session.add(
        FaceAppearance(
            appearance_id="fa3", scene_id="s_long_unknown", person_id=None, confidence=0.5
        )
    )
    await session.commit()


async def _scene_ids(session, stmt):
    rows = (await session.execute(stmt)).scalars().all()
    return set(rows)


async def test_apply_scene_filters_none_is_noop(async_session):
    await _seed(async_session)
    stmt = select(Scene.scene_id)
    assert await _scene_ids(async_session, apply_scene_filters(stmt, None)) == {
        "s_short",
        "s_medium",
        "s_long",
        "s_long_unknown",
    }


async def test_apply_scene_filters_min_duration(async_session):
    await _seed(async_session)
    stmt = apply_scene_filters(select(Scene.scene_id), SceneFilters(min_duration_ms=2000))
    assert await _scene_ids(async_session, stmt) == {"s_medium", "s_long", "s_long_unknown"}


async def test_apply_scene_filters_max_duration(async_session):
    await _seed(async_session)
    stmt = apply_scene_filters(select(Scene.scene_id), SceneFilters(max_duration_ms=2000))
    assert await _scene_ids(async_session, stmt) == {"s_short", "s_medium"}


async def test_apply_scene_filters_duration_range_both_bounds(async_session):
    await _seed(async_session)
    stmt = apply_scene_filters(
        select(Scene.scene_id),
        SceneFilters(min_duration_ms=1000, max_duration_ms=5000),
    )
    assert await _scene_ids(async_session, stmt) == {"s_medium"}


async def test_apply_scene_filters_has_person_true(async_session):
    await _seed(async_session)
    stmt = apply_scene_filters(select(Scene.scene_id), SceneFilters(has_person=True))
    assert await _scene_ids(async_session, stmt) == {"s_medium", "s_long", "s_long_unknown"}


async def test_apply_scene_filters_has_person_false(async_session):
    await _seed(async_session)
    stmt = apply_scene_filters(select(Scene.scene_id), SceneFilters(has_person=False))
    assert await _scene_ids(async_session, stmt) == {"s_short"}


async def test_apply_scene_filters_person_id_specific(async_session):
    await _seed(async_session)
    stmt = apply_scene_filters(select(Scene.scene_id), SceneFilters(person_id="mc-lan"))
    assert await _scene_ids(async_session, stmt) == {"s_long"}
    # face "không xác định" (person_id=None) không khớp dù có mặt người
    assert "s_medium" not in await _scene_ids(async_session, stmt)
    assert "s_long_unknown" not in await _scene_ids(async_session, stmt)


async def test_apply_scene_filters_person_id_nonexistent_returns_empty(async_session):
    # Review fix: person_id trỏ tới Person không tồn tại trong bảng person -> EXISTS
    # trả False cho mọi Scene, kết quả rỗng, KHÔNG crash (không phải bug).
    await _seed(async_session)
    stmt = apply_scene_filters(select(Scene.scene_id), SceneFilters(person_id="khong-ton-tai"))
    assert await _scene_ids(async_session, stmt) == set()


async def test_apply_scene_filters_combines_with_and_not_or(async_session):
    await _seed(async_session)
    # min_duration_ms=2000 khớp {s_medium, s_long, s_long_unknown}; has_person=True cũng khớp
    # cùng tập -> giao = như nhau. Thêm case phân biệt AND thật: max_duration_ms loại s_long*.
    stmt = apply_scene_filters(
        select(Scene.scene_id),
        SceneFilters(max_duration_ms=2000, has_person=True),
    )
    assert await _scene_ids(async_session, stmt) == {"s_medium"}

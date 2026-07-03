from __future__ import annotations

import pytest

from shared.ids import ms_to_smpte, new_video_id, scene_id


def test_scene_id_deterministic_immutable():
    # AD-1: cùng (video, start, end) -> cùng id (re-detect ánh xạ về scene cũ)
    assert scene_id("vid1", 1000, 2000) == scene_id("vid1", 1000, 2000)


def test_scene_id_differs_by_boundary():
    assert scene_id("vid1", 0, 1000) != scene_id("vid1", 0, 2000)
    assert scene_id("vid1", 0, 1000) != scene_id("vid2", 0, 1000)


def test_scene_id_requires_int_ms():
    # AD-12: timecode phải là int millisecond
    with pytest.raises(TypeError):
        scene_id("vid1", 1.0, 2000)  # type: ignore[arg-type]


def test_ms_to_smpte():
    assert ms_to_smpte(0, 25) == "00:00:00:00"
    assert ms_to_smpte(3_661_000, 25) == "01:01:01:00"


def test_new_video_id_unique():
    assert new_video_id() != new_video_id()

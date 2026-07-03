"""Định danh & timecode bất biến.

- scene_id / video_id: id ỔN ĐỊNH (AD-1). scene_id KHÔNG dùng số thứ tự vị trí;
  sinh bằng UUID5 tất định từ (video_id, start_ms, end_ms) để re-detect ánh xạ về
  đúng scene cũ khi ranh giới không đổi.
- Timecode: millisecond integer là canonical (AD-12); SMPTE chỉ để hiển thị.
"""
from __future__ import annotations

import uuid

# Namespace cố định cho id tất định (không đổi -> id ổn định qua re-ingest).
_SCENE_NS = uuid.UUID("6f6b1e7a-6c2a-4b8e-9d3a-2c1b0a9f8e7d")
_SHOT_NS = uuid.UUID("b2d4a1c8-3e5f-4a7b-8c9d-0e1f2a3b4c5d")


def new_id() -> str:
    """Sinh id ngẫu nhiên (job/task…)."""
    return uuid.uuid4().hex


def new_video_id() -> str:
    """Sinh video_id ngẫu nhiên, ổn định suốt đời Video."""
    return uuid.uuid4().hex


def scene_id(video_id: str, start_ms: int, end_ms: int) -> str:
    """scene_id tất định & bất biến từ (video_id, start_ms, end_ms) — AD-1.

    Cùng bộ tham số -> cùng id (re-detect ánh xạ về scene cũ, không re-mint).
    """
    if not isinstance(start_ms, int) or not isinstance(end_ms, int):
        raise TypeError("start_ms/end_ms phải là int millisecond (AD-12)")
    return uuid.uuid5(_SCENE_NS, f"{video_id}:{start_ms}:{end_ms}").hex


def shot_id(scene_id_value: str, start_ms: int, end_ms: int) -> str:
    """shot_id tất định & bất biến từ (scene_id, start_ms, end_ms) — AD-1."""
    if not isinstance(start_ms, int) or not isinstance(end_ms, int):
        raise TypeError("start_ms/end_ms phải là int millisecond (AD-12)")
    return uuid.uuid5(_SHOT_NS, f"{scene_id_value}:{start_ms}:{end_ms}").hex


def ms_to_smpte(ms: int, fps: float) -> str:
    """Đổi millisecond -> SMPTE 'HH:MM:SS:FF' để hiển thị (AD-12)."""
    if not isinstance(ms, int) or ms < 0:
        raise ValueError("ms phải là int không âm")
    if fps <= 0:
        raise ValueError("fps phải > 0")
    total_seconds, rem_ms = divmod(ms, 1000)
    hours, rem = divmod(total_seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    frames = int(rem_ms / 1000 * fps)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frames:02d}"

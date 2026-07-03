"""Làm giàu tiếng Việt: ASR + OCR (Story 1.4 — FR-3, AD-5, AD-9).

Ghi vào cột riêng của Scene (`transcript`, `ocr_text`) — không đụng field stage khác (AD-5).
Guard AD-9: chỉ nhận model hỗ trợ tiếng Việt (cấm English-only trong đường NL).
Model thật ở enrich_backends.py (guarded).
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import Scene, Shot, Video
from shared.storage import StoragePort

_VI_OK = {"vi", "multilingual"}


@runtime_checkable
class Transcriber(Protocol):
    language: str

    def transcribe(self, media_key: str, start_ms: int, end_ms: int) -> str: ...


@runtime_checkable
class OcrReader(Protocol):
    language: str

    def read_text(self, image: bytes) -> str: ...


def _assert_vietnamese(model: object, role: str) -> None:
    lang = getattr(model, "language", None)
    if lang not in _VI_OK:
        raise ValueError(f"{role} không hỗ trợ tiếng Việt (language={lang!r}) — vi phạm AD-9")


async def enrich_scene_vietnamese(
    session: AsyncSession,
    storage: StoragePort,
    scene_id: str,
    transcriber: Transcriber,
    ocr: OcrReader,
) -> dict:
    """ASR trên audio scene + OCR trên keyframe các shot; ghi cột riêng (idempotent overwrite)."""
    _assert_vietnamese(transcriber, "ASR")  # AD-9
    _assert_vietnamese(ocr, "OCR")

    scene = await session.get(Scene, scene_id)
    if scene is None:
        raise ValueError(f"scene không tồn tại: {scene_id}")
    video = await session.get(Video, scene.video_id)
    if video is None:
        raise ValueError(f"video không tồn tại: {scene.video_id}")

    transcript = transcriber.transcribe(video.source_key, scene.start_ms, scene.end_ms)

    shots = (
        await session.execute(select(Shot).where(Shot.scene_id == scene_id))
    ).scalars().all()
    texts: list[str] = []
    seen_keys: set[str] = set()
    for sh in shots:  # OCR trên keyframe (AD-6), lấy ảnh qua storage-port (AD-23)
        if not sh.keyframe_key or sh.keyframe_key in seen_keys:
            continue
        seen_keys.add(sh.keyframe_key)
        text = ocr.read_text(storage.get(sh.keyframe_key)).strip()
        if text:
            texts.append(text)

    scene.transcript = transcript  # cột riêng (AD-5)
    scene.ocr_text = "\n".join(texts) if texts else None
    await session.flush()
    return {"scene_id": scene_id, "transcript_len": len(transcript), "ocr_blocks": len(texts)}

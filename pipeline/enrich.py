"""Làm giàu tiếng Việt: ASR + OCR (Story 1.4 — FR-3, AD-5, AD-9).

Ghi vào cột riêng của Scene (`transcript`, `ocr_text`) — không đụng field stage khác (AD-5).
Guard AD-9: chỉ nhận model hỗ trợ tiếng Việt (cấm English-only trong đường NL).
Model thật ở enrich_backends.py (guarded).

ASR chạy **MỘT lần cho cả video** rồi cắt theo timecode từng scene
(`transcript_for_range`). Mỗi lần gọi `WhisperModel.transcribe()` chạy trọn một encoder
pass Whisper (audio luôn được pad lên cửa sổ 30s), nên gọi theo từng scene khiến chi phí
là O(số scene × 30s) bất kể scene dài hay ngắn — video 38s / 21 scene tốn ~300s thay vì
~15s nếu transcribe một lần.

Adapter PhoWhisper phát segment ở mức TỪ (`word_timestamps=True`) chứ không phải mức câu:
timestamp mức câu rất thô (đo được một câu trải 20s), cắt theo nó thì scene ngắn sẽ rỗng
hoặc nuốt cả câu dài vào một scene. Mức từ cho phép cắt đúng lời thoại theo ranh giới scene.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import Scene, Shot
from shared.storage import StoragePort

_VI_OK = {"vi", "multilingual"}


@dataclass(frozen=True)
class TranscriptSegment:
    """Một mảnh lời thoại có mốc thời gian (ms từ đầu video).

    Adapter PhoWhisper phát ở mức TỪ; `text` đã strip và được nối bằng khoảng trắng trong
    `transcript_for_range` (đúng cho tiếng Việt — AD-9 chỉ nhận model tiếng Việt)."""

    start_ms: int
    end_ms: int
    text: str


@runtime_checkable
class Transcriber(Protocol):
    language: str

    def transcribe(self, media_key: str) -> list[TranscriptSegment]: ...


@runtime_checkable
class OcrReader(Protocol):
    language: str

    def read_text(self, image: bytes) -> str: ...


def transcript_for_range(
    segments: list[TranscriptSegment], start_ms: int, end_ms: int
) -> str:
    """Ghép lời thoại của các mảnh rơi vào nửa khoảng [start_ms, end_ms).

    Gán theo TRUNG ĐIỂM mảnh: ranh giới scene liền kề không chồng lấn, nên một mảnh vắt
    qua ranh giới thuộc đúng một scene thay vì bị đếm hai lần ở hai scene kề nhau.
    """
    parts = [
        seg.text.strip()
        for seg in segments
        if start_ms <= (seg.start_ms + seg.end_ms) // 2 < end_ms
    ]
    return " ".join(p for p in parts if p).strip()


def _assert_vietnamese(model: object, role: str) -> None:
    lang = getattr(model, "language", None)
    if lang not in _VI_OK:
        raise ValueError(f"{role} không hỗ trợ tiếng Việt (language={lang!r}) — vi phạm AD-9")


def assert_vietnamese_models(transcriber: Transcriber, ocr: OcrReader | None = None) -> None:
    """Guard AD-9 gọi được từ ngoài: fail SỚM (lúc dựng port ở worker) thay vì lặp lỗi
    trên từng scene. `enrich_scene_vietnamese` vẫn tự guard OCR — port có thể đến từ nơi khác.

    `ocr=None` là chế độ ASR-only hợp lệ (xem enrich_scene_vietnamese), không phải lỗi."""
    _assert_vietnamese(transcriber, "ASR")
    if ocr is not None:
        _assert_vietnamese(ocr, "OCR")


async def enrich_scene_vietnamese(
    session: AsyncSession,
    storage: StoragePort,
    scene_id: str,
    segments: list[TranscriptSegment],
    ocr: OcrReader | None = None,
) -> dict:
    """Ghi transcript (cắt từ `segments` theo timecode scene) + OCR keyframe các shot.

    `segments` do `Transcriber.transcribe()` sinh MỘT lần cho cả video (xem docstring
    module) — hàm này không gọi model, chỉ cắt theo `scene.start_ms`/`end_ms`.

    `ocr=None` => chạy ASR-only và **không đụng** `scene.ocr_text`. Đây là hệ quả trực tiếp
    của AD-5 (mỗi stage sở hữu cột của mình): OCR không chạy thì không ghi gì, nên kết quả
    OCR từ lượt trước không bị xoá. Dùng khi trọng số OCR chưa nạp được trên node.
    """
    if ocr is not None:
        _assert_vietnamese(ocr, "OCR")

    scene = await session.get(Scene, scene_id)
    if scene is None:
        raise ValueError(f"scene không tồn tại: {scene_id}")

    transcript = transcript_for_range(segments, scene.start_ms, scene.end_ms)

    texts: list[str] = []
    if ocr is not None:
        shots = (
            await session.execute(select(Shot).where(Shot.scene_id == scene_id))
        ).scalars().all()
        seen_keys: set[str] = set()
        for sh in shots:  # OCR trên keyframe (AD-6), lấy ảnh qua storage-port (AD-23)
            if not sh.keyframe_key or sh.keyframe_key in seen_keys:
                continue
            seen_keys.add(sh.keyframe_key)
            text = ocr.read_text(storage.get(sh.keyframe_key)).strip()
            if text:
                texts.append(text)

    scene.transcript = transcript  # cột riêng (AD-5)
    if ocr is not None:  # OCR không chạy => giữ nguyên giá trị cũ, không ghi None đè lên
        scene.ocr_text = "\n".join(texts) if texts else None
    await session.flush()
    return {
        "scene_id": scene_id,
        "transcript_len": len(transcript),
        "ocr_blocks": len(texts) if ocr is not None else None,  # None = stage không chạy
    }

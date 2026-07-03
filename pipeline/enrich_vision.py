"""Làm giàu thị giác: khuôn mặt + đối tượng (Story 1.5 — FR-4, AD-5, AD-6, AD-11).

Face chỉ gán tên khi khớp registry (cosine similarity) và confidence >= ngưỡng;
ngoài ra `person_id=None` ("không xác định" — AD-11, không bịa danh tính).
Object lưu kèm confidence. Ghi vào bảng/cột riêng của stage này (`face_appearance`,
`scene.objects`) — không đụng field của stage khác (AD-5). Model thật ở
enrich_vision_backends.py (guarded).
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.ids import new_id
from shared.models import FaceAppearance, Person, Scene, Shot
from shared.storage import StoragePort


@dataclass(frozen=True)
class FaceDetection:
    embedding: list[float]


@dataclass(frozen=True)
class ObjectDetection:
    label: str
    confidence: float


class FaceRecognizer(Protocol):
    def detect(self, image: bytes) -> list[FaceDetection]: ...


class ObjectDetector(Protocol):
    def detect(self, image: bytes) -> list[ObjectDetection]: ...


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    if len(a) != len(b):
        raise ValueError(f"embedding lệch chiều: {len(a)} != {len(b)}")
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    # confidence/score = float 0-1 theo Consistency Conventions của spine -> kẹp âm về 0
    return max(0.0, dot / (norm_a * norm_b))


def _best_match(embedding: list[float], persons: list[Person]) -> tuple[str | None, float]:
    """Trả (person_id, best_score) — best_score=0.0 nếu registry rỗng.

    Person có `reference_embedding` hỏng (JSON lỗi) hoặc lệch chiều bị bỏ qua thay vì
    làm crash toàn bộ face-match của Scene.
    """
    best_id: str | None = None
    best_score = 0.0
    for person in persons:
        try:
            ref = json.loads(person.reference_embedding)
            score = _cosine_similarity(embedding, ref)
        except (TypeError, ValueError):
            continue
        if score > best_score:
            best_score, best_id = score, person.person_id
    return best_id, best_score


async def enrich_scene_vision(
    session: AsyncSession,
    storage: StoragePort,
    scene_id: str,
    face_recognizer: FaceRecognizer,
    object_detector: ObjectDetector,
    *,
    face_threshold: float = 0.5,
) -> dict:
    """Face-match + object-detect trên keyframe các Shot của Scene (idempotent overwrite)."""
    scene = await session.get(Scene, scene_id)
    if scene is None:
        raise ValueError(f"scene không tồn tại: {scene_id}")

    # order_by ổn định -> tie-break xác định khi hai person có cùng similarity cao nhất
    persons = (
        await session.execute(select(Person).order_by(Person.created_at, Person.person_id))
    ).scalars().all()

    shots = (
        await session.execute(select(Shot).where(Shot.scene_id == scene_id))
    ).scalars().all()

    face_rows: list[tuple[str | None, float]] = []
    object_rows: list[dict] = []
    seen_keys: set[str] = set()
    for sh in shots:  # face/object chỉ chạy trên Keyframe (AD-6), qua storage-port (AD-23)
        if not sh.keyframe_key or sh.keyframe_key in seen_keys:
            continue
        seen_keys.add(sh.keyframe_key)
        image = storage.get(sh.keyframe_key)

        for face in face_recognizer.detect(image):
            person_id, score = _best_match(face.embedding, persons)
            if score < face_threshold:
                person_id = None  # AD-11: không bịa danh tính
            face_rows.append((person_id, score))

        for det in object_detector.detect(image):
            object_rows.append({"label": det.label, "confidence": det.confidence})

    # Idempotent overwrite: xoá face_appearance cũ của Scene trước khi ghi lại (stage sở hữu bảng này)
    await session.execute(delete(FaceAppearance).where(FaceAppearance.scene_id == scene_id))
    for person_id, score in face_rows:
        session.add(FaceAppearance(appearance_id=new_id(), scene_id=scene_id,
                                   person_id=person_id, confidence=score))

    scene.objects = json.dumps(object_rows) if object_rows else None  # cột riêng (AD-5)
    await session.flush()
    return {"scene_id": scene_id, "faces": len(face_rows), "objects": len(object_rows)}

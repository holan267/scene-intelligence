"""Sinh Scene Document bằng VLM (Story 1.6 — FR-5, FR-13, AD-5, AD-6, AD-9).

Siết nhiễu (FR-13) xảy ra ở build_hints — TRƯỚC khi đưa vào ngữ cảnh cho model, nghĩa là
tín hiệu nhiễu/confidence-thấp không bao giờ được đưa cho model như một khẳng định (không
phải lọc hậu-kỳ trên văn bản model đã sinh ra). Model thật ở describe_backends.py (guarded).
"""
from __future__ import annotations

import json
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import FaceAppearance, Person, Scene, Shot
from shared.storage import StoragePort


class SceneDescriber(Protocol):
    def describe(self, keyframe_images: list[bytes], hints: dict) -> str: ...


def _filter_objects(objects_json: str, corpus_stopwords: set[str], confidence_threshold: float) -> list[str]:
    """Nhãn đối tượng qua ngưỡng confidence, không trong corpus_stopwords (FR-13)."""
    try:
        parsed = json.loads(objects_json)
    except (json.JSONDecodeError, TypeError):
        return []
    labels: list[str] = []
    for obj in parsed:
        if not isinstance(obj, dict) or "label" not in obj or "confidence" not in obj:
            continue
        if obj["confidence"] >= confidence_threshold and obj["label"] not in corpus_stopwords:
            labels.append(obj["label"])
    return labels


def _identified_face_names(face_appearances: list[FaceAppearance], persons: dict[str, Person]) -> list[str]:
    """Tên người đã xác định (person_id is not None), khử trùng lặp qua nhiều Shot (FR-13)."""
    names: list[str] = []
    seen: set[str] = set()
    for appearance in face_appearances:
        if appearance.person_id is None or appearance.person_id not in persons:
            continue
        name = persons[appearance.person_id].name
        if name not in seen:
            seen.add(name)
            names.append(name)
    return names


def build_hints(
    scene: Scene,
    face_appearances: list[FaceAppearance],
    persons: dict[str, Person],
    corpus_stopwords: set[str],
    *,
    confidence_threshold: float = 0.5,
) -> dict:
    """Gộp tín hiệu đã làm giàu thành ngữ cảnh cho describer — siết nhiễu tại đây (FR-13)."""
    ocr_text = scene.ocr_text
    if ocr_text is not None and ocr_text in corpus_stopwords:
        ocr_text = None

    objects = _filter_objects(scene.objects, corpus_stopwords, confidence_threshold) if scene.objects else []
    faces = _identified_face_names(face_appearances, persons)

    return {
        "transcript": scene.transcript,
        "ocr_text": ocr_text,
        "objects": objects,
        "faces": faces,
    }


async def describe_scene(
    session: AsyncSession,
    storage: StoragePort,
    scene_id: str,
    describer: SceneDescriber,
    corpus_stopwords: set[str],
    *,
    confidence_threshold: float = 0.5,
) -> dict:
    """Sinh scene.scene_document từ keyframe + hints đã siết nhiễu (cột riêng — AD-5)."""
    scene = await session.get(Scene, scene_id)
    if scene is None:
        raise ValueError(f"scene không tồn tại: {scene_id}")

    shots = (
        await session.execute(
            select(Shot).where(Shot.scene_id == scene_id).order_by(Shot.start_ms)
        )
    ).scalars().all()
    keyframe_images: list[bytes] = []
    seen_keys: set[str] = set()
    for sh in shots:  # chỉ Keyframe (AD-6), qua storage-port (AD-23)
        if not sh.keyframe_key or sh.keyframe_key in seen_keys:
            continue
        seen_keys.add(sh.keyframe_key)
        keyframe_images.append(storage.get(sh.keyframe_key))

    appearances = (
        await session.execute(select(FaceAppearance).where(FaceAppearance.scene_id == scene_id))
    ).scalars().all()
    person_ids = {a.person_id for a in appearances if a.person_id is not None}
    persons = {}
    if person_ids:
        rows = (await session.execute(select(Person).where(Person.person_id.in_(person_ids)))).scalars().all()
        persons = {p.person_id: p for p in rows}

    hints = build_hints(scene, appearances, persons, corpus_stopwords,
                        confidence_threshold=confidence_threshold)
    scene.scene_document = describer.describe(keyframe_images, hints)  # cột riêng (AD-5)
    await session.flush()
    return {"scene_id": scene_id, "scene_document_len": len(scene.scene_document)}

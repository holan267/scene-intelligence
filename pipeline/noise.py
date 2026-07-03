"""Siết nhiễu theo corpus (Story 1.6 — FR-13).

Chuỗi OCR hoặc nhãn đối tượng xuất hiện ở hầu hết Scene trong kho (logo, ticker) bị coi
là "stopword" — bị loại khỏi ngữ cảnh dựng Scene Document (xem `pipeline/describe.py`).
Đơn vị là TOÀN BỘ giá trị `ocr_text`/`label`, không tách từ — đúng nghĩa "chuỗi lặp" của FR-13.
"""
from __future__ import annotations

import json
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import Scene


def _scene_labels(objects_json: str) -> set[str]:
    """Nhãn distinct trong scene.objects — bỏ qua JSON hỏng thay vì làm crash cả corpus scan."""
    try:
        parsed = json.loads(objects_json)
    except (json.JSONDecodeError, TypeError):
        return set()
    return {obj["label"] for obj in parsed if isinstance(obj, dict) and "label" in obj}


async def corpus_stopwords(session: AsyncSession, *, ratio_threshold: float = 0.6) -> set[str]:
    """Trả tập chuỗi OCR/nhãn xuất hiện ở tỷ lệ Scene >= ratio_threshold trên toàn kho."""
    scenes = (await session.execute(select(Scene.ocr_text, Scene.objects))).all()
    total = len(scenes)
    if total == 0:
        return set()

    ocr_counts: Counter[str] = Counter()
    label_counts: Counter[str] = Counter()
    for ocr_text, objects_json in scenes:
        if ocr_text:
            ocr_counts[ocr_text] += 1
        if objects_json:
            label_counts.update(_scene_labels(objects_json))

    stopwords = {text for text, count in ocr_counts.items() if count / total >= ratio_threshold}
    stopwords |= {label for label, count in label_counts.items() if count / total >= ratio_threshold}
    return stopwords

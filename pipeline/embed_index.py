"""Embed + Index (Story 1.6 — FR-5, AD-4, AD-7, AD-16, AD-17).

`index_scene` ghi đúng một `scene_embedding`/Scene, dựng lại được 100% từ
`scene.scene_document` (SoT — AD-4). Chỉ chuyển `search_status = "indexed"` SAU KHI
scene_embedding đã ghi xong (flush thành công) — nếu embedder lỗi, hàm raise trước khi
chạm search_status, giữ nguyên trạng thái cũ (AD-17). Model thật ở embed_backends.py (guarded).
"""
from __future__ import annotations

import hashlib
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import Scene, SceneEmbedding


class TextEmbedder(Protocol):
    def embed(self, text: str) -> list[float]: ...


def doc_version(scene_document: str) -> str:
    """Checksum sha256 của scene_document — freshness của derived-artifact (AD-16)."""
    return hashlib.sha256(scene_document.encode()).hexdigest()


async def index_scene(session: AsyncSession, scene_id: str, embedder: TextEmbedder) -> dict:
    scene = await session.get(Scene, scene_id)
    if scene is None:
        raise ValueError(f"scene không tồn tại: {scene_id}")
    if scene.scene_document is None or not scene.scene_document.strip():
        raise ValueError(f"scene {scene_id} chưa có scene_document hợp lệ (chưa chạy describe)")

    version = doc_version(scene.scene_document)
    embedding = embedder.embed(scene.scene_document)  # có thể raise -> search_status chưa bị đụng

    existing = await session.get(SceneEmbedding, scene_id)
    if existing is not None:
        existing.embedding = embedding
        existing.fts_text = scene.scene_document
        existing.doc_version = version
    else:
        session.add(SceneEmbedding(scene_id=scene_id, embedding=embedding,
                                   fts_text=scene.scene_document, doc_version=version))
    await session.flush()  # ghi xong scene_embedding trước

    scene.search_status = "indexed"  # AD-17: chỉ set sau khi đã ghi xong derived-store
    await session.flush()
    return {"scene_id": scene_id, "doc_version": version, "search_status": scene.search_status}

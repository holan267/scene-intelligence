"""ANN candidate fetch (Story 2.1, AD-8, AD-17).

⚠️ Chỉ chạy đúng trên Postgres thật — `.cosine_distance()` sinh SQL `<=>` không hợp lệ
trên sqlite (verify thực nghiệm: OperationalError "near '>': syntax error"). Đây là ranh
giới DUY NHẤT trong search/ chạm cosine-distance-query; mọi logic khác (search/rank.py)
là hàm thuần nhận list[dict] để unit-test không cần Postgres.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import Scene, SceneEmbedding


async def fetch_ann_candidates(  # pragma: no cover - phụ thuộc Postgres/pgvector thật
    session: AsyncSession, query_embedding: list[float], *, pool_size: int
) -> list[dict]:
    """Top-`pool_size` Scene `indexed` gần nhất theo cosine distance (AD-17: chỉ Scene indexed)."""
    q = (
        select(
            Scene.scene_id,
            Scene.video_id,
            Scene.start_ms,
            Scene.end_ms,
            Scene.scene_document,
            SceneEmbedding.doc_version,
            SceneEmbedding.embedding.cosine_distance(query_embedding).label("ann_distance"),
        )
        .join(SceneEmbedding, SceneEmbedding.scene_id == Scene.scene_id)
        .where(Scene.search_status == "indexed")
        .order_by("ann_distance")
        .limit(pool_size)
    )
    rows = (await session.execute(q)).all()
    return [
        {
            "scene_id": r.scene_id,
            "video_id": r.video_id,
            "start_ms": r.start_ms,
            "end_ms": r.end_ms,
            "scene_document": r.scene_document,
            "doc_version": r.doc_version,
            "ann_distance": r.ann_distance,
        }
        for r in rows
    ]

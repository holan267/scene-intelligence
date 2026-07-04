"""Nhúng câu truy vấn NL bằng BGE-M3 (Story 2.1, AD-9).

File riêng trong search/ (KHÔNG import pipeline/embed_backends.py) — ranh giới CQRS-lite
ingest/search (AD-2): search/ không được gọi hàm chéo từ pipeline/. Logic HTTP gần giống
pipeline/embed_backends.py::BgeM3Embedder là chủ đích (chia sẻ config, không chia sẻ code).
"""
from __future__ import annotations

import math
from typing import Protocol

import httpx

from shared.config import Settings, get_settings
from shared.models import SCENE_EMBEDDING_DIM


class QueryEmbedder(Protocol):
    async def embed(self, text: str) -> list[float]: ...


class BgeM3QueryEmbedder:
    """Nhúng câu truy vấn qua BGE-M3 (cùng Model Server dùng để dựng scene_embedding — Story 1.6)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def embed(self, text: str) -> list[float]:  # pragma: no cover - phụ thuộc production
        # httpx.AsyncClient (KHÔNG dùng httpx.post đồng bộ) — tránh chặn event loop trong
        # đường tìm kiếm tương tác (Review fix, Story 2.1).
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self._settings.embed_model_url}/v1/embeddings",
                    json={"model": "BGE-M3", "input": text},
                )
            response.raise_for_status()
            embedding = response.json()["data"][0]["embedding"]
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Gọi BGE-M3 thất bại: {exc}") from exc
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise RuntimeError(f"BGE-M3 trả response không đúng hình dạng mong đợi: {exc}") from exc

        if not isinstance(embedding, list) or len(embedding) != SCENE_EMBEDDING_DIM:
            raise RuntimeError(
                f"BGE-M3 trả embedding sai chiều: kỳ vọng {SCENE_EMBEDDING_DIM}, "
                f"nhận {len(embedding) if isinstance(embedding, list) else type(embedding)}"
            )
        # Review fix: từ chối NaN/inf — tránh normalize_ann_score biến giá trị hỏng thành
        # điểm "hoàn hảo" 1.0 một cách âm thầm.
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in embedding):
            raise RuntimeError("BGE-M3 trả embedding chứa giá trị không hữu hạn (NaN/inf)")
        return embedding

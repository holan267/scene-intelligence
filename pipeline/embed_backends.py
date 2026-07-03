"""Adapter BGE-M3 thật (Story 1.6). Guarded — chưa chạy môi trường dev.

BGE-M3 chạy trên Model Server (vLLM/embedder, AD-14) — gọi qua endpoint embeddings
OpenAI-compatible, không load model trong tiến trình pipeline. Cần server BGE-M3 đang
chạy tại `embed_model_url`.
"""
from __future__ import annotations

import httpx

from shared.config import Settings, get_settings
from shared.models import SCENE_EMBEDDING_DIM


class BgeM3Embedder:
    """Sinh dense embedding (1024 chiều — SCENE_EMBEDDING_DIM) qua BGE-M3 (vLLM embeddings)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def embed(self, text: str) -> list[float]:  # pragma: no cover - phụ thuộc production
        try:
            response = httpx.post(
                f"{self._settings.embed_model_url}/v1/embeddings",
                json={"model": "BGE-M3", "input": text},
                timeout=30.0,
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
        return embedding

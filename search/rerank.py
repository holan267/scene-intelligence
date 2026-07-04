"""Rerank candidate qua bge-reranker-v2-m3 (Story 2.1, AD-8, AD-9).

Cùng pattern adapter HTTP guarded như pipeline/describe_backends.py/embed_backends.py.
Endpoint/payload cụ thể của Model Server bge-reranker-v2-m3 là [ASSUMPTION] — chưa có
server thật để verify thực nghiệm (khác BGE-M3 vốn đã có tiền lệ /v1/embeddings rõ ràng
từ Story 1.6); implement theo convention rerank OpenAI-compatible phổ biến nhất, điều
chỉnh khi có Model Server thật.
"""
from __future__ import annotations

from typing import Protocol

import httpx

from shared.config import Settings, get_settings


class Reranker(Protocol):
    async def rerank(self, query: str, passages: list[str]) -> list[float]: ...


class BgeRerankerV2M3:
    """Cross-encoder rerank — trả điểm liên quan (0-1, đã chuẩn hoá) song song với passages."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def rerank(self, query: str, passages: list[str]) -> list[float]:  # pragma: no cover - phụ thuộc production
        # httpx.AsyncClient (KHÔNG dùng httpx.post đồng bộ) — tránh chặn event loop (Review fix).
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self._settings.rerank_model_url}/v1/rerank",
                    json={"model": "bge-reranker-v2-m3", "query": query, "documents": passages},
                )
            response.raise_for_status()
            results = response.json()["results"]
            by_index = {r["index"]: float(r["relevance_score"]) for r in results}
            scores = [by_index[i] for i in range(len(passages))]
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Gọi bge-reranker-v2-m3 thất bại: {exc}") from exc
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise RuntimeError(
                f"bge-reranker-v2-m3 trả response không đúng hình dạng mong đợi: {exc}"
            ) from exc

        if len(scores) != len(passages):
            raise RuntimeError(
                f"bge-reranker-v2-m3 trả số điểm sai: kỳ vọng {len(passages)}, nhận {len(scores)}"
            )
        return scores

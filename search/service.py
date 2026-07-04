"""Search Service entrypoint (Story 2.1, FR-6, AD-8): embed -> ANN -> lọc freshness -> rerank -> envelope."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from search.candidates import fetch_ann_candidates
from search.query_embed import QueryEmbedder
from search.rank import build_envelope, filter_fresh_candidates, maybe_rerank
from search.rerank import Reranker


async def search(
    session: AsyncSession,
    embedder: QueryEmbedder,
    reranker: Reranker,
    query: str,
    *,
    limit: int,
    pool_size: int,
    gap_threshold: float,
) -> tuple[list[dict], dict]:
    query_vec = await embedder.embed(query)
    candidates = await fetch_ann_candidates(session, query_vec, pool_size=pool_size)
    fresh = filter_fresh_candidates(candidates)
    ranked = await maybe_rerank(fresh, reranker, query, gap_threshold=gap_threshold)
    return build_envelope(ranked, limit=limit)

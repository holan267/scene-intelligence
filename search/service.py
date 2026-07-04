"""Search Service entrypoint (Story 2.1/2.2, FR-6/7/8, AD-8): embed -> ANN∥FTS -> RRF merge
-> lọc freshness -> rerank -> envelope."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from search.candidates import fetch_ann_candidates
from search.fts_candidates import fetch_fts_candidates
from search.fuse import reciprocal_rank_fusion
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
    k: int,
) -> tuple[list[dict], dict]:
    query_vec = await embedder.embed(query)
    # Tuần tự trên cùng AsyncSession (KHÔNG asyncio.gather — AsyncSession không an toàn khi
    # 2 coroutine dùng chung 1 session/connection đồng thời). "Song song" ở AD-8 là tầng khái
    # niệm (hai cơ chế truy hồi độc lập được hợp nhất bởi RRF), không phải concurrency runtime.
    ann_candidates = await fetch_ann_candidates(session, query_vec, pool_size=pool_size)
    fts_candidates = await fetch_fts_candidates(session, query, pool_size=pool_size)
    fused = reciprocal_rank_fusion(ann_candidates, fts_candidates, k=k)
    fresh = filter_fresh_candidates(fused)
    ranked = await maybe_rerank(fresh, reranker, query, gap_threshold=gap_threshold, k=k)
    return build_envelope(ranked, limit=limit)

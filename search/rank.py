"""Logic thuần: lọc freshness, rerank có điều kiện, dựng envelope (Story 2.1, AD-8, AD-13, AD-16).

Toàn bộ hàm ở đây KHÔNG chạm DB/HTTP — nhận list[dict] sẵn (từ search/candidates.py) để
unit-test đầy đủ bằng fake data (candidates.py không unit-test được qua sqlite — xem đó).
"""
from __future__ import annotations

import math

from search.rerank import Reranker
from shared.versioning import doc_version


def filter_fresh_candidates(candidates: list[dict]) -> list[dict]:
    """Loại candidate có scene_embedding.doc_version lệch checksum hiện tại (AD-16).

    Candidate có `scene_document=None` (cột nullable, không ràng buộc DB — Review fix) cũng
    bị loại như lệch phiên bản: không thể tính checksum để so sánh, coi là không đủ điều
    kiện phục vụ search thay vì crash.
    """
    return [
        c for c in candidates
        if c["scene_document"] is not None and doc_version(c["scene_document"]) == c["doc_version"]
    ]


def normalize_ann_score(distance: float) -> float:
    """cosine_distance -> điểm 0-1 (0=không liên quan, 1=giống hệt). Dùng khi bỏ qua rerank."""
    if not math.isfinite(distance):  # Review fix: NaN/inf -> 0.0 thay vì lọt qua min/max âm thầm
        return 0.0
    return max(0.0, min(1.0, 1.0 - distance))


async def maybe_rerank(
    candidates: list[dict], reranker: Reranker, query: str, *, gap_threshold: float
) -> list[dict]:
    """Rerank có điều kiện (AD-8): bỏ qua khi điểm ANN #1 bỏ xa #2."""
    ranked = sorted(candidates, key=lambda c: normalize_ann_score(c["ann_distance"]), reverse=True)
    if len(ranked) < 2:
        for c in ranked:
            c["score"] = normalize_ann_score(c["ann_distance"])
        return ranked

    scores = [normalize_ann_score(c["ann_distance"]) for c in ranked]
    if scores[0] - scores[1] >= gap_threshold:
        for c, s in zip(ranked, scores, strict=True):
            c["score"] = s
        return ranked

    rerank_scores = await reranker.rerank(query, [c["scene_document"] for c in ranked])
    for c, s in zip(ranked, rerank_scores, strict=True):
        c["score"] = s
    return sorted(ranked, key=lambda c: c["score"], reverse=True)


def build_envelope(ranked: list[dict], *, limit: int) -> tuple[list[dict], dict]:
    """Dựng envelope {results, meta} (AD-13). thumbnail_url = URL scheme (Story 3.1 mới phục vụ
    thật); highlights = [] cố định (Story 2.2 full-text mới có nội dung để highlight)."""
    page = ranked[:limit]
    results = [
        {
            "scene_id": c["scene_id"],
            "video_id": c["video_id"],
            "start_ms": c["start_ms"],
            "end_ms": c["end_ms"],
            "score": c["score"],
            "thumbnail_url": f"/api/v1/scenes/{c['scene_id']}/thumbnail",
            "highlights": [],
        }
        for c in page
    ]
    meta = {"next_cursor": None, "count": len(results)}
    return results, meta

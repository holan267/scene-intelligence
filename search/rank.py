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


def normalize_rrf_score(rrf_score: float, *, k: int) -> float:
    """RRF score -> điểm 0-1, chuẩn hoá theo max lý thuyết 2/(k+1) (Scene #1 ở CẢ hai nhánh
    ANN+FTS). Dùng cho gap-check + score khi bỏ qua rerank (Story 2.2, thay normalize_ann_score
    của Story 2.1 — sau story này mọi candidate đều đến từ RRF, không còn ann_distance thuần)."""
    if not math.isfinite(rrf_score):  # Review fix (Story 2.1): NaN/inf -> 0.0
        return 0.0
    max_score = 2.0 / (k + 1)
    return max(0.0, min(1.0, rrf_score / max_score))


async def maybe_rerank(
    candidates: list[dict], reranker: Reranker, query: str, *, gap_threshold: float, k: int
) -> list[dict]:
    """Rerank có điều kiện (AD-8): bỏ qua khi điểm RRF chuẩn hoá #1 bỏ xa #2."""
    ranked = sorted(candidates, key=lambda c: normalize_rrf_score(c["rrf_score"], k=k), reverse=True)
    if len(ranked) < 2:
        for c in ranked:
            c["score"] = normalize_rrf_score(c["rrf_score"], k=k)
        return ranked

    scores = [normalize_rrf_score(c["rrf_score"], k=k) for c in ranked]
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
    thật); highlights = [snippet] khi Scene khớp qua FTS (ts_headline, Story 2.2), [] khi chỉ
    khớp qua ANN."""
    page = ranked[:limit]
    results = [
        {
            "scene_id": c["scene_id"],
            "video_id": c["video_id"],
            "start_ms": c["start_ms"],
            "end_ms": c["end_ms"],
            "score": c["score"],
            "thumbnail_url": f"/api/v1/scenes/{c['scene_id']}/thumbnail",
            "highlights": [c["fts_snippet"]] if c.get("fts_snippet") else [],
        }
        for c in page
    ]
    meta = {"next_cursor": None, "count": len(results)}
    return results, meta

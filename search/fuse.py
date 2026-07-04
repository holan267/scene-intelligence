"""Reciprocal Rank Fusion — hợp nhất candidate ANN + FTS ở mức Scene (Story 2.2, AD-7, AD-8).

Hàm thuần, KHÔNG chạm DB — nhận list[dict] đã sắp giảm dần theo mức liên quan của từng nhánh
(từ search/candidates.py::fetch_ann_candidates / search/fts_candidates.py::fetch_fts_candidates,
vốn đã ORDER BY), unit-test đầy đủ bằng fake data.
"""
from __future__ import annotations


def reciprocal_rank_fusion(
    ann_candidates: list[dict], fts_candidates: list[dict], *, k: int
) -> list[dict]:
    """Hợp nhất hai list candidate theo scene_id: rrf_score = Σ 1/(k + rank) qua mỗi nhánh có mặt.

    Scene chỉ ở một nhánh chỉ nhận đóng góp từ nhánh đó (AC #3). Scene ở cả hai nhánh cộng dồn
    điểm từ cả hai. Trả về list đã sort giảm dần theo rrf_score.
    """
    merged: dict[str, dict] = {}

    for rank, c in enumerate(ann_candidates, start=1):
        scene_id = c["scene_id"]
        merged[scene_id] = {**c, "fts_snippet": None, "rrf_score": 1.0 / (k + rank)}

    for rank, c in enumerate(fts_candidates, start=1):
        scene_id = c["scene_id"]
        contribution = 1.0 / (k + rank)
        if scene_id in merged:
            merged[scene_id]["rrf_score"] += contribution
            merged[scene_id]["fts_snippet"] = c.get("fts_snippet")
        else:
            merged[scene_id] = {**c, "rrf_score": contribution}

    return sorted(merged.values(), key=lambda c: c["rrf_score"], reverse=True)

from __future__ import annotations

from search.fuse import reciprocal_rank_fusion


def _candidate(scene_id: str, *, fts_snippet=None) -> dict:
    return {
        "scene_id": scene_id,
        "video_id": "v1",
        "start_ms": 0,
        "end_ms": 1000,
        "scene_document": f"doc-{scene_id}",
        "doc_version": "v1",
        "fts_snippet": fts_snippet,
    }


def test_scene_only_in_ann_keeps_fields_and_no_snippet():
    ann = [_candidate("s1")]
    result = reciprocal_rank_fusion(ann, [], k=60)
    assert len(result) == 1
    assert result[0]["scene_id"] == "s1"
    assert result[0]["video_id"] == "v1"
    assert result[0]["scene_document"] == "doc-s1"
    assert result[0].get("fts_snippet") is None
    assert result[0]["rrf_score"] == 1.0 / 61


def test_scene_only_in_fts_keeps_fields_and_snippet():
    fts = [_candidate("s1", fts_snippet="**World Cup**")]
    result = reciprocal_rank_fusion([], fts, k=60)
    assert len(result) == 1
    assert result[0]["scene_id"] == "s1"
    assert result[0]["fts_snippet"] == "**World Cup**"
    assert result[0]["rrf_score"] == 1.0 / 61


def test_scene_in_both_lists_sums_rrf_score():
    ann = [_candidate("s1"), _candidate("s2")]
    fts = [_candidate("s2", fts_snippet="hit"), _candidate("s1", fts_snippet="hit2")]
    result = reciprocal_rank_fusion(ann, fts, k=60)
    by_id = {c["scene_id"]: c for c in result}
    # s1: rank 1 in ann (idx0), rank 2 in fts (idx1) -> 1/61 + 1/62
    assert by_id["s1"]["rrf_score"] == 1.0 / 61 + 1.0 / 62
    # s2: rank 2 in ann, rank 1 in fts -> 1/62 + 1/61 (same total, but check independently)
    assert by_id["s2"]["rrf_score"] == 1.0 / 62 + 1.0 / 61
    assert by_id["s1"]["fts_snippet"] == "hit2"
    assert by_id["s2"]["fts_snippet"] == "hit"


def test_sorted_descending_by_rrf_score():
    ann = [_candidate("s1"), _candidate("s2"), _candidate("s3")]
    fts = [_candidate("s3")]
    result = reciprocal_rank_fusion(ann, fts, k=60)
    scores = [c["rrf_score"] for c in result]
    assert scores == sorted(scores, reverse=True)
    assert result[0]["scene_id"] == "s3"  # s3 in both ann(rank3)+fts(rank1) -> highest


def test_k_parameter_changes_formula():
    ann = [_candidate("s1")]
    result_k60 = reciprocal_rank_fusion(ann, [], k=60)
    result_k10 = reciprocal_rank_fusion(ann, [], k=10)
    assert result_k60[0]["rrf_score"] == 1.0 / 61
    assert result_k10[0]["rrf_score"] == 1.0 / 11
    assert result_k60[0]["rrf_score"] != result_k10[0]["rrf_score"]

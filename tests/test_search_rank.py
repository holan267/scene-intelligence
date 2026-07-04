from __future__ import annotations

from search.rank import build_envelope, filter_fresh_candidates, maybe_rerank, normalize_ann_score
from shared.versioning import doc_version


class FakeReranker:
    def __init__(self, scores: list[float] | None = None, *, raise_error: bool = False) -> None:
        self._scores = scores
        self._raise_error = raise_error
        self.calls = 0

    async def rerank(self, query: str, passages: list[str]) -> list[float]:
        self.calls += 1
        if self._raise_error:
            raise RuntimeError("reranker lỗi")
        return self._scores if self._scores is not None else [0.5] * len(passages)


def _candidate(scene_id: str, *, scene_document="doc", distance=0.1, video_id="v1",
               start_ms=0, end_ms=1000, doc_version_override=None) -> dict:
    return {
        "scene_id": scene_id,
        "video_id": video_id,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "scene_document": scene_document,
        "doc_version": doc_version_override if doc_version_override is not None else doc_version(scene_document),
        "ann_distance": distance,
    }


def test_filter_fresh_candidates_keeps_matching_and_drops_stale():
    fresh = _candidate("s1")
    stale = _candidate("s2", doc_version_override="deadbeef")
    result = filter_fresh_candidates([fresh, stale])
    assert [c["scene_id"] for c in result] == ["s1"]


def test_filter_fresh_candidates_drops_none_scene_document():
    # Review fix: scene_document=None (cột nullable) không được crash, chỉ bị loại
    none_doc = _candidate("s1", scene_document=None, doc_version_override="anything")
    result = filter_fresh_candidates([none_doc])
    assert result == []


def test_normalize_ann_score_clamps_0_1():
    assert normalize_ann_score(0.0) == 1.0
    assert normalize_ann_score(1.0) == 0.0
    assert normalize_ann_score(-0.5) == 1.0  # clamp trên
    assert normalize_ann_score(2.0) == 0.0  # clamp dưới


def test_normalize_ann_score_nan_and_inf_return_zero():
    # Review fix: NaN/inf không được lọt qua min/max thành điểm "hoàn hảo" âm thầm
    assert normalize_ann_score(float("nan")) == 0.0
    assert normalize_ann_score(float("inf")) == 0.0
    assert normalize_ann_score(float("-inf")) == 0.0


async def test_maybe_rerank_skips_when_gap_large():
    candidates = [_candidate("s1", distance=0.0), _candidate("s2", distance=0.5)]
    reranker = FakeReranker()
    result = await maybe_rerank(candidates, reranker, "query", gap_threshold=0.15)
    assert reranker.calls == 0  # bỏ qua rerank
    assert [c["scene_id"] for c in result] == ["s1", "s2"]
    assert result[0]["score"] == 1.0


async def test_maybe_rerank_calls_reranker_when_gap_small_and_resorts():
    candidates = [_candidate("s1", distance=0.1), _candidate("s2", distance=0.12)]
    reranker = FakeReranker(scores=[0.2, 0.9])  # đảo thứ tự
    result = await maybe_rerank(candidates, reranker, "query", gap_threshold=0.15)
    assert reranker.calls == 1
    assert [c["scene_id"] for c in result] == ["s2", "s1"]
    assert result[0]["score"] == 0.9


async def test_maybe_rerank_skips_for_single_candidate():
    candidates = [_candidate("s1", distance=0.2)]
    reranker = FakeReranker()
    result = await maybe_rerank(candidates, reranker, "query", gap_threshold=0.15)
    assert reranker.calls == 0
    assert result[0]["score"] == normalize_ann_score(0.2)


def test_build_envelope_shape_and_limit():
    ranked = [
        {**_candidate("s1"), "score": 0.9},
        {**_candidate("s2"), "score": 0.5},
        {**_candidate("s3"), "score": 0.1},
    ]
    results, meta = build_envelope(ranked, limit=2)
    assert len(results) == 2
    assert results[0] == {
        "scene_id": "s1",
        "video_id": "v1",
        "start_ms": 0,
        "end_ms": 1000,
        "score": 0.9,
        "thumbnail_url": "/api/v1/scenes/s1/thumbnail",
        "highlights": [],
    }
    assert meta == {"next_cursor": None, "count": 2}

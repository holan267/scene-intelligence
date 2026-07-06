from __future__ import annotations

import search.service as service_module
from shared.filters import SceneFilters
from shared.versioning import doc_version


class FakeQueryEmbedder:
    def __init__(self, vector: list[float] | None = None) -> None:
        self._vector = vector or [0.1, 0.2, 0.3]
        self.calls = 0

    async def embed(self, text: str) -> list[float]:
        self.calls += 1
        return self._vector


class FakeReranker:
    async def rerank(self, query: str, passages: list[str]) -> list[float]:
        return [0.5] * len(passages)


def _fake_ann_candidate(scene_id: str, *, scene_document="doc", stale=False) -> dict:
    return {
        "scene_id": scene_id,
        "video_id": "v1",
        "start_ms": 0,
        "end_ms": 1000,
        "scene_document": scene_document,
        "doc_version": "stale-checksum" if stale else doc_version(scene_document),
    }


def _fake_fts_candidate(scene_id: str, *, scene_document="doc", snippet="**hit**") -> dict:
    return {
        "scene_id": scene_id,
        "video_id": "v1",
        "start_ms": 0,
        "end_ms": 1000,
        "scene_document": scene_document,
        "doc_version": doc_version(scene_document),
        "fts_snippet": snippet,
    }


def _patch_fetchers(monkeypatch, *, ann=None, fts=None, captured_filters=None):
    async def _fake_ann(session, query_embedding, *, pool_size, filters=None):
        assert query_embedding == [0.1, 0.2, 0.3]
        if captured_filters is not None:
            captured_filters["ann"] = filters
        return ann or []

    async def _fake_fts(session, query, *, pool_size, filters=None):
        if captured_filters is not None:
            captured_filters["fts"] = filters
        return fts or []

    monkeypatch.setattr(service_module, "fetch_ann_candidates", _fake_ann)
    monkeypatch.setattr(service_module, "fetch_fts_candidates", _fake_fts)


async def test_search_orchestrates_embed_fetch_fuse_filter_rank_envelope(async_session, monkeypatch):
    ann = [
        _fake_ann_candidate("s1"),  # top ANN, gap lớn với s2 -> bỏ rerank
        _fake_ann_candidate("s2"),
        _fake_ann_candidate("s3", stale=True),  # lệch doc_version -> bị loại
    ]
    _patch_fetchers(monkeypatch, ann=ann, fts=[])

    embedder = FakeQueryEmbedder()
    results, meta = await service_module.search(
        async_session, embedder, FakeReranker(), "câu truy vấn",
        limit=10, pool_size=20, gap_threshold=0.15, k=60,
    )

    assert embedder.calls == 1
    scene_ids = [r["scene_id"] for r in results]
    assert "s3" not in scene_ids  # stale bị lọc bởi filter_fresh_candidates
    assert scene_ids == ["s1", "s2"]
    assert meta == {"next_cursor": None, "count": 2}


async def test_search_respects_limit(async_session, monkeypatch):
    ann = [_fake_ann_candidate(f"s{i}") for i in range(5)]
    _patch_fetchers(monkeypatch, ann=ann, fts=[])

    results, meta = await service_module.search(
        async_session, FakeQueryEmbedder(), FakeReranker(), "q",
        limit=2, pool_size=20, gap_threshold=0.15, k=60,
    )
    assert len(results) == 2
    assert meta["count"] == 2


async def test_search_includes_fts_only_scene(async_session, monkeypatch):
    # Scene chỉ khớp FTS (không lọt top ANN) vẫn xuất hiện trong kết quả cuối (AC #3)
    ann = [_fake_ann_candidate("s1")]
    fts = [_fake_fts_candidate("s2", snippet="**World Cup**")]
    _patch_fetchers(monkeypatch, ann=ann, fts=fts)

    results, _ = await service_module.search(
        async_session, FakeQueryEmbedder(), FakeReranker(), "World Cup",
        limit=10, pool_size=20, gap_threshold=0.15, k=60,
    )
    scene_ids = {r["scene_id"] for r in results}
    assert "s2" in scene_ids
    s2 = next(r for r in results if r["scene_id"] == "s2")
    assert s2["highlights"] == ["**World Cup**"]


async def test_search_scene_in_both_lists_ranks_higher(async_session, monkeypatch):
    ann = [_fake_ann_candidate("s1"), _fake_ann_candidate("s2")]
    fts = [_fake_fts_candidate("s2", snippet="**hit**")]
    _patch_fetchers(monkeypatch, ann=ann, fts=fts)

    results, _ = await service_module.search(
        async_session, FakeQueryEmbedder(), FakeReranker(), "q",
        limit=10, pool_size=20, gap_threshold=0.15, k=60,
    )
    # s2 xuất hiện ở cả 2 nhánh -> rrf_score cao hơn -> đứng đầu
    assert results[0]["scene_id"] == "s2"


async def test_search_forwards_filters_to_both_fetchers(async_session, monkeypatch):
    captured = {}
    _patch_fetchers(monkeypatch, ann=[], fts=[], captured_filters=captured)

    filters = SceneFilters(min_duration_ms=1000)
    await service_module.search(
        async_session, FakeQueryEmbedder(), FakeReranker(), "q",
        limit=10, pool_size=20, gap_threshold=0.15, k=60, filters=filters,
    )
    assert captured["ann"] is filters
    assert captured["fts"] is filters


async def test_search_defaults_filters_to_none(async_session, monkeypatch):
    captured = {}
    _patch_fetchers(monkeypatch, ann=[], fts=[], captured_filters=captured)

    await service_module.search(
        async_session, FakeQueryEmbedder(), FakeReranker(), "q",
        limit=10, pool_size=20, gap_threshold=0.15, k=60,
    )
    assert captured["ann"] is None
    assert captured["fts"] is None

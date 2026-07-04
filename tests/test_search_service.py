from __future__ import annotations

import search.service as service_module
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


def _fake_candidate(scene_id: str, *, distance=0.1, scene_document="doc", stale=False) -> dict:
    return {
        "scene_id": scene_id,
        "video_id": "v1",
        "start_ms": 0,
        "end_ms": 1000,
        "scene_document": scene_document,
        "doc_version": "stale-checksum" if stale else doc_version(scene_document),
        "ann_distance": distance,
    }


async def test_search_orchestrates_embed_fetch_filter_rank_envelope(async_session, monkeypatch):
    fake_candidates = [
        _fake_candidate("s1", distance=0.0),  # gap lớn với s2 -> bỏ rerank
        _fake_candidate("s2", distance=0.9),
        _fake_candidate("s3", distance=0.05, stale=True),  # lệch doc_version -> bị loại
    ]

    async def _fake_fetch(session, query_embedding, *, pool_size):
        assert query_embedding == [0.1, 0.2, 0.3]
        return fake_candidates

    monkeypatch.setattr(service_module, "fetch_ann_candidates", _fake_fetch)

    embedder = FakeQueryEmbedder()
    results, meta = await service_module.search(
        async_session, embedder, FakeReranker(), "câu truy vấn",
        limit=10, pool_size=20, gap_threshold=0.15,
    )

    assert embedder.calls == 1
    scene_ids = [r["scene_id"] for r in results]
    assert "s3" not in scene_ids  # stale bị lọc bởi filter_fresh_candidates
    assert scene_ids == ["s1", "s2"]  # sắp theo điểm ANN chuẩn hoá, không rerank (gap lớn)
    assert meta == {"next_cursor": None, "count": 2}


async def test_search_respects_limit(async_session, monkeypatch):
    fake_candidates = [_fake_candidate(f"s{i}", distance=i * 0.01) for i in range(5)]

    async def _fake_fetch(session, query_embedding, *, pool_size):
        return fake_candidates

    monkeypatch.setattr(service_module, "fetch_ann_candidates", _fake_fetch)

    results, meta = await service_module.search(
        async_session, FakeQueryEmbedder(), FakeReranker(), "q",
        limit=2, pool_size=20, gap_threshold=0.15,
    )
    assert len(results) == 2
    assert meta["count"] == 2

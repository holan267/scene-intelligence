from __future__ import annotations

import pytest
from sqlalchemy import select

from pipeline.embed_index import doc_version, index_scene
from shared.ids import scene_id as make_scene_id
from shared.models import SCENE_EMBEDDING_DIM, Scene, SceneEmbedding, Video


def _vec(*head: float) -> list[float]:
    """Vector đủ chiều SCENE_EMBEDDING_DIM — điền head vào đầu, phần còn lại = 0.0."""
    return list(head) + [0.0] * (SCENE_EMBEDDING_DIM - len(head))


class FakeEmbedder:
    def __init__(self, vector: list[float] | None = None, *, raise_error: bool = False) -> None:
        self._vector = vector if vector is not None else _vec(0.1, 0.2, 0.3)
        self._raise_error = raise_error

    def embed(self, text: str) -> list[float]:
        if self._raise_error:
            raise RuntimeError("embedder lỗi")
        return self._vector


async def _seed(session, *, with_document: bool = True) -> str:
    session.add(Video(video_id="v1", framerate=25.0, source_key="v1/src.mp4"))
    sid = make_scene_id("v1", 0, 2000)
    session.add(Scene(scene_id=sid, video_id="v1", start_ms=0, end_ms=2000,
                      scene_document="Bản tin thời sự" if with_document else None))
    await session.flush()
    return sid


def test_doc_version_is_deterministic_sha256():
    v1 = doc_version("Bản tin thời sự")
    v2 = doc_version("Bản tin thời sự")
    v3 = doc_version("Bản tin khác")
    assert v1 == v2
    assert v1 != v3
    assert len(v1) == 64  # sha256 hex


async def test_index_scene_raises_when_no_scene_document(async_session):
    sid = await _seed(async_session, with_document=False)
    with pytest.raises(ValueError):
        await index_scene(async_session, sid, FakeEmbedder())


async def test_index_scene_raises_when_scene_document_blank(async_session):
    # [Review][Patch]: chuỗi rỗng/toàn khoảng trắng không được coi là scene_document hợp lệ
    sid = await _seed(async_session, with_document=False)
    scene = await async_session.get(Scene, sid)
    scene.scene_document = "   "
    await async_session.flush()
    with pytest.raises(ValueError):
        await index_scene(async_session, sid, FakeEmbedder())


async def test_index_scene_writes_embedding_and_flips_indexed(async_session):
    # AC-2/3/5: ghi đúng 1 dòng scene_embedding + doc_version, rồi mới chuyển indexed
    sid = await _seed(async_session)
    result = await index_scene(async_session, sid, FakeEmbedder(_vec(0.1, 0.2, 0.3)))

    row = await async_session.get(SceneEmbedding, sid)
    assert row.embedding is not None
    assert row.doc_version == doc_version("Bản tin thời sự")
    assert row.fts_text == "Bản tin thời sự"

    scene = await async_session.get(Scene, sid)
    assert scene.search_status == "indexed"
    assert result["search_status"] == "indexed"


async def test_index_scene_does_not_flip_status_when_embedder_fails(async_session):
    # AC-5: embed lỗi -> search_status giữ nguyên, không có dòng scene_embedding mồ côi
    sid = await _seed(async_session)
    with pytest.raises(RuntimeError):
        await index_scene(async_session, sid, FakeEmbedder(raise_error=True))

    scene = await async_session.get(Scene, sid)
    assert scene.search_status == "pending"  # default, chưa đổi

    row = await async_session.get(SceneEmbedding, sid)
    assert row is None


async def test_index_scene_idempotent_rerun_updates_same_row(async_session):
    sid = await _seed(async_session)
    await index_scene(async_session, sid, FakeEmbedder(_vec(0.1, 0.2, 0.3)))
    await index_scene(async_session, sid, FakeEmbedder(_vec(0.4, 0.5, 0.6)))

    rows = (await async_session.execute(select(SceneEmbedding).where(SceneEmbedding.scene_id == sid))).scalars().all()
    assert len(rows) == 1  # không nhân đôi
    assert list(rows[0].embedding)[:3] == pytest.approx([0.4, 0.5, 0.6])


async def test_index_scene_rebuild_after_delete_is_equivalent(async_session):
    # AD-4: xoá scene_embedding rồi chạy lại -> dữ liệu tương đương (dựng lại từ SoT)
    sid = await _seed(async_session)
    embedder = FakeEmbedder(_vec(0.7, 0.8, 0.9))
    first = await index_scene(async_session, sid, embedder)

    row = await async_session.get(SceneEmbedding, sid)
    await async_session.delete(row)
    await async_session.flush()

    second = await index_scene(async_session, sid, embedder)
    assert second["doc_version"] == first["doc_version"]

    rebuilt = await async_session.get(SceneEmbedding, sid)
    assert list(rebuilt.embedding)[:3] == pytest.approx([0.7, 0.8, 0.9])

"""Test GET /api/v1/scenes/{scene_id}/thumbnail + GET /api/v1/videos/{video_id}/stream
(Story 3.1, AC #1-#4, #6).

Dùng httpx.AsyncClient + ASGITransport (KHÔNG dùng starlette.testclient.TestClient) để
chạy hoàn toàn trong CÙNG event loop với fixture `async_session` (sqlite in-memory,
StaticPool) — TestClient chạy app qua portal thread với event loop riêng, rủi ro xung
đột với connection sqlite in-memory đã mở ở loop khác.
"""
from __future__ import annotations

import httpx
from httpx import ASGITransport

import api.routes_media as routes_media_module
from api.main import create_app
from shared.db import get_session
from shared.models import Scene, Shot, Video
from shared.storage import FilesystemStorage


def _make_client(async_session, monkeypatch, storage):
    monkeypatch.setattr(routes_media_module, "build_storage", lambda *a, **kw: storage)

    async def _override_get_session():
        yield async_session

    app = create_app()
    app.dependency_overrides[get_session] = _override_get_session
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_thumbnail_returns_first_shot_keyframe_by_start_ms(
    async_session, monkeypatch, tmp_path
):
    storage = FilesystemStorage(tmp_path)
    storage.put("v1/keyframes/a.jpg", b"AAA-first-shot-bytes")
    storage.put("v1/keyframes/b.jpg", b"BBB-second-shot-bytes")

    async_session.add(Video(video_id="v1", source_key="v1.mp4"))
    async_session.add(Scene(scene_id="s1", video_id="v1", start_ms=0, end_ms=5000))
    # Cố tình thêm shot thứ hai (start_ms lớn hơn) TRƯỚC shot đầu trong thứ tự insert
    # để xác nhận endpoint chọn theo start_ms nhỏ nhất, không phải thứ tự chèn.
    async_session.add(
        Shot(shot_id="sh-b", scene_id="s1", video_id="v1", start_ms=2000, end_ms=3000,
             keyframe_key="v1/keyframes/b.jpg")
    )
    async_session.add(
        Shot(shot_id="sh-a", scene_id="s1", video_id="v1", start_ms=0, end_ms=2000,
             keyframe_key="v1/keyframes/a.jpg")
    )
    await async_session.commit()

    async with _make_client(async_session, monkeypatch, storage) as client:
        resp = await client.get("/api/v1/scenes/s1/thumbnail")

    assert resp.status_code == 200
    assert resp.content == b"AAA-first-shot-bytes"
    assert resp.headers["content-type"] == "image/jpeg"
    # AC #6: không lộ media-key/path thật trong response (review fix: assertion cũ
    # `b"v1/keyframes" not in resp.content` là no-op — resp.content là bytes JPEG cố
    # định, không bao giờ chứa chuỗi đó; check thật duy nhất có ý nghĩa là ở header).
    assert "v1/keyframes" not in "".join(resp.headers.values())


async def test_thumbnail_404_when_scene_not_found(async_session, monkeypatch, tmp_path):
    storage = FilesystemStorage(tmp_path)
    async with _make_client(async_session, monkeypatch, storage) as client:
        resp = await client.get("/api/v1/scenes/khong-ton-tai/thumbnail")
    assert resp.status_code == 404


async def test_thumbnail_404_when_scene_has_no_shot(async_session, monkeypatch, tmp_path):
    storage = FilesystemStorage(tmp_path)
    async_session.add(Video(video_id="v1", source_key="v1.mp4"))
    async_session.add(Scene(scene_id="s1", video_id="v1", start_ms=0, end_ms=5000))
    await async_session.commit()

    async with _make_client(async_session, monkeypatch, storage) as client:
        resp = await client.get("/api/v1/scenes/s1/thumbnail")
    assert resp.status_code == 404


async def test_thumbnail_404_when_shot_has_no_keyframe(async_session, monkeypatch, tmp_path):
    storage = FilesystemStorage(tmp_path)
    async_session.add(Video(video_id="v1", source_key="v1.mp4"))
    async_session.add(Scene(scene_id="s1", video_id="v1", start_ms=0, end_ms=5000))
    async_session.add(
        Shot(shot_id="sh-a", scene_id="s1", video_id="v1", start_ms=0, end_ms=2000,
             keyframe_key=None)
    )
    await async_session.commit()

    async with _make_client(async_session, monkeypatch, storage) as client:
        resp = await client.get("/api/v1/scenes/s1/thumbnail")
    assert resp.status_code == 404


async def test_thumbnail_404_when_keyframe_key_is_empty_string(async_session, monkeypatch, tmp_path):
    # Review fix: "" (chuỗi rỗng) khác None, phải bị chặn giống hệt None -> 404,
    # không để lọt xuống storage._resolve() raise ValueError -> 500.
    storage = FilesystemStorage(tmp_path)
    async_session.add(Video(video_id="v1", source_key="v1.mp4"))
    async_session.add(Scene(scene_id="s1", video_id="v1", start_ms=0, end_ms=5000))
    async_session.add(
        Shot(shot_id="sh-a", scene_id="s1", video_id="v1", start_ms=0, end_ms=2000,
             keyframe_key="")
    )
    await async_session.commit()

    async with _make_client(async_session, monkeypatch, storage) as client:
        resp = await client.get("/api/v1/scenes/s1/thumbnail")
    assert resp.status_code == 404


async def test_thumbnail_404_when_keyframe_file_missing_on_disk(async_session, monkeypatch, tmp_path):
    # Review fix: DB có row nhưng file đã mất trên disk -> 404 sạch, không phải 500.
    storage = FilesystemStorage(tmp_path)
    async_session.add(Video(video_id="v1", source_key="v1.mp4"))
    async_session.add(Scene(scene_id="s1", video_id="v1", start_ms=0, end_ms=5000))
    async_session.add(
        Shot(shot_id="sh-a", scene_id="s1", video_id="v1", start_ms=0, end_ms=2000,
             keyframe_key="v1/keyframes/khong-ton-tai.jpg")
    )
    await async_session.commit()

    async with _make_client(async_session, monkeypatch, storage) as client:
        resp = await client.get("/api/v1/scenes/s1/thumbnail")
    assert resp.status_code == 404


async def test_stream_returns_full_content_without_range(async_session, monkeypatch, tmp_path):
    storage = FilesystemStorage(tmp_path)
    storage.put("v1.mp4", b"0123456789")
    async_session.add(Video(video_id="v1", source_key="v1.mp4"))
    await async_session.commit()

    async with _make_client(async_session, monkeypatch, storage) as client:
        resp = await client.get("/api/v1/videos/v1/stream")

    assert resp.status_code == 200
    assert resp.content == b"0123456789"
    assert resp.headers["accept-ranges"] == "bytes"
    # AC #6: không lộ source_key/path filesystem thật
    assert "v1.mp4" not in "".join(resp.headers.values())
    assert "content-disposition" not in resp.headers  # không ép download (không truyền filename=)


async def test_stream_returns_partial_content_with_range(async_session, monkeypatch, tmp_path):
    storage = FilesystemStorage(tmp_path)
    storage.put("v1.mp4", b"0123456789")
    async_session.add(Video(video_id="v1", source_key="v1.mp4"))
    await async_session.commit()

    async with _make_client(async_session, monkeypatch, storage) as client:
        resp = await client.get("/api/v1/videos/v1/stream", headers={"Range": "bytes=0-3"})

    assert resp.status_code == 206
    assert resp.content == b"0123"
    assert resp.headers["content-range"] == "bytes 0-3/10"


async def test_stream_404_when_video_file_missing_on_disk(async_session, monkeypatch, tmp_path):
    # Review fix: DB có row Video nhưng file source_key đã mất trên disk -> 404 sạch.
    storage = FilesystemStorage(tmp_path)
    async_session.add(Video(video_id="v1", source_key="khong-ton-tai.mp4"))
    await async_session.commit()

    async with _make_client(async_session, monkeypatch, storage) as client:
        resp = await client.get("/api/v1/videos/v1/stream")
    assert resp.status_code == 404


async def test_stream_404_when_video_not_found(async_session, monkeypatch, tmp_path):
    storage = FilesystemStorage(tmp_path)
    async with _make_client(async_session, monkeypatch, storage) as client:
        resp = await client.get("/api/v1/videos/khong-ton-tai/stream")
    assert resp.status_code == 404

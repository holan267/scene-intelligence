from __future__ import annotations

from sqlalchemy import func, select

from pipeline.ingest import (
    discover_videos,
    enqueue_batch,
    finalize_job,
    job_progress,
)
from pipeline.workers import run_once
from shared.models import Video


def test_discover_filters_by_extension(tmp_path):
    (tmp_path / "a.mp4").write_bytes(b"x")
    (tmp_path / "b.txt").write_text("no")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "c.mov").write_bytes(b"y")
    names = {p.name for p in discover_videos(tmp_path)}
    assert names == {"a.mp4", "c.mov"}


async def test_enqueue_and_progress(tmp_path, async_session):
    # AC-1, AC-2
    (tmp_path / "a.mp4").write_bytes(b"x")
    (tmp_path / "b.mov").write_bytes(b"y")
    res = await enqueue_batch(async_session, discover_videos(tmp_path), tmp_path)
    assert res["queued"] == 2
    prog = await job_progress(async_session, res["job_id"])
    assert prog["total"] == 2 and prog["queued"] == 2 and prog["status"] == "running"


async def test_dedupe_idempotent(tmp_path, async_session):
    # AC-5: nạp lại không nhân đôi
    (tmp_path / "a.mp4").write_bytes(b"x")
    paths = discover_videos(tmp_path)
    await enqueue_batch(async_session, paths, tmp_path)
    res2 = await enqueue_batch(async_session, paths, tmp_path)
    assert res2["queued"] == 0 and res2["duplicates"] == 1


async def test_error_skip_does_not_stop_batch(tmp_path, async_session):
    # AC-3: tệp lỗi bị bỏ qua, lô vẫn chạy
    good = tmp_path / "a.mp4"
    good.write_bytes(b"x")
    missing = tmp_path / "ghost.mp4"  # không tạo -> not a file
    res = await enqueue_batch(async_session, [good, missing], tmp_path)
    assert res["queued"] == 1 and res["invalid"] == 1


async def test_worker_registers_video_and_orchestrator_finalizes(tmp_path, async_session):
    # AC-1, AC-4
    (tmp_path / "a.mp4").write_bytes(b"x")
    job = await enqueue_batch(async_session, discover_videos(tmp_path), tmp_path)
    assert await run_once(async_session, skip_locked=False) is True
    assert await run_once(async_session, skip_locked=False) is False  # hết task
    await finalize_job(async_session, job["job_id"])
    n = (await async_session.execute(select(func.count()).select_from(Video))).scalar_one()
    assert n == 1
    prog = await job_progress(async_session, job["job_id"])
    assert prog["done"] == 1 and prog["status"] == "done"


def test_ingest_routes_registered():
    from api.main import create_app

    paths = set(create_app().openapi()["paths"].keys())
    assert "/api/v1/ingest" in paths
    assert "/api/v1/jobs/{job_id}" in paths

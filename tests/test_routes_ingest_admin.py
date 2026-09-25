"""Test API quản trị kho: liệt kê video/job/task + requeue từ giao diện web.

Dùng httpx.AsyncClient + ASGITransport (cùng event loop với fixture `async_session`) như
tests/test_routes_media.py — TestClient chạy app ở loop riêng, xung đột sqlite in-memory.
"""
from __future__ import annotations

import httpx
from httpx import ASGITransport
from sqlalchemy import select

from api.main import create_app
from shared.db import get_session
from shared.ids import new_id
from shared.models import IngestTask, Job, Scene, Video


def _make_client(async_session):
    async def _override_get_session():
        yield async_session

    app = create_app()
    app.dependency_overrides[get_session] = _override_get_session
    return httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _seed_task(async_session, *, status: str, attempts: int = 0, job: Job | None = None):
    if job is None:
        job = Job(job_id=new_id(), kind="ingest_batch", status="running")
        async_session.add(job)
        await async_session.flush()
    task = IngestTask(
        task_id=new_id(),
        job_id=job.job_id,
        source_key=f"news/{new_id()}.mp4",
        status=status,
        attempts=attempts,
        reason="boom" if status == "error" else None,
    )
    async_session.add(task)
    await async_session.flush()
    return job, task


def test_admin_routes_registered():
    paths = set(create_app().openapi()["paths"].keys())
    assert "/api/v1/videos" in paths
    assert "/api/v1/jobs" in paths
    assert "/api/v1/ingest/tasks" in paths
    assert "/api/v1/ingest/tasks/{task_id}/requeue" in paths
    assert "/api/v1/jobs/{job_id}/requeue" in paths
    assert "/api/v1/ingest/requeue-failed" in paths


async def test_list_videos_exposes_name_not_source_key(async_session):
    async_session.add(Video(video_id="v1", source_key="news/2026/clip.mp4"))
    async_session.add(Scene(scene_id="s1", video_id="v1", start_ms=0, end_ms=1000,
                            search_status="indexed"))
    async_session.add(Scene(scene_id="s2", video_id="v1", start_ms=1000, end_ms=2000,
                            search_status="pending"))
    await async_session.commit()

    async with _make_client(async_session) as client:
        resp = await client.get("/api/v1/videos")

    assert resp.status_code == 200
    body = resp.json()
    assert body["meta"]["total"] == 1
    video = body["results"][0]
    assert video["name"] == "clip.mp4"
    assert video["scene_count"] == 2
    assert video["indexed_count"] == 1
    assert video["pending_count"] == 1
    # AD-19: không lộ media-key/path thật trong response
    assert "source_key" not in video
    assert "news/2026" not in resp.text


async def test_list_tasks_filters_by_status(async_session):
    await _seed_task(async_session, status="error")
    await _seed_task(async_session, status="queued")
    await async_session.commit()

    async with _make_client(async_session) as client:
        resp = await client.get("/api/v1/ingest/tasks", params={"status": "error"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["meta"]["total"] == 1
    assert body["results"][0]["status"] == "error"
    assert "source_key" not in body["results"][0]


async def test_requeue_error_task_resets_and_creates_job(async_session):
    old_job, task = await _seed_task(async_session, status="error", attempts=3)
    await async_session.commit()

    async with _make_client(async_session) as client:
        resp = await client.post(f"/api/v1/ingest/tasks/{task.task_id}/requeue")

    assert resp.status_code == 200
    meta = resp.json()["meta"]
    assert meta["requeued"] == 1
    assert meta["job_id"] and meta["job_id"] != old_job.job_id

    refreshed = (
        await async_session.execute(select(IngestTask).where(IngestTask.task_id == task.task_id))
    ).scalar_one()
    assert refreshed.status == "queued"
    assert refreshed.attempts == 0
    assert refreshed.claimed_at is None
    assert refreshed.finished_at is None
    assert refreshed.reason is None
    assert refreshed.job_id == meta["job_id"]


async def test_requeue_unknown_task_returns_404(async_session):
    async with _make_client(async_session) as client:
        resp = await client.post("/api/v1/ingest/tasks/khong-ton-tai/requeue")
    assert resp.status_code == 404


async def test_requeue_skips_in_flight_task(async_session):
    _, task = await _seed_task(async_session, status="claimed")
    await async_session.commit()

    async with _make_client(async_session) as client:
        resp = await client.post(f"/api/v1/ingest/tasks/{task.task_id}/requeue")

    assert resp.status_code == 200
    meta = resp.json()["meta"]
    assert meta["requeued"] == 0 and meta["skipped"] == 1 and meta["job_id"] is None


async def test_requeue_job_only_retryable_by_default(async_session):
    job = Job(job_id=new_id(), kind="ingest_batch", status="done")
    async_session.add(job)
    await async_session.flush()
    _, err = await _seed_task(async_session, status="error", job=job)
    _, done = await _seed_task(async_session, status="done", job=job)
    await async_session.commit()

    async with _make_client(async_session) as client:
        resp = await client.post(f"/api/v1/jobs/{job.job_id}/requeue", json={})

    assert resp.status_code == 200
    meta = resp.json()["meta"]
    assert meta["requeued"] == 1 and meta["matched"] == 1

    err_row = (await async_session.execute(
        select(IngestTask).where(IngestTask.task_id == err.task_id)
    )).scalar_one()
    done_row = (await async_session.execute(
        select(IngestTask).where(IngestTask.task_id == done.task_id)
    )).scalar_one()
    assert err_row.status == "queued"
    assert done_row.status == "done"  # không đụng vì mặc định không gồm 'done'


async def test_requeue_job_include_done(async_session):
    job = Job(job_id=new_id(), kind="ingest_batch", status="done")
    async_session.add(job)
    await async_session.flush()
    _, done = await _seed_task(async_session, status="done", job=job)
    await async_session.commit()

    async with _make_client(async_session) as client:
        resp = await client.post(f"/api/v1/jobs/{job.job_id}/requeue", json={"include_done": True})

    assert resp.status_code == 200
    assert resp.json()["meta"]["requeued"] == 1
    refreshed = (await async_session.execute(
        select(IngestTask).where(IngestTask.task_id == done.task_id)
    )).scalar_one()
    assert refreshed.status == "queued"


async def test_requeue_unknown_job_returns_404(async_session):
    async with _make_client(async_session) as client:
        resp = await client.post("/api/v1/jobs/khong-ton-tai/requeue", json={})
    assert resp.status_code == 404


async def test_requeue_failed_bulk(async_session):
    await _seed_task(async_session, status="error")
    await _seed_task(async_session, status="skipped")
    await _seed_task(async_session, status="done")
    await async_session.commit()

    async with _make_client(async_session) as client:
        resp = await client.post("/api/v1/ingest/requeue-failed")

    assert resp.status_code == 200
    assert resp.json()["meta"]["requeued"] == 2


async def test_list_jobs_reports_status_counts(async_session):
    job = Job(job_id=new_id(), kind="ingest_batch", status="running")
    async_session.add(job)
    await async_session.flush()
    await _seed_task(async_session, status="error", job=job)
    await _seed_task(async_session, status="done", job=job)
    await async_session.commit()

    async with _make_client(async_session) as client:
        resp = await client.get("/api/v1/jobs")

    assert resp.status_code == 200
    row = resp.json()["results"][0]
    assert row["total"] == 2 and row["error"] == 1 and row["done"] == 1

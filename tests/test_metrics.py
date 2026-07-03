from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pipeline.metrics import collect_metrics
from shared.ids import new_id
from shared.models import IngestTask, Job

WINDOW = 300


async def _seed_job_with_tasks(async_session, statuses_and_finished: list[tuple[str, object]]):
    job = Job(job_id=new_id(), kind="ingest_batch", status="running")
    async_session.add(job)
    await async_session.flush()
    for status, finished_at in statuses_and_finished:
        async_session.add(
            IngestTask(
                task_id=new_id(),
                job_id=job.job_id,
                source_key=new_id(),
                status=status,
                finished_at=finished_at,
            )
        )
    await async_session.flush()
    return job.job_id


async def test_queue_depth_counts_queued_and_claimed_only(async_session):
    await _seed_job_with_tasks(
        async_session,
        [("queued", None), ("claimed", None), ("done", datetime.now(timezone.utc)), ("skipped", None)],
    )
    result = await collect_metrics(async_session, window_seconds=WINDOW)
    assert result["queue_depth"] == 2


async def test_throughput_and_error_rate_within_window(async_session):
    now = datetime.now(timezone.utc)
    await _seed_job_with_tasks(
        async_session,
        [
            ("done", now),
            ("done", now),
            ("error", now),
            ("done", now - timedelta(seconds=WINDOW * 2)),  # ngoài cửa sổ
            ("skipped", None),  # không tính (chưa từng qua claim)
        ],
    )
    result = await collect_metrics(async_session, window_seconds=WINDOW)
    # throughput chỉ tính task 'done' (2), KHÔNG gồm 'error' (review fix — trái AC #1 trước đó)
    assert result["ingest_throughput_per_min"] == 2 / (WINDOW / 60)
    # job_error_rate vẫn dùng mẫu số done+error (3) — "trong số task đã hoàn tất"
    assert result["job_error_rate"] == 1 / 3


async def test_error_rate_zero_when_no_completed_tasks_in_window(async_session):
    await _seed_job_with_tasks(async_session, [("queued", None)])
    result = await collect_metrics(async_session, window_seconds=WINDOW)
    assert result["job_error_rate"] == 0.0
    assert result["ingest_throughput_per_min"] == 0.0


async def test_window_seconds_echoed_back(async_session):
    result = await collect_metrics(async_session, window_seconds=WINDOW)
    assert result["window_seconds"] == WINDOW


def test_metrics_route_registered():
    from api.main import create_app

    paths = set(create_app().openapi()["paths"].keys())
    assert "/api/v1/metrics" in paths

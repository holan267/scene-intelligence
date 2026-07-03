from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from pipeline.ingest import claim_next_task, enqueue_batch, job_progress, reclaim_stale_tasks
from pipeline.workers import drain
from shared.models import IngestTask


async def _seed_task(tmp_path, async_session, name="a.mp4"):
    (tmp_path / name).write_bytes(b"x")
    from pipeline.ingest import discover_videos

    res = await enqueue_batch(async_session, discover_videos(tmp_path), tmp_path)
    return res["job_id"]


async def test_claim_sets_claimed_at_and_increments_attempts(tmp_path, async_session):
    await _seed_task(tmp_path, async_session)
    task = await claim_next_task(async_session, skip_locked=False)
    assert task.claimed_at is not None
    assert task.attempts == 1


async def test_reclaim_ignores_task_within_lease(tmp_path, async_session):
    await _seed_task(tmp_path, async_session)
    await claim_next_task(async_session, skip_locked=False)
    result = await reclaim_stale_tasks(
        async_session, lease_seconds=900, max_attempts=3, skip_locked=False
    )
    assert result == {"requeued": 0, "expired": 0, "job_ids": set()}
    task = (await async_session.execute(select(IngestTask))).scalars().first()
    assert task.status == "claimed"


async def test_reclaim_requeues_stale_task_under_max_attempts(tmp_path, async_session):
    job_id = await _seed_task(tmp_path, async_session)
    task = await claim_next_task(async_session, skip_locked=False)
    task.claimed_at = datetime.now(timezone.utc) - timedelta(seconds=1000)  # crash mô phỏng
    await async_session.flush()

    result = await reclaim_stale_tasks(
        async_session, lease_seconds=900, max_attempts=3, skip_locked=False
    )
    assert result == {"requeued": 1, "expired": 0, "job_ids": {job_id}}
    await async_session.refresh(task)
    assert task.status == "queued"
    assert task.claimed_at is None
    assert task.attempts == 1  # không tăng lại khi reclaim, chỉ tăng khi claim


async def test_reclaim_expires_task_at_max_attempts(tmp_path, async_session):
    job_id = await _seed_task(tmp_path, async_session)
    task = await claim_next_task(async_session, skip_locked=False)
    task.attempts = 3  # đã hết lượt thử cho phép (max_attempts=3)
    task.claimed_at = datetime.now(timezone.utc) - timedelta(seconds=1000)
    await async_session.flush()

    result = await reclaim_stale_tasks(
        async_session, lease_seconds=900, max_attempts=3, skip_locked=False
    )
    assert result == {"requeued": 0, "expired": 1, "job_ids": {job_id}}
    await async_session.refresh(task)
    assert task.status == "error"
    assert task.reason == "lease_timeout_exceeded"
    assert task.finished_at is not None


async def test_drain_finalizes_job_when_its_last_task_expires_via_reclaim(tmp_path, async_session):
    # Review fix (AC #3): job không được kẹt 'running' vĩnh viễn khi task cuối bị reclaim expire
    job_id = await _seed_task(tmp_path, async_session)
    task = await claim_next_task(async_session, skip_locked=False)
    task.attempts = 3  # hết lượt thử
    task.claimed_at = datetime.now(timezone.utc) - timedelta(seconds=1000)
    await async_session.flush()

    await drain(async_session, skip_locked=False)

    await async_session.refresh(task)
    assert task.status == "error"
    prog = await job_progress(async_session, job_id)
    assert prog["status"] == "done"  # trước fix: kẹt "running" vĩnh viễn


async def test_requeue_via_enqueue_batch_resets_lease_and_attempts(tmp_path, async_session):
    # Review fix: task đã hết task_max_attempts ở lượt trước không được re-expire ngay
    # ở lần crash đầu tiên của lượt nạp lại mới (mất "3 lần thử/lượt" đã định)
    (tmp_path / "a.mp4").write_bytes(b"x")
    from pipeline.ingest import discover_videos

    paths = discover_videos(tmp_path)
    await enqueue_batch(async_session, paths, tmp_path)
    task = (await async_session.execute(select(IngestTask))).scalars().first()
    task.status = "error"
    task.reason = "lease_timeout_exceeded"
    task.attempts = 3
    task.claimed_at = datetime.now(timezone.utc) - timedelta(seconds=1000)
    task.finished_at = datetime.now(timezone.utc)
    await async_session.flush()

    await enqueue_batch(async_session, paths, tmp_path)
    await async_session.refresh(task)
    assert task.status == "queued"
    assert task.attempts == 0
    assert task.claimed_at is None
    assert task.finished_at is None


async def test_reclaimed_task_can_be_claimed_again_by_another_worker(tmp_path, async_session):
    # AC #3: worker crash -> task requeue -> worker khác claim lại được, không mất việc
    await _seed_task(tmp_path, async_session)
    first_claim = await claim_next_task(async_session, skip_locked=False)
    first_claim.claimed_at = datetime.now(timezone.utc) - timedelta(seconds=1000)
    await async_session.flush()

    await reclaim_stale_tasks(async_session, lease_seconds=900, max_attempts=3, skip_locked=False)
    second_claim = await claim_next_task(async_session, skip_locked=False)
    assert second_claim is not None
    assert second_claim.task_id == first_claim.task_id
    assert second_claim.attempts == 2

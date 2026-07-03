"""Logic ingest theo lô (Story 1.2 — FR-1, AD-5, AD-10, AD-18).

- discover_videos: quét thư mục.
- enqueue_batch: tạo Job + Task, dedupe theo source_key (idempotent), bỏ qua tệp lỗi.
- job_progress: đếm tiến độ.
- claim_next_task: orchestrator lấy task kế (Postgres SKIP LOCKED, fallback cho sqlite/test).
- finalize_job: orchestrator kết luận job done (worker KHÔNG tự ghi job.status — AD-18).
"""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.ids import new_id
from shared.models import IngestTask, Job

VIDEO_EXTS = {".mp4", ".mov", ".mxf", ".mkv", ".avi", ".ts", ".m4v", ".mpg", ".mpeg", ".webm"}


def discover_videos(root: str | Path) -> list[Path]:
    """Quét đệ quy, trả các tệp video (theo đuôi)."""
    root_path = Path(root)
    if not root_path.is_dir():
        return []
    return sorted(
        p for p in root_path.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTS
    )


def source_key_for(path: str | Path, root: str | Path) -> str:
    """media-key ổn định (AD-23): đường dẫn tương đối so với root batch; fallback = tên tệp."""
    p = Path(path)
    try:
        return p.resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return p.name


def _readable(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            f.read(1)
        return True
    except OSError:
        return False


async def enqueue_batch(
    session: AsyncSession, paths: Iterable[str | Path], root: str | Path
) -> dict:
    """Tạo Job + Task cho lô. Dedupe theo source_key; tệp lỗi -> skipped, không dừng lô."""
    job = Job(job_id=new_id(), kind="ingest_batch", status="queued")
    session.add(job)
    await session.flush()

    existing = set((await session.execute(select(IngestTask.source_key))).scalars().all())
    seen: set[str] = set()
    queued = duplicates = invalid = 0

    for raw in paths:
        p = Path(raw)
        key = source_key_for(p, root)
        if key in existing or key in seen:
            duplicates += 1
            continue
        seen.add(key)
        if not (p.is_file() and _readable(p)):
            session.add(
                IngestTask(
                    task_id=new_id(),
                    job_id=job.job_id,
                    source_key=key,
                    status="skipped",
                    reason="unreadable-or-missing",
                )
            )
            invalid += 1
            continue
        session.add(
            IngestTask(task_id=new_id(), job_id=job.job_id, source_key=key, status="queued")
        )
        queued += 1

    job.status = "running" if queued else "done"
    await session.flush()
    return {"job_id": job.job_id, "queued": queued, "duplicates": duplicates, "invalid": invalid}


async def job_progress(session: AsyncSession, job_id: str) -> dict | None:
    """Đếm task theo trạng thái cho một job (None nếu job không tồn tại)."""
    job = await session.get(Job, job_id)
    if job is None:
        return None
    rows = (
        await session.execute(
            select(IngestTask.status, func.count())
            .where(IngestTask.job_id == job_id)
            .group_by(IngestTask.status)
        )
    ).all()
    counts = {status: n for status, n in rows}
    return {
        "job_id": job_id,
        "status": job.status,
        "total": sum(counts.values()),
        "done": counts.get("done", 0),
        "queued": counts.get("queued", 0),
        "claimed": counts.get("claimed", 0),
        "skipped": counts.get("skipped", 0),
        "error": counts.get("error", 0),
    }


async def claim_next_task(
    session: AsyncSession, *, skip_locked: bool = True
) -> IngestTask | None:
    """Lấy task 'queued' kế tiếp và đánh dấu 'claimed'.

    Postgres dùng FOR UPDATE SKIP LOCKED để nhiều worker không tranh nhau; test/sqlite
    truyền skip_locked=False.
    """
    q = (
        select(IngestTask)
        .where(IngestTask.status == "queued")
        .order_by(IngestTask.created_at)
        .limit(1)
    )
    if skip_locked:
        q = q.with_for_update(skip_locked=True)
    task = (await session.execute(q)).scalars().first()
    if task is None:
        return None
    task.status = "claimed"
    await session.flush()
    return task


async def finalize_job(session: AsyncSession, job_id: str) -> None:
    """Orchestrator: job -> done khi không còn task queued/claimed (AD-18)."""
    prog = await job_progress(session, job_id)
    if prog and prog["queued"] == 0 and prog["claimed"] == 0:
        job = await session.get(Job, job_id)
        if job is not None:
            job.status = "done"
            await session.flush()

"""Logic ingest theo lô (Story 1.2 — FR-1, AD-5, AD-10, AD-18, AD-23).

- resolve_source_dir: giới hạn nguồn trong MEDIA_ROOT (bảo mật/DoS — D1).
- discover_videos: quét thư mục.
- source_key_for: media-key = path tương-đối MEDIA_ROOT (AD-23); ngoài root -> lỗi.
- enqueue_batch: tạo Job + Task, dedupe; task skipped/error được RE-QUEUE khi nạp lại
  (lỗi tạm thời không thành bỏ-qua-vĩnh-viễn).
- claim_next_task: SKIP LOCKED (Postgres), có tiebreaker; finalize_job: orchestrator (AD-18).
- reclaim_stale_tasks (Story 1.7, NFR-2): orchestrator requeue/expire task 'claimed' quá lease
  khi worker crash — không mất việc (xem pipeline/workers.py::drain, gọi mỗi vòng lặp).

Ghi chú (defer): `existing` nạp toàn bộ source_key vào bộ nhớ (chưa bound); an toàn cạnh
tranh đa tiến trình cần INSERT ON CONFLICT — xem deferred-work.md.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import get_settings
from shared.ids import new_id
from shared.models import IngestTask, Job

VIDEO_EXTS = {".mp4", ".mov", ".mxf", ".mkv", ".avi", ".ts", ".m4v", ".mpg", ".mpeg", ".webm"}
_RETRYABLE = {"skipped", "error"}


def _media_root() -> Path:
    return Path(get_settings().media_root).resolve()


def resolve_source_dir(source_dir: str | Path, media_root: str | Path | None = None) -> Path:
    """Trả thư mục nguồn ĐÃ xác thực nằm trong MEDIA_ROOT và tồn tại; nếu không -> ValueError."""
    root = Path(media_root).resolve() if media_root is not None else _media_root()
    target = Path(source_dir).resolve()
    if root != target and root not in target.parents:
        raise ValueError(f"source_dir ngoài MEDIA_ROOT: {source_dir!r}")
    if not target.is_dir():
        raise ValueError(f"source_dir không tồn tại hoặc không phải thư mục: {source_dir!r}")
    return target


def discover_videos(root: str | Path) -> list[Path]:
    root_path = Path(root)
    if not root_path.is_dir():
        return []
    return sorted(p for p in root_path.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTS)


def source_key_for(path: str | Path, media_root: str | Path) -> str:
    """media-key ổn định (AD-23) = path tương-đối MEDIA_ROOT. Ngoài root -> ValueError."""
    p = Path(path).resolve()
    root = Path(media_root).resolve()
    try:
        return p.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError(f"path ngoài MEDIA_ROOT: {path!r}") from exc


def _readable(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            f.read(1)
        return True
    except OSError:
        return False


async def enqueue_batch(
    session: AsyncSession, paths: Iterable[str | Path], media_root: str | Path
) -> dict:
    """Tạo Job + Task cho lô. Dedupe theo source_key; task cũ skipped/error được re-queue."""
    job = Job(job_id=new_id(), kind="ingest_batch", status="queued")
    session.add(job)
    await session.flush()

    by_key = {t.source_key: t for t in (await session.execute(select(IngestTask))).scalars().all()}
    seen: set[str] = set()
    queued = duplicates = invalid = 0

    for raw in paths:
        p = Path(raw)
        key = source_key_for(p, media_root)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)

        existing = by_key.get(key)
        if existing is not None and existing.status not in _RETRYABLE:
            duplicates += 1  # done/queued/claimed -> đã có, bỏ qua
            continue

        readable = p.is_file() and _readable(p)
        if existing is not None:  # re-queue task cũ skipped/error
            existing.job_id = job.job_id
            # Lượt nạp mới -> reset lease/attempts (Story 1.7): nếu không, task đã hết
            # task_max_attempts ở lượt trước bị reclaim expire ngay ở lần crash đầu của lượt này.
            existing.claimed_at = None
            existing.attempts = 0
            existing.finished_at = None
            if readable:
                existing.status, existing.reason = "queued", None
                queued += 1
            else:
                existing.status, existing.reason = "skipped", "unreadable-or-missing"
                invalid += 1
            continue

        if not readable:
            session.add(IngestTask(task_id=new_id(), job_id=job.job_id, source_key=key,
                                   status="skipped", reason="unreadable-or-missing"))
            invalid += 1
        else:
            session.add(IngestTask(task_id=new_id(), job_id=job.job_id, source_key=key, status="queued"))
            queued += 1

    job.status = "running" if queued else "done"
    await session.flush()
    return {"job_id": job.job_id, "queued": queued, "duplicates": duplicates, "invalid": invalid}


async def job_progress(session: AsyncSession, job_id: str) -> dict | None:
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
    counts = dict(rows)
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


async def claim_next_task(session: AsyncSession, *, skip_locked: bool = True) -> IngestTask | None:
    """Lấy task 'queued' kế và đánh dấu 'claimed'. Tiebreaker task_id -> thứ tự xác định."""
    q = (
        select(IngestTask)
        .where(IngestTask.status == "queued")
        .order_by(IngestTask.created_at, IngestTask.task_id)
        .limit(1)
    )
    if skip_locked:
        q = q.with_for_update(skip_locked=True)
    task = (await session.execute(q)).scalars().first()
    if task is None:
        return None
    task.status = "claimed"
    task.claimed_at = datetime.now(timezone.utc)
    task.attempts = (task.attempts or 0) + 1
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


async def reclaim_stale_tasks(
    session: AsyncSession, *, lease_seconds: int, max_attempts: int, skip_locked: bool = True
) -> dict:
    """Orchestrator (AD-18): requeue/expire task 'claimed' quá lease (worker crash, NFR-2).

    Task còn dưới `max_attempts` -> về 'queued' để worker khác claim lại (không mất việc).
    Task đã hết lượt thử -> 'error' (reason=lease_timeout_exceeded), không kẹt vĩnh viễn.
    Trả về `job_ids` của MỌI task bị đụng (requeue lẫn expire) để caller (drain()) finalize
    đúng job — nhánh expire không bao giờ được claim lại nên job của nó phải được finalize
    ngay từ đây, không đợi vòng claim sau.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=lease_seconds)
    q = select(IngestTask).where(IngestTask.status == "claimed", IngestTask.claimed_at < cutoff)
    if skip_locked:
        q = q.with_for_update(skip_locked=True)
    stale = (await session.execute(q)).scalars().all()

    requeued = expired = 0
    job_ids: set[str] = set()
    for task in stale:
        job_ids.add(task.job_id)
        if task.attempts < max_attempts:
            task.status, task.claimed_at = "queued", None
            requeued += 1
        else:
            task.status = "error"
            task.reason = "lease_timeout_exceeded"
            task.finished_at = datetime.now(timezone.utc)
            expired += 1
    await session.flush()
    return {"requeued": requeued, "expired": expired, "job_ids": job_ids}

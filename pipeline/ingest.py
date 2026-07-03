"""Logic ingest theo lô (Story 1.2 — FR-1, AD-5, AD-10, AD-18, AD-23).

- resolve_source_dir: giới hạn nguồn trong MEDIA_ROOT (bảo mật/DoS — D1).
- discover_videos: quét thư mục.
- source_key_for: media-key = path tương-đối MEDIA_ROOT (AD-23); ngoài root -> lỗi.
- enqueue_batch: tạo Job + Task, dedupe; task skipped/error được RE-QUEUE khi nạp lại
  (lỗi tạm thời không thành bỏ-qua-vĩnh-viễn).
- claim_next_task: SKIP LOCKED (Postgres), có tiebreaker; finalize_job: orchestrator (AD-18).

Ghi chú (defer): `existing` nạp toàn bộ source_key vào bộ nhớ (chưa bound); an toàn cạnh
tranh đa tiến trình cần INSERT ON CONFLICT — xem deferred-work.md.
"""
from __future__ import annotations

from collections.abc import Iterable
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

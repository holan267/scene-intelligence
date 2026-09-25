"""Logic ingest theo lô (Story 1.2 — FR-1, AD-5, AD-10, AD-18, AD-23).

- resolve_source_dir: giới hạn nguồn trong MEDIA_ROOT (bảo mật/DoS — D1).
- discover_videos: quét thư mục.
- source_key_for: media-key = path tương-đối MEDIA_ROOT (AD-23); ngoài root -> lỗi.
- enqueue_batch: tạo Job + Task, dedupe; task skipped/error được RE-QUEUE khi nạp lại
  (lỗi tạm thời không thành bỏ-qua-vĩnh-viễn).
- claim_next_task: SKIP LOCKED (Postgres), có tiebreaker; finalize_job: orchestrator (AD-18).
- reclaim_stale_tasks (Story 1.7, NFR-2): orchestrator requeue/expire task 'claimed' quá lease
  khi worker crash — không mất việc (xem pipeline/workers.py::drain, gọi mỗi vòng lặp).
- Quản trị kho (giao diện web): list_videos/list_jobs/list_tasks để hiển thị, và
  requeue_task/requeue_job/requeue_failed để đẩy task lỗi/bỏ-qua trở lại hàng đợi dưới một
  Job mới — cùng khuôn orchestrator AD-18 với enqueue_batch/reclaim_stale_tasks.

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
from shared.models import IngestTask, Job, Scene, Video

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


# --- Quản trị kho (giao diện web): liệt kê video/job/task + requeue từ UI ---------------
# UI KHÔNG nhận media-key/path thật (AD-19) — mọi dict trả ra chỉ có `name` = tên tệp
# (basename của source_key) để người vận hành nhận diện, không có source_key đầy đủ.

_IN_FLIGHT = {"queued", "claimed"}


def _display_name(source_key: str) -> str:
    return Path(source_key).name


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


async def list_videos(session: AsyncSession, *, limit: int = 50, offset: int = 0) -> dict:
    """Liệt kê Video kèm số Scene + số Scene đã index (màn quản lý video)."""
    total = (await session.execute(select(func.count()).select_from(Video))).scalar_one()
    rows = (
        await session.execute(
            select(
                Video.video_id,
                Video.source_key,
                Video.framerate,
                Video.created_at,
                func.count(Scene.scene_id),
            )
            .outerjoin(Scene, Scene.video_id == Video.video_id)
            .group_by(Video.video_id, Video.source_key, Video.framerate, Video.created_at)
            .order_by(Video.created_at.desc(), Video.video_id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()

    video_ids = [row[0] for row in rows]
    indexed: dict[str, int] = {}
    if video_ids:
        idx_rows = (
            await session.execute(
                select(Scene.video_id, func.count())
                .where(Scene.video_id.in_(video_ids), Scene.search_status == "indexed")
                .group_by(Scene.video_id)
            )
        ).all()
        indexed = dict(idx_rows)

    results = [
        {
            "video_id": video_id,
            "name": _display_name(source_key),
            "framerate": framerate,
            "created_at": _iso(created_at),
            "scene_count": scene_count,
            "indexed_count": indexed.get(video_id, 0),
            "pending_count": scene_count - indexed.get(video_id, 0),
        }
        for video_id, source_key, framerate, created_at, scene_count in rows
    ]
    return {"results": results, "total": total}


async def list_jobs(session: AsyncSession, *, limit: int = 50, offset: int = 0) -> dict:
    """Liệt kê Job kèm phân bố trạng thái task (màn ingest status)."""
    total = (await session.execute(select(func.count()).select_from(Job))).scalar_one()
    jobs = (
        await session.execute(
            select(Job)
            .order_by(Job.created_at.desc(), Job.job_id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()
    counts = (
        await session.execute(
            select(IngestTask.job_id, IngestTask.status, func.count())
            .group_by(IngestTask.job_id, IngestTask.status)
        )
    ).all()
    by_job: dict[str, dict[str, int]] = {}
    for job_id, status, n in counts:
        by_job.setdefault(job_id, {})[status] = n

    results = []
    for job in jobs:
        c = by_job.get(job.job_id, {})
        results.append(
            {
                "job_id": job.job_id,
                "kind": job.kind,
                "status": job.status,
                "created_at": _iso(job.created_at),
                "total": sum(c.values()),
                "done": c.get("done", 0),
                "queued": c.get("queued", 0),
                "claimed": c.get("claimed", 0),
                "skipped": c.get("skipped", 0),
                "error": c.get("error", 0),
            }
        )
    return {"results": results, "total": total}


async def list_tasks(
    session: AsyncSession, *, status: str | None = None, limit: int = 50, offset: int = 0
) -> dict:
    """Liệt kê IngestTask (lọc theo status) — nguồn cho bảng task + nút requeue."""
    conds = [IngestTask.status == status] if status else []
    total_q = select(func.count()).select_from(IngestTask)
    q = select(IngestTask).order_by(IngestTask.created_at.desc(), IngestTask.task_id.desc())
    if conds:
        total_q = total_q.where(*conds)
        q = q.where(*conds)
    total = (await session.execute(total_q)).scalar_one()
    tasks = (await session.execute(q.limit(limit).offset(offset))).scalars().all()
    results = [
        {
            "task_id": t.task_id,
            "job_id": t.job_id,
            "name": _display_name(t.source_key),
            "status": t.status,
            "reason": t.reason,
            "attempts": t.attempts,
            "video_id": t.video_id,
            "claimed_at": _iso(t.claimed_at),
            "finished_at": _iso(t.finished_at),
            "created_at": _iso(t.created_at),
        }
        for t in tasks
    ]
    return {"results": results, "total": total}


async def _requeue(session: AsyncSession, tasks: list[IngestTask]) -> dict:
    """Đưa các task đã chọn về 'queued' dưới MỘT Job mới (đơn vị orchestration AD-18).

    Task đang 'queued'/'claimed' bị bỏ qua: chúng đang chờ/đang chạy, requeue nữa sẽ khiến
    worker thứ hai xử lý trùng. Reset attempts/claimed_at/finished_at/reason như đường
    `enqueue_batch` (Story 1.7) để lượt chạy mới có trọn `task_max_attempts`.
    """
    runnable = [t for t in tasks if t.status not in _IN_FLIGHT]
    if not runnable:
        return {"job_id": None, "requeued": 0, "skipped": len(tasks)}

    job = Job(job_id=new_id(), kind="requeue", status="running")
    session.add(job)
    await session.flush()
    for task in runnable:
        task.job_id = job.job_id
        task.status = "queued"
        task.reason = None
        task.claimed_at = None
        task.attempts = 0
        task.finished_at = None
    await session.flush()
    return {"job_id": job.job_id, "requeued": len(runnable), "skipped": len(tasks) - len(runnable)}


async def requeue_task(session: AsyncSession, task_id: str) -> dict | None:
    """Requeue một task theo id. None nếu task không tồn tại."""
    task = await session.get(IngestTask, task_id)
    if task is None:
        return None
    return await _requeue(session, [task])


async def requeue_job(session: AsyncSession, job_id: str, *, include_done: bool = False) -> dict | None:
    """Requeue task lỗi/bỏ-qua của một Job (tuỳ chọn gồm cả task 'done' để chạy lại toàn bộ).

    None nếu job không tồn tại. Task queued/claimed của job luôn được giữ nguyên.
    """
    job = await session.get(Job, job_id)
    if job is None:
        return None
    tasks = (
        await session.execute(select(IngestTask).where(IngestTask.job_id == job_id))
    ).scalars().all()
    targets = [
        t for t in tasks if t.status in _RETRYABLE or (include_done and t.status == "done")
    ]
    result = await _requeue(session, targets)
    result["matched"] = len(targets)
    return result


async def requeue_failed(session: AsyncSession) -> dict:
    """Requeue MỌI task 'skipped'/'error' toàn kho (nút "Requeue tất cả lỗi")."""
    tasks = (
        await session.execute(select(IngestTask).where(IngestTask.status.in_(_RETRYABLE)))
    ).scalars().all()
    return await _requeue(session, tasks)

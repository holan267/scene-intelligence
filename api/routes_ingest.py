"""API nạp lô + tiến độ job + quản trị kho (Story 1.2/1.7, AD-13).

UI/thủ thư gọi qua REST/JSON: nạp lô, xem tiến độ job, liệt kê video/job/task và requeue
task lỗi/bỏ-qua trở lại hàng đợi. UI không bao giờ nhận media-key/path thật (AD-19) —
các endpoint liệt kê chỉ trả `name` = tên tệp để nhận diện.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.envelope import ok
from pipeline.ingest import (
    discover_videos,
    enqueue_batch,
    job_progress,
    list_jobs,
    list_tasks,
    list_videos,
    requeue_failed,
    requeue_job,
    requeue_task,
    resolve_source_dir,
)
from shared.config import get_settings
from shared.db import get_session

router = APIRouter(prefix="/api/v1")


class IngestRequest(BaseModel):
    source_dir: str


class RequeueJobRequest(BaseModel):
    # Mặc định chỉ requeue task lỗi/bỏ-qua; true = chạy lại cả task đã 'done' (re-index).
    include_done: bool = False


@router.post("/ingest", responses={400: {"description": "source_dir không hợp lệ"}})
async def ingest(req: IngestRequest, session: Annotated[AsyncSession, Depends(get_session)]) -> dict:
    media_root = get_settings().media_root
    try:  # D1: giới hạn trong MEDIA_ROOT + P2.6: báo lỗi nếu dir sai/thiếu
        source_dir = resolve_source_dir(req.source_dir, media_root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result = await enqueue_batch(session, discover_videos(source_dir), media_root)
    await session.commit()
    return ok(meta=result)


@router.get("/jobs/{job_id}", responses={404: {"description": "job not found"}})
async def job_status(job_id: str, session: Annotated[AsyncSession, Depends(get_session)]) -> dict:
    prog = await job_progress(session, job_id)
    if prog is None:
        raise HTTPException(status_code=404, detail="job not found")
    return ok(meta=prog)


@router.get("/jobs")
async def jobs(
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    data = await list_jobs(session, limit=limit, offset=offset)
    return ok(results=data["results"], meta={"total": data["total"], "limit": limit, "offset": offset})


@router.get("/videos")
async def videos(
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    data = await list_videos(session, limit=limit, offset=offset)
    return ok(results=data["results"], meta={"total": data["total"], "limit": limit, "offset": offset})


@router.get("/ingest/tasks")
async def tasks(
    session: Annotated[AsyncSession, Depends(get_session)],
    status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    data = await list_tasks(session, status=status, limit=limit, offset=offset)
    return ok(results=data["results"], meta={"total": data["total"], "limit": limit, "offset": offset})


@router.post(
    "/ingest/tasks/{task_id}/requeue",
    responses={404: {"description": "task not found"}},
)
async def requeue_one(
    task_id: str, session: Annotated[AsyncSession, Depends(get_session)]
) -> dict:
    result = await requeue_task(session, task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="task not found")
    await session.commit()
    return ok(meta=result)


@router.post("/jobs/{job_id}/requeue", responses={404: {"description": "job not found"}})
async def requeue_a_job(
    job_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    req: RequeueJobRequest = RequeueJobRequest(),
) -> dict:
    result = await requeue_job(session, job_id, include_done=req.include_done)
    if result is None:
        raise HTTPException(status_code=404, detail="job not found")
    await session.commit()
    return ok(meta=result)


@router.post("/ingest/requeue-failed")
async def requeue_all_failed(session: Annotated[AsyncSession, Depends(get_session)]) -> dict:
    result = await requeue_failed(session)
    await session.commit()
    return ok(meta=result)

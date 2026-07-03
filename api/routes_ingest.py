"""API nạp lô + tiến độ job (Story 1.2, AD-13). UI/thủ thư gọi qua REST/JSON."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.envelope import ok
from pipeline.ingest import discover_videos, enqueue_batch, job_progress, resolve_source_dir
from shared.config import get_settings
from shared.db import get_session

router = APIRouter(prefix="/api/v1")


class IngestRequest(BaseModel):
    source_dir: str


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

"""Endpoint metrics vận hành (Story 1.7, NFR-8): thông lượng, độ sâu hàng đợi, tỷ lệ lỗi."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.envelope import ok
from pipeline.metrics import collect_metrics
from shared.config import get_settings
from shared.db import get_session

router = APIRouter(prefix="/api/v1")


@router.get("/metrics")
async def metrics(session: Annotated[AsyncSession, Depends(get_session)]) -> dict:
    result = await collect_metrics(session, window_seconds=get_settings().metrics_window_seconds)
    return ok(meta=result)

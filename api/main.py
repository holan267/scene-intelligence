"""API Gateway — ranh giới cứng UI<->lõi (AD-13, AD-14).

Prefix /api/v1, envelope chuẩn. Story 1.1 chỉ cần endpoint health kiểm tra 3 kho.
Các endpoint ingest/search thêm ở story sau (AD-2 tách write/read).
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI

from api.envelope import ok
from api.routes_ingest import router as ingest_router
from shared.db import check_db
from shared.storage import build_storage


async def db_health() -> bool:
    """Dependency: Postgres kết nối được? (override trong test)."""
    return await check_db()


def storage_health() -> bool:
    """Dependency: storage-port media khả dụng? (override trong test)."""
    store = build_storage()
    check = getattr(store, "healthcheck", None)
    return bool(check()) if callable(check) else True


def create_app() -> FastAPI:
    app = FastAPI(title="Scene Intelligence", version="0.1.0")
    v1 = APIRouter(prefix="/api/v1")

    @v1.get("/health")
    async def health(
        db_ok: Annotated[bool, Depends(db_health)],
        store_ok: Annotated[bool, Depends(storage_health)],
    ) -> dict:
        return ok(
            meta={
                "status": "ok",
                "stores": {"postgres": db_ok, "media_storage": store_ok},
            }
        )

    app.include_router(v1)
    app.include_router(ingest_router)
    return app


app = create_app()

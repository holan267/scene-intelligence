"""API Gateway — ranh giới cứng UI<->lõi (AD-13, AD-14).

Prefix /api/v1, envelope chuẩn, error-shape chung. Story 1.1: health kiểm tra 3 kho.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.envelope import err, ok
from api.routes_ingest import router as ingest_router
from api.routes_metrics import router as metrics_router
from shared.db import check_db
from shared.logging import configure_logging
from shared.storage import build_storage


async def db_health() -> bool:
    """Dependency: Postgres kết nối được? (override trong test)."""
    return await check_db()


def storage_health() -> bool:
    """Dependency: storage-port media ghi được? Không ném lỗi -> health luôn báo được trạng thái."""
    try:
        return bool(build_storage().healthcheck())
    except Exception:  # noqa: BLE001 - health không được ném ra 500
        return False


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="Scene Intelligence", version="0.1.0")
    v1 = APIRouter(prefix="/api/v1")

    @v1.get("/health")
    async def health(
        db_ok: Annotated[bool, Depends(db_health)],
        store_ok: Annotated[bool, Depends(storage_health)],
    ) -> dict:
        status = "ok" if (db_ok and store_ok) else "degraded"
        return ok(meta={"status": status, "stores": {"postgres": db_ok, "media_storage": store_ok}})

    @app.exception_handler(StarletteHTTPException)
    async def http_exc_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # Bọc lỗi theo error-shape chung (AD-13) thay vì {detail}
        return JSONResponse(status_code=exc.status_code, content=err(str(exc.status_code), exc.detail))

    app.include_router(v1)
    app.include_router(ingest_router)
    app.include_router(metrics_router)
    return app


app = create_app()

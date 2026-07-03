from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.main import create_app, db_health, storage_health
from shared.models import Base


@pytest.fixture
def client() -> TestClient:
    """Client với health-deps override -> chạy được không cần Postgres thật."""
    app = create_app()

    async def _db_ok() -> bool:
        return True

    def _store_ok() -> bool:
        return True

    app.dependency_overrides[db_health] = _db_ok
    app.dependency_overrides[storage_health] = _store_ok
    with TestClient(app) as c:
        yield c


@pytest_asyncio.fixture
async def async_session():
    """AsyncSession trên sqlite in-memory (test logic DB không cần Postgres)."""
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app, db_health, storage_health


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

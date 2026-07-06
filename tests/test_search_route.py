from __future__ import annotations

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from api.routes_search import SearchRequest, search_endpoint
from shared.filters import SceneFilters


def test_search_route_registered():
    from api.main import create_app

    paths = set(create_app().openapi()["paths"].keys())
    assert "/api/v1/search" in paths


def test_search_request_rejects_blank_query():
    with pytest.raises(ValidationError):
        SearchRequest(query="   ")


def test_search_request_strips_query():
    assert SearchRequest(query="  câu hỏi  ").query == "câu hỏi"


@pytest.mark.parametrize("limit", [0, -1, 101])
def test_search_request_rejects_out_of_range_limit(limit):
    with pytest.raises(ValidationError):
        SearchRequest(query="q", limit=limit)


def test_search_request_defaults_filters_to_none():
    assert SearchRequest(query="q").filters is None


def test_search_request_accepts_nested_filters():
    req = SearchRequest(query="q", filters={"has_person": True})
    assert req.filters == SceneFilters(has_person=True)


def test_search_request_rejects_invalid_nested_filters():
    # Validation kế thừa từ SceneFilters (AD-21) — route không tự viết logic riêng
    with pytest.raises(ValidationError):
        SearchRequest(query="q", filters={"max_duration_ms": -1})


async def test_search_endpoint_forwards_filters(async_session, monkeypatch):
    import api.routes_search as routes_search_module

    captured = {}

    async def _fake_search(*args, **kwargs):
        captured.update(kwargs)
        return [], {"next_cursor": None, "count": 0}

    monkeypatch.setattr(routes_search_module, "search", _fake_search)

    filters = SceneFilters(min_duration_ms=1000)
    await search_endpoint(SearchRequest(query="q", filters=filters), async_session)
    assert captured["filters"] == filters


async def test_search_endpoint_maps_runtime_error_to_502(async_session, monkeypatch):
    # Review fix: lỗi embed/rerank (RuntimeError) phải thành HTTPException(502), không phải 500 thô
    import api.routes_search as routes_search_module

    async def _raise(*args, **kwargs):
        raise RuntimeError("model server lỗi")

    monkeypatch.setattr(routes_search_module, "search", _raise)

    with pytest.raises(HTTPException) as exc_info:
        await search_endpoint(SearchRequest(query="câu hỏi"), async_session)
    assert exc_info.value.status_code == 502

"""API tìm kiếm ngữ nghĩa (Story 2.1, FR-6, AD-13)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from api.envelope import ok
from search.query_embed import BgeM3QueryEmbedder
from search.rerank import BgeRerankerV2M3
from search.service import search
from shared.config import get_settings
from shared.db import get_session

router = APIRouter(prefix="/api/v1")


class SearchRequest(BaseModel):
    query: str
    limit: int = Field(default=10, ge=1, le=100)

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("query không được rỗng")
        return v


@router.post("/search", responses={502: {"description": "embed/rerank model server lỗi"}})
async def search_endpoint(
    req: SearchRequest, session: Annotated[AsyncSession, Depends(get_session)]
) -> dict:
    settings = get_settings()
    embedder = BgeM3QueryEmbedder(settings)
    reranker = BgeRerankerV2M3(settings)
    try:
        results, meta = await search(
            session,
            embedder,
            reranker,
            req.query,
            limit=req.limit,
            pool_size=settings.search_pool_size,
            gap_threshold=settings.rerank_skip_gap,
            k=settings.rrf_k,
        )
    except RuntimeError as exc:  # lỗi HTTP/hình dạng response từ embed/rerank model server
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ok(results=results, meta=meta)

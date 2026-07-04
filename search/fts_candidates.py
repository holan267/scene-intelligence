"""FTS candidate fetch (Story 2.2, FR-8, AD-8, AD-17).

⚠️ Chỉ chạy đúng trên Postgres thật — `to_tsvector`/`phraseto_tsquery`/`ts_headline`/
`ts_rank_cd` là hàm riêng Postgres, không có trên sqlite. Cùng ranh giới Postgres-only như
`search/candidates.py::fetch_ann_candidates` (Story 2.1); mọi logic khác (search/rank.py,
search/fuse.py) là hàm thuần nhận list[dict] để unit-test không cần Postgres.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import Scene, SceneEmbedding

# 'simple' (tokenize + lowercase, không stemming): Postgres không có dictionary tiếng Việt
# built-in; 'simple' phù hợp với AC "chính xác cụm từ" và tránh vi phạm AD-9 (không lỡ dùng
# 'english' stem sai ngôn ngữ). PHẢI khớp đúng config dùng ở migration 0009 để dùng được index.
_TS_CONFIG = "simple"


async def fetch_fts_candidates(  # pragma: no cover - phụ thuộc Postgres thật
    session: AsyncSession, query: str, *, pool_size: int
) -> list[dict]:
    """Top-`pool_size` Scene `indexed` khớp cụm từ chính xác (phraseto_tsquery) trong `fts_text`.

    Dùng phraseto_tsquery (không phải plainto_tsquery/websearch_to_tsquery) để giữ đúng thứ tự
    liền kề của cụm từ (AC: "cụm từ" — vd "World Cup" phải khớp theo đúng thứ tự).
    """
    tsvector = func.to_tsvector(_TS_CONFIG, SceneEmbedding.fts_text)
    tsquery = func.phraseto_tsquery(_TS_CONFIG, query)
    rank_expr = func.ts_rank_cd(tsvector, tsquery).label("fts_rank_score")

    # Code review fix: ts_headline (re-tokenize toàn văn bản) PHẢI tính SAU khi ORDER BY+LIMIT
    # đã cắt còn pool_size dòng — nếu tính ở cùng tầng SELECT với WHERE/ORDER BY/LIMIT, Postgres
    # phải materialize ts_headline cho MỌI dòng khớp WHERE trước khi Sort/Limit kịp cắt bớt
    # (Limit nằm trên Sort, Sort cần đủ target-list của toàn bộ dòng khớp trước khi sắp xếp) —
    # biến chi phí O(pool_size) thành O(số dòng khớp). Dùng subquery con để LIMIT trước, chỉ
    # tính ts_headline trên đúng pool_size dòng còn lại ở tầng ngoài (đúng khuyến nghị của
    # Postgres docs — Text Search § Highlighting Results).
    limited = (
        select(
            Scene.scene_id,
            Scene.video_id,
            Scene.start_ms,
            Scene.end_ms,
            Scene.scene_document,
            SceneEmbedding.doc_version,
            SceneEmbedding.fts_text,
            rank_expr,
        )
        .join(SceneEmbedding, SceneEmbedding.scene_id == Scene.scene_id)
        .where(Scene.search_status == "indexed", tsvector.op("@@")(tsquery))
        .order_by(rank_expr.desc())
        .limit(pool_size)
        .subquery()
    )
    snippet_expr = func.ts_headline(
        _TS_CONFIG, limited.c.fts_text, tsquery, "StartSel=**,StopSel=**"
    ).label("fts_snippet")

    q = (
        select(
            limited.c.scene_id,
            limited.c.video_id,
            limited.c.start_ms,
            limited.c.end_ms,
            limited.c.scene_document,
            limited.c.doc_version,
            limited.c.fts_rank_score,
            snippet_expr,
        )
        .order_by(limited.c.fts_rank_score.desc())
    )
    rows = (await session.execute(q)).all()
    return [
        {
            "scene_id": r.scene_id,
            "video_id": r.video_id,
            "start_ms": r.start_ms,
            "end_ms": r.end_ms,
            "scene_document": r.scene_document,
            "doc_version": r.doc_version,
            "fts_rank_score": r.fts_rank_score,
            "fts_snippet": r.fts_snippet,
        }
        for r in rows
    ]

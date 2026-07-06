"""Review fix (Story 2.3): khoá AC #3 bằng test tự động thay vì chỉ verify thủ công.

Dùng fake session (chỉ cần `async def execute(self, stmt)`) để bắt statement thật
mà `fetch_ann_candidates`/`fetch_fts_candidates` build, rồi compile (dialect
postgresql, không cần Postgres sống) để xác nhận predicate filter nằm TRƯỚC
`ORDER BY`/`LIMIT` — đúng thứ tự phễu AD-8, không phải lọc sau khi đã cắt pool.
"""
from __future__ import annotations

from sqlalchemy.dialects import postgresql

from search.candidates import fetch_ann_candidates
from search.fts_candidates import fetch_fts_candidates
from shared.filters import SceneFilters


class _FakeResult:
    def all(self):
        return []


class _CapturingSession:
    def __init__(self) -> None:
        self.captured_stmt = None

    async def execute(self, stmt):
        self.captured_stmt = stmt
        return _FakeResult()


async def test_fetch_ann_candidates_filter_before_order_by_limit():
    session = _CapturingSession()
    await fetch_ann_candidates(
        session, [0.0] * 1024, pool_size=10, filters=SceneFilters(max_duration_ms=2000)
    )
    sql = str(session.captured_stmt.compile(dialect=postgresql.dialect()))

    where_pos = sql.upper().index("WHERE")
    # "end_ms" cũng xuất hiện ở SELECT column list (Scene.end_ms được select ra) —
    # tìm đúng biểu thức predicate `end_ms - scene.start_ms`, không phải cột đơn lẻ.
    filter_pos = sql.find("end_ms - scene.start_ms")
    limit_pos = sql.upper().index("LIMIT")
    assert where_pos < filter_pos < limit_pos


async def test_fetch_fts_candidates_filter_inside_subquery_before_limit():
    session = _CapturingSession()
    await fetch_fts_candidates(
        session, "world cup", pool_size=10, filters=SceneFilters(max_duration_ms=2000)
    )
    sql = str(session.captured_stmt.compile(dialect=postgresql.dialect()))

    sub_start = sql.index("FROM (")
    sub_end = sql.index(") AS anon_1")
    # "end_ms" cũng xuất hiện ở SELECT column list (Scene.end_ms được select ra) —
    # tìm đúng biểu thức predicate `end_ms - scene.start_ms`, không phải cột đơn lẻ.
    filter_pos = sql.find("end_ms - scene.start_ms")
    limit_pos = sql.upper().index("LIMIT")

    assert sub_start < filter_pos < sub_end, "filter phải nằm TRONG subquery"
    assert sub_start < limit_pos < sub_end, "LIMIT phải nằm TRONG subquery"
    assert filter_pos < limit_pos, "filter phải đứng TRƯỚC LIMIT trong subquery"

    # ts_headline PHẢI ở tầng ngoài (ngoài ranh giới subquery), không bị filter ảnh hưởng
    ts_headline_positions = [i for i in range(len(sql)) if sql.startswith("ts_headline", i)]
    assert all(p < sub_start or p > sub_end for p in ts_headline_positions)

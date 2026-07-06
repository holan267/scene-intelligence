"""Schema dùng chung cho thuộc tính lọc Scene (Story 2.3, FR-7, AD-21).

AD-21: "danh mục thuộc tính lọc ... khai báo ở MỘT schema dùng chung trong shared/;
ingest (ghi), search và UI (lọc) đều bind vào nó. Thêm bộ lọc mới = sửa schema này,
không tự thêm rời." `search/candidates.py`, `search/fts_candidates.py`,
`api/routes_search.py` PHẢI import `SceneFilters`/`apply_scene_filters` từ đây,
KHÔNG tự khai báo field lọc rời hoặc trùng lặp logic filter.

Phạm vi (Story 2.3): chỉ 2/4 bộ lọc tối thiểu của FR-7 — độ dài Scene và có mặt
người — vì đây là 2 thuộc tính duy nhất đã có tín hiệu ghi sẵn từ Epic 1
(`Scene.start_ms/end_ms` Story 1.3, `FaceAppearance` Story 1.5). `shot_size`
(cận/trung/toàn) và "không dính logo" CHƯA khai báo ở đây — không có ingest stage
nào ghi các trường này (chỉ tồn tại dưới dạng prose "Bối cảnh" trong
`scene_document`, Qwen3-VL Story 1.6); khai báo field mà không ai ghi dữ liệu sẽ
khiến filter luôn rỗng — tệ hơn không khai báo. Xem
`_bmad-output/implementation-artifacts/deferred-work.md`.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Select, exists, select

from shared.models import FaceAppearance, Scene


class SceneFilters(BaseModel):
    """Bộ lọc metadata Scene — mọi field mặc định `None` (không lọc).

    `extra="forbid"` (code review fix): field không tồn tại (vd chính `shot_size`/
    `has_logo` mà story cố tình chưa hỗ trợ — xem docstring module) phải báo lỗi
    ngay, không được Pydantic âm thầm bỏ qua — nếu không, client tưởng filter có
    tác dụng trong khi thực chất không được áp dụng.
    """

    model_config = ConfigDict(extra="forbid")

    min_duration_ms: int | None = Field(default=None, ge=0)
    max_duration_ms: int | None = Field(default=None, ge=0)
    has_person: bool | None = None
    # min_length=1 (code review fix): chuỗi rỗng lọt qua sẽ tạo "không tìm thấy"
    # âm thầm giống hệt gõ sai id, không có tín hiệu lỗi rõ ràng cho client.
    person_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _max_not_less_than_min(self) -> "SceneFilters":
        if (
            self.min_duration_ms is not None
            and self.max_duration_ms is not None
            and self.max_duration_ms < self.min_duration_ms
        ):
            raise ValueError("max_duration_ms không được nhỏ hơn min_duration_ms")
        return self

    @model_validator(mode="after")
    def _has_person_false_not_with_person_id(self) -> "SceneFilters":
        # Code review fix: has_person=False (không ai) + person_id=<id> (đúng người
        # đó) tự mâu thuẫn (NOT EXISTS mọi face_appearance VÀ EXISTS đúng person_id)
        # -> luôn ra kết quả rỗng mà không có tín hiệu lỗi nào cho client.
        if self.has_person is False and self.person_id is not None:
            raise ValueError(
                "has_person=False không thể kết hợp với person_id (tự mâu thuẫn)"
            )
        return self


def apply_scene_filters(stmt: Select, filters: SceneFilters | None) -> Select:
    """Thêm điều kiện `WHERE` lên `stmt` (đã `select`/`join` sẵn trên `Scene`) theo `filters`.

    Chỉ dùng SQL Core dialect-độc-lập (phép trừ nguyên + EXISTS) — không dùng hàm
    riêng Postgres nào (khác `fetch_ann_candidates`/`fetch_fts_candidates`) — nên
    dùng được ở CẢ hai nhánh ANN/FTS và unit-test được qua sqlite (AD-8: filter
    phải áp TRƯỚC `ORDER BY`/`LIMIT` — gọi hàm này TRƯỚC hai mệnh đề đó).
    """
    if filters is None:
        return stmt

    duration = Scene.end_ms - Scene.start_ms
    if filters.min_duration_ms is not None:
        stmt = stmt.where(duration >= filters.min_duration_ms)
    if filters.max_duration_ms is not None:
        stmt = stmt.where(duration <= filters.max_duration_ms)

    if filters.has_person is not None:
        has_face = exists(
            select(FaceAppearance.appearance_id).where(
                FaceAppearance.scene_id == Scene.scene_id
            )
        )
        stmt = stmt.where(has_face if filters.has_person else ~has_face)

    if filters.person_id is not None:
        stmt = stmt.where(
            exists(
                select(FaceAppearance.appearance_id).where(
                    FaceAppearance.scene_id == Scene.scene_id,
                    FaceAppearance.person_id == filters.person_id,
                )
            )
        )

    return stmt

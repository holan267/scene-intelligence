"""Registry danh tính đã đăng ký cho face-match (Story 1.5 — AC-3, AD-11).

Đăng ký/cập nhật Person là hàm thuần Python (không route API/UI ở story này — quy
trình đăng ký còn là câu hỏi mở của PRD). Idempotent theo `name`: gọi lại cùng tên
chỉ cập nhật `reference_embedding`, không tạo Person thứ hai.
"""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from shared.ids import new_id
from shared.models import Person


async def register_person(session: AsyncSession, name: str, embedding: list[float]) -> str:
    """Tạo mới Person theo `name`, hoặc cập nhật `reference_embedding` nếu đã tồn tại.

    Đăng ký đồng thời cùng `name` mới có thể đua trên unique constraint; SAVEPOINT
    (`begin_nested`) bắt `IntegrityError` mà không huỷ transaction ngoài, rồi update
    thay vì để lỗi unhandled lọt ra.
    """
    existing = (
        await session.execute(select(Person).where(Person.name == name))
    ).scalar_one_or_none()
    if existing is not None:
        existing.reference_embedding = json.dumps(embedding)
        await session.flush()
        return existing.person_id

    person_id = new_id()
    try:
        async with session.begin_nested():
            session.add(Person(person_id=person_id, name=name, reference_embedding=json.dumps(embedding)))
            await session.flush()
    except IntegrityError:
        existing = (
            await session.execute(select(Person).where(Person.name == name))
        ).scalar_one()
        existing.reference_embedding = json.dumps(embedding)
        await session.flush()
        return existing.person_id
    return person_id

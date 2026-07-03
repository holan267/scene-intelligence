from __future__ import annotations

import json

from sqlalchemy import select

from pipeline.registry import register_person
from shared.models import Person


async def test_register_person_creates_new(async_session):
    # AC-3: đăng ký danh tính mới
    pid = await register_person(async_session, "Trần Bình Minh", [1.0, 0.0, 0.0])
    person = await async_session.get(Person, pid)
    assert person is not None
    assert person.name == "Trần Bình Minh"
    assert json.loads(person.reference_embedding) == [1.0, 0.0, 0.0]


async def test_register_person_idempotent_by_name(async_session):
    # AC-3: gọi lại cùng tên -> cập nhật embedding, không tạo person thứ hai
    pid1 = await register_person(async_session, "Lại Văn Sâm", [1.0, 0.0])
    pid2 = await register_person(async_session, "Lại Văn Sâm", [0.0, 1.0])
    assert pid1 == pid2

    rows = (await async_session.execute(select(Person).where(Person.name == "Lại Văn Sâm"))).scalars().all()
    assert len(rows) == 1
    assert json.loads(rows[0].reference_embedding) == [0.0, 1.0]

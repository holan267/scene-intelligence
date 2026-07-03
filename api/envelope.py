"""Envelope kết quả + error-shape chuẩn (AD-13).

Mọi response API bọc `{results, meta}`; lỗi theo `{error: {code, message, detail}}`.
"""
from __future__ import annotations

from typing import Any


def ok(results: list[Any] | None = None, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"results": results or [], "meta": meta or {}}


def err(code: str, message: str, detail: Any | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "detail": detail}}

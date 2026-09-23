"""Adapter Qwen3-VL: tên model gửi đi + chẩn đoán khi model trả content rỗng.

Khoá lại một lỗi đã xảy ra thật: qwen3-vl là model *thinking*, với num_ctx nhỏ thì phần
"suy nghĩ" ăn hết cửa sổ ngữ cảnh và request kết thúc `finish_reason='length'` với
`content` RỖNG. Tầng trên (`describe_scene` -> `index_scene`) khi đó bỏ qua embedder nên
triệu chứng hiện ra ở chỗ khác hẳn nơi hỏng (log nhiều chat/completions, ít embeddings,
scene kẹt 'pending') — thông điệp lỗi là thứ duy nhất chỉ đúng chỗ, nên nó được test.
"""
from __future__ import annotations

import httpx
import pytest

from pipeline.describe_backends import Qwen3VLDescriber
from shared.config import Settings


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def _patch_post(monkeypatch, payload: dict) -> dict:
    """Thay httpx.post, trả về dict ghi lại request để assert phần gửi đi."""
    sent: dict = {}

    def fake_post(url, json, timeout):  # noqa: A002 - khớp chữ ký httpx.post
        sent["url"] = url
        sent["json"] = json
        return _FakeResponse(payload)

    monkeypatch.setattr(httpx, "post", fake_post)
    return sent


def _choice(content, finish_reason: str) -> dict:
    return {"choices": [{"message": {"content": content}, "finish_reason": finish_reason}]}


def _describer() -> Qwen3VLDescriber:
    return Qwen3VLDescriber(Settings(describe_model_name="qwen3-vl:2b-ctx16k"))


def test_gui_dung_tag_trong_cau_hinh(monkeypatch):
    # Sai tag là 404 từ Ollama; tag phải đến từ config chứ không hardcode trong adapter.
    sent = _patch_post(monkeypatch, _choice("Cảnh quay hiện trường.", "stop"))
    assert _describer().describe([b"\xff\xd8"], {}) == "Cảnh quay hiện trường."
    assert sent["json"]["model"] == "qwen3-vl:2b-ctx16k"


def test_content_rong_vi_chay_het_ngu_canh_bao_dung_nguyen_nhan(monkeypatch):
    _patch_post(monkeypatch, _choice("", "length"))
    with pytest.raises(RuntimeError, match="num_ctx"):
        _describer().describe([b"\xff\xd8"], {})


def test_content_rong_khong_phai_do_ngu_canh_van_bao_rong(monkeypatch):
    # Hai nguyên nhân sửa bằng hai cách khác nhau (cấu hình vs prompt) -> không gộp lỗi.
    _patch_post(monkeypatch, _choice("   ", "stop"))
    with pytest.raises(RuntimeError, match="rỗng"):
        _describer().describe([b"\xff\xd8"], {})

"""Adapter Qwen3-VL thật (Story 1.6). Guarded — chưa chạy môi trường dev.

Qwen3-VL chạy trên Model Server (vLLM, AD-14) — gọi qua endpoint chat/completions
OpenAI-compatible, không load model trong tiến trình pipeline. Ảnh keyframe truyền vào
đã lấy qua storage-port ở caller (`describe_scene`) — adapter chỉ encode bytes, không
tự đọc storage (AD-23). Cần server Qwen3-VL đang chạy tại `describe_model_url`.
"""
from __future__ import annotations

import base64

import httpx

from shared.config import Settings, get_settings


def _build_prompt(hints: dict) -> str:
    parts = []
    if hints.get("transcript"):
        parts.append(f"Lời thoại: {hints['transcript']}")
    if hints.get("ocr_text"):
        parts.append(f"Chữ trên hình: {hints['ocr_text']}")
    if hints.get("objects"):
        parts.append(f"Đối tượng: {', '.join(hints['objects'])}")
    if hints.get("faces"):
        parts.append(f"Người xuất hiện: {', '.join(hints['faces'])}")
    context = "\n".join(parts)
    return (
        "Mô tả ngắn gọn bằng tiếng Việt nội dung Scene trong video thời sự dựa trên "
        f"(các) khung hình và ngữ cảnh sau:\n{context}"
    )


class Qwen3VLDescriber:
    """Sinh Scene Document NL qua Qwen3-VL (vLLM, chat/completions đa phương thức)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def describe(self, keyframe_images: list[bytes], hints: dict) -> str:  # pragma: no cover - phụ thuộc production
        image_content = [
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{base64.b64encode(img).decode()}"},
            }
            for img in keyframe_images
        ]
        payload = {
            "model": "Qwen3-VL",
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": _build_prompt(hints)}, *image_content],
                }
            ],
        }
        try:
            response = httpx.post(
                f"{self._settings.describe_model_url}/v1/chat/completions", json=payload, timeout=60.0
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Gọi Qwen3-VL thất bại: {exc}") from exc
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise RuntimeError(f"Qwen3-VL trả response không đúng hình dạng mong đợi: {exc}") from exc

        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Qwen3-VL trả nội dung rỗng")
        return content.strip()

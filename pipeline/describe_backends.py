"""Adapter Qwen3-VL thật (Story 1.6).

Qwen3-VL chạy trên Model Server (AD-14) — gọi qua endpoint chat/completions
OpenAI-compatible, không load model trong tiến trình pipeline. Ảnh keyframe truyền vào
đã lấy qua storage-port ở caller (`describe_scene`) — adapter chỉ encode bytes, không
tự đọc storage (AD-23). Cần server Qwen3-VL đang chạy tại `describe_model_url`.

Dev 1 máy: Ollama (`ollama pull qwen3-vl:2b && ollama serve`, cổng 11434) — cùng tiến
trình phục vụ BGE-M3 cho embed, xem `shared/config.py`. Tag gửi đi là tag DẪN XUẤT có
num_ctx nới rộng (`describe_model_name`), không phải tag gốc — lý do ở `shared/config.py`
và ở `_ERR_TRUNCATED` bên dưới.
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


# qwen3-vl là model *thinking*: nó xả phần suy nghĩ vào `reasoning` TRƯỚC khi viết
# `content`. Cửa sổ ngữ cảnh hẹp (num_ctx=4096 mặc định của Ollama) + prompt ~2.1k token
# cho MỘT keyframe => suy nghĩ ăn hết chỗ còn lại, finish_reason='length' và `content`
# rỗng. Triệu chứng ở tầng trên rất dễ đọc nhầm: describe raise nên `scene_document` vẫn
# NULL, `index_scene` raise trước khi gọi embedder => log có N lần chat/completions nhưng
# chỉ vài lần embeddings, và scene kẹt ở search_status='pending'.
_ERR_TRUNCATED = (
    "Qwen3-VL chạm trần cửa sổ ngữ cảnh trước khi kịp trả lời (finish_reason='length', "
    "content rỗng) — model {model!r} đang phục vụ với num_ctx quá nhỏ cho prompt có "
    "keyframe. Nới num_ctx cho tag đang dùng (xem `describe_model_name` trong "
    "shared/config.py); đặt qua `options.num_ctx` trong payload KHÔNG có tác dụng vì lớp "
    "OpenAI-compat của Ollama bỏ qua trường này."
)


class Qwen3VLDescriber:
    """Sinh Scene Document NL qua Qwen3-VL (vLLM, chat/completions đa phương thức)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def describe(self, keyframe_images: list[bytes], hints: dict) -> str:
        image_content = [
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{base64.b64encode(img).decode()}"},
            }
            for img in keyframe_images
        ]
        payload = {
            # Tên model theo ĐÚNG tag Ollama đang phục vụ. Khác BGE-M3 (Ollama match tên
            # không phân biệt hoa/thường nên "BGE-M3" khớp `bge-m3:latest`), ở đây tag đầy
            # đủ là BẮT BUỘC: không có `qwen3-vl:latest` nên "Qwen3-VL" trần trả 404.
            # Đổi sang on-prem vLLM: đặt `--served-model-name` khớp DESCRIBE_MODEL_NAME.
            "model": self._settings.describe_model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": _build_prompt(hints)}, *image_content],
                }
            ],
        }
        try:
            response = httpx.post(
                f"{self._settings.describe_model_url}/v1/chat/completions", json=payload, timeout=120.0
            )
            response.raise_for_status()
            choice = response.json()["choices"][0]
            content = choice["message"]["content"]
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Gọi Qwen3-VL thất bại: {exc}") from exc
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise RuntimeError(f"Qwen3-VL trả response không đúng hình dạng mong đợi: {exc}") from exc

        if not isinstance(content, str) or not content.strip():
            # Phân biệt hai nguyên nhân rất khác nhau của "content rỗng": chạm trần cửa sổ
            # ngữ cảnh (sửa bằng cấu hình) hay model thật sự không nói gì (sửa bằng prompt).
            if choice.get("finish_reason") == "length":
                raise RuntimeError(_ERR_TRUNCATED.format(model=self._settings.describe_model_name))
            raise RuntimeError("Qwen3-VL trả nội dung rỗng")
        return content.strip()

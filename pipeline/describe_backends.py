"""Adapter describe: Qwen3-VL trên Model Server nội bộ, hoặc DeepSeek qua API (Story 1.6).

Cả hai backend nói CÙNG một giao thức: chat/completions OpenAI-compatible với ảnh truyền
dưới dạng `image_url` base64. Vì vậy phần thân nằm ở `_ChatCompletionsDescriber`, hai lớp
con chỉ khai báo endpoint / tên model / header xác thực / chẩn đoán riêng. Chọn backend
bằng `describe_backend` (xem `build_describer`).

Không backend nào load model trong tiến trình pipeline (AD-14). Ảnh keyframe truyền vào đã
lấy qua storage-port ở caller (`describe_scene`) — adapter chỉ encode bytes, không tự đọc
storage (AD-23).

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


class _ChatCompletionsDescriber:
    """Thân chung: dựng payload đa phương thức, POST, bóc `content`, dịch lỗi sang RuntimeError.

    Lớp con khai báo: `_label` (tên backend trong thông điệp lỗi), `_model`, `_endpoint`,
    `_headers`, `_timeout`, và `_truncated_error()` (chẩn đoán khi bị cắt giữa chừng —
    nguyên nhân và cách sửa khác hẳn nhau giữa Ollama tự host và API đám mây).
    """

    _label = "describe backend"
    _timeout = 120.0

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    @property
    def _model(self) -> str:  # pragma: no cover - lớp con luôn ghi đè
        raise NotImplementedError

    @property
    def _endpoint(self) -> str:  # pragma: no cover - lớp con luôn ghi đè
        raise NotImplementedError

    @property
    def _headers(self) -> dict[str, str]:
        return {}

    def _truncated_error(self) -> str:
        return f"{self._label} bị cắt giữa chừng (finish_reason='length', content rỗng)"

    def describe(self, keyframe_images: list[bytes], hints: dict) -> str:
        image_content = [
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{base64.b64encode(img).decode()}"},
            }
            for img in keyframe_images
        ]
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": _build_prompt(hints)}, *image_content],
                }
            ],
        }
        try:
            response = httpx.post(
                self._endpoint, json=payload, timeout=self._timeout, headers=self._headers
            )
            response.raise_for_status()
            choice = response.json()["choices"][0]
            content = choice["message"]["content"]
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Gọi {self._label} thất bại: {exc}") from exc
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise RuntimeError(
                f"{self._label} trả response không đúng hình dạng mong đợi: {exc}"
            ) from exc

        if not isinstance(content, str) or not content.strip():
            # Phân biệt hai nguyên nhân rất khác nhau của "content rỗng": chạm trần cửa sổ
            # ngữ cảnh (sửa bằng cấu hình) hay model thật sự không nói gì (sửa bằng prompt).
            if choice.get("finish_reason") == "length":
                raise RuntimeError(self._truncated_error())
            raise RuntimeError(f"{self._label} trả nội dung rỗng")
        return content.strip()


class Qwen3VLDescriber(_ChatCompletionsDescriber):
    """Sinh Scene Document NL qua Qwen3-VL trên model server nội bộ (Ollama/vLLM)."""

    _label = "Qwen3-VL"

    @property
    def _model(self) -> str:
        # Tên model theo ĐÚNG tag Ollama đang phục vụ. Khác BGE-M3 (Ollama match tên không
        # phân biệt hoa/thường nên "BGE-M3" khớp `bge-m3:latest`), ở đây tag đầy đủ là BẮT
        # BUỘC: không có `qwen3-vl:latest` nên "Qwen3-VL" trần trả 404.
        # Đổi sang on-prem vLLM: đặt `--served-model-name` khớp DESCRIBE_MODEL_NAME.
        return self._settings.describe_model_name

    @property
    def _endpoint(self) -> str:
        return f"{self._settings.describe_model_url}/v1/chat/completions"

    def _truncated_error(self) -> str:
        return _ERR_TRUNCATED.format(model=self._settings.describe_model_name)


class DeepSeekDescriber(_ChatCompletionsDescriber):
    """Sinh Scene Document NL qua API DeepSeek (chat/completions đa phương thức).

    Dùng khi node chưa có GPU đủ chạy model VL. ĐÁNH ĐỔI so với Qwen3-VL tự host: keyframe
    rời khỏi máy chủ (base64 trong payload gửi lên api.deepseek.com), ngược với mặc định
    air-gap AD-14 — chỉ bật cho tư liệu được phép ra ngoài.

    Gọi thẳng bằng httpx thay vì SDK `openai`: giao thức y hệt các model server còn lại
    (POST /v1/chat/completions + header Bearer), thêm dependency chỉ để có đúng lời gọi đó
    là không cần thiết.
    """

    _label = "DeepSeek"

    @property
    def _model(self) -> str:
        return self._settings.deepseek_model

    @property
    def _endpoint(self) -> str:
        # rstrip('/'): DEEPSEEK_BASE_URL đặt tay rất hay kèm dấu '/' cuối, nối thẳng sẽ ra
        # '//v1/chat/completions'.
        return f"{self._settings.deepseek_base_url.rstrip('/')}/v1/chat/completions"

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._settings.deepseek_api_key}"}

    def _truncated_error(self) -> str:
        # Khác Qwen3-VL tự host: không có num_ctx để nới. Cụt ở đây là do model xả phần suy
        # nghĩ/độ dài vượt giới hạn của chính API — sửa bằng prompt hoặc đổi model.
        return (
            f"DeepSeek trả về content rỗng vì chạm giới hạn độ dài (finish_reason='length') "
            f"— model {self._settings.deepseek_model!r}. Rút gọn hints trong prompt (ASR/OCR "
            f"dài) hoặc đổi sang model khác."
        )


def build_describer(settings: Settings | None = None) -> _ChatCompletionsDescriber:
    """Chọn adapter describe theo `describe_backend`.

    Fail ngay tại đây (lúc worker boot) thay vì để mọi task rơi vào 'error' rồi mới đọc
    `ingest_task.reason` — cấu hình sai backend hoặc thiếu API key là lỗi cấu hình.
    """
    settings = settings or get_settings()
    backend = settings.describe_backend.strip().lower()
    if backend == "qwen3vl":
        return Qwen3VLDescriber(settings)
    if backend == "deepseek":
        if not settings.deepseek_api_key:
            raise RuntimeError(
                "DESCRIBE_BACKEND=deepseek nhưng thiếu DEEPSEEK_API_KEY — lấy key ở "
                "platform.deepseek.com rồi đặt vào .env."
            )
        return DeepSeekDescriber(settings)
    raise RuntimeError(
        f"DESCRIBE_BACKEND không hợp lệ: {settings.describe_backend!r} (chọn: qwen3vl | deepseek)"
    )

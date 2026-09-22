"""Adapter ASR/OCR tiếng Việt thật (Story 1.4). Guarded import — chưa chạy môi trường dev.

- PhoWhisperTranscriber: PhoWhisper-large qua faster-whisper/CTranslate2 (SOTA Vi ASR).
- VietOcrReader: EasyOCR (dò vùng chữ) + VietOCR (đọc chữ Việt có dấu). Đều `language="vi"` (AD-9).
Media truy cập qua storage-port `local_path` (AD-23). Cần faster-whisper/easyocr/vietocr + ffmpeg.

Cả hai adapter nạp model LƯỜI và giữ lại cho cả vòng đời worker: pipeline.workers gọi
`transcribe`/`read_text` theo từng scene/keyframe (hàng trăm lần cho một video tin tức),
nạp lại mỗi lần sẽ tốn vài GB I/O + khởi tạo cho mỗi scene.
"""
from __future__ import annotations

from shared.storage import StoragePort, build_storage


class PhoWhisperTranscriber:
    language = "vi"

    def __init__(
        self,
        storage: StoragePort | None = None,
        model_dir: str = "PhoWhisper-large",
        device: str = "auto",
        compute_type: str = "default",
    ) -> None:
        self._storage = storage or build_storage()
        self._model_dir = model_dir
        self._device = device
        self._compute_type = compute_type
        self._model = None

    def _lazy(self):  # pragma: no cover - phụ thuộc production
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise RuntimeError(
                    "Cần cài `faster-whisper` (+ PhoWhisper-large convert CTranslate2)"
                ) from exc
            self._model = WhisperModel(
                self._model_dir, device=self._device, compute_type=self._compute_type
            )
        return self._model

    def transcribe(self, media_key: str, start_ms: int, end_ms: int) -> str:  # pragma: no cover - phụ thuộc production
        model = self._lazy()
        path = self._storage.local_path(media_key)  # qua port (AD-23)
        # clip_timestamps nhận giây: chỉ decode đoạn audio của scene, không chạy cả video.
        segments, _ = model.transcribe(
            path, language="vi", clip_timestamps=[start_ms / 1000, end_ms / 1000]
        )
        return " ".join(seg.text.strip() for seg in segments).strip()


class VietOcrReader:
    """EasyOCR dò vùng chữ + VietOCR đọc nội dung.

    Tách đôi vì recognizer 'vi' sẵn có của EasyOCR đọc dấu tiếng Việt kém hơn hẳn VietOCR
    (vgg_transformer) — chữ chạy dưới màn hình tin tức gần như luôn có dấu.
    """

    language = "vi"

    def __init__(self, model_name: str = "vgg_transformer", device: str = "cpu") -> None:
        self._detector = None
        self._recognizer = None
        self._model_name = model_name
        self._device = device

    def _lazy(self):  # pragma: no cover - phụ thuộc production
        if self._detector is None:
            import easyocr

            # recognizer=False: chỉ nạp phần dò vùng chữ (CRAFT), phần đọc để VietOCR lo.
            self._detector = easyocr.Reader(
                ["vi"], gpu=self._device != "cpu", recognizer=False
            )
        if self._recognizer is None:
            from vietocr.tool.config import Cfg
            from vietocr.tool.predictor import Predictor

            cfg = Cfg.load_config_from_name(self._model_name)
            cfg["device"] = self._device
            cfg["predictor"]["beamsearch"] = False  # greedy: nhanh hơn nhiều, đủ cho chữ chạy
            self._recognizer = Predictor(cfg)
        return self._detector, self._recognizer

    def read_text(self, image: bytes) -> str:  # pragma: no cover - phụ thuộc production
        try:
            detector, recognizer = self._lazy()
        except ImportError as exc:
            raise RuntimeError("Cần cài `easyocr` + `vietocr` để OCR tiếng Việt") from exc
        import cv2
        import numpy as np
        from PIL import Image

        arr = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR)
        if arr is None:
            raise RuntimeError("Không decode được keyframe (ảnh hỏng/rỗng)")
        # detect() trả (horizontal_list, free_list), mỗi cái là list-theo-ảnh. Chỉ lấy hộp
        # ngang: free_list là chữ nghiêng/cong, hiếm trong đồ hoạ tin tức và crop xiên vào
        # VietOCR cho kết quả rác.
        horizontal, _free = detector.detect(arr)
        boxes = horizontal[0] if horizontal else []
        rgb = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
        height, width = rgb.shape[:2]

        lines: list[str] = []
        for box in sorted(boxes, key=lambda b: (b[2], b[0])):  # trên->dưới, trái->phải
            x_min, x_max, y_min, y_max = box
            x0, x1 = max(0, int(x_min)), min(width, int(x_max))
            y0, y1 = max(0, int(y_min)), min(height, int(y_max))
            if x1 <= x0 or y1 <= y0:  # hộp rỗng sau khi kẹp biên
                continue
            text = recognizer.predict(Image.fromarray(rgb[y0:y1, x0:x1])).strip()
            if text:
                lines.append(text)
        return " ".join(lines)

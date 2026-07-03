"""Adapter ASR/OCR tiếng Việt thật (Story 1.4). Guarded import — chưa chạy môi trường dev.

- PhoWhisperTranscriber: PhoWhisper-large qua faster-whisper/CTranslate2 (SOTA Vi ASR).
- VietOcrReader: EasyOCR (dò chữ) + VietOCR (đọc chữ Việt). Đều `language="vi"` (AD-9).
Media truy cập qua storage-port `local_path` (AD-23). Cần faster-whisper/easyocr/vietocr + ffmpeg.
"""
from __future__ import annotations

from shared.storage import StoragePort, build_storage


class PhoWhisperTranscriber:
    language = "vi"

    def __init__(self, storage: StoragePort | None = None, model_dir: str = "PhoWhisper-large") -> None:
        self._storage = storage or build_storage()
        self._model_dir = model_dir

    def transcribe(self, media_key: str, start_ms: int, end_ms: int) -> str:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:  # pragma: no cover - phụ thuộc production
            raise RuntimeError("Cần cài `faster-whisper` (+ PhoWhisper-large convert CTranslate2)") from exc
        model = WhisperModel(self._model_dir)
        path = self._storage.local_path(media_key)  # qua port (AD-23)
        segments, _ = model.transcribe(path, language="vi", clip_timestamps=[start_ms / 1000, end_ms / 1000])
        return " ".join(seg.text.strip() for seg in segments).strip()


class VietOcrReader:
    language = "vi"

    def __init__(self) -> None:
        self._reader = None
        self._recognizer = None

    def _lazy(self) -> None:  # pragma: no cover - phụ thuộc production
        if self._reader is None:
            import easyocr

            self._reader = easyocr.Reader(["vi"])

    def read_text(self, image: bytes) -> str:  # pragma: no cover - phụ thuộc production
        try:
            self._lazy()
        except ImportError as exc:
            raise RuntimeError("Cần cài `easyocr` + `vietocr` để OCR tiếng Việt") from exc
        import numpy as np

        arr = np.frombuffer(image, dtype=np.uint8)
        results = self._reader.readtext(arr, detail=0)
        return " ".join(results).strip()

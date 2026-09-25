"""Adapter ASR/OCR tiếng Việt thật (Story 1.4). Guarded import — chưa chạy môi trường dev.

- PhoWhisperTranscriber: PhoWhisper-large qua faster-whisper/CTranslate2 (SOTA Vi ASR).
- VietOcrReader: EasyOCR (dò vùng chữ) + VietOCR (đọc chữ Việt có dấu). Đều `language="vi"` (AD-9).
Media truy cập qua storage-port `local_path` (AD-23).

## Trọng số: LOCAL, không bao giờ tải lúc chạy (AD-14 air-gap)

Cả ba thư viện đều mặc định tự tải trọng số về `~/.cache` khi gọi lần đầu — trong container
thì vừa gọi Internet (vỡ air-gap) vừa mất sạch sau mỗi lần restart. Adapter này chặn hết:

- faster-whisper: `WhisperModel("tên-không-phải-thư-mục")` coi đó là repo-id HuggingFace và
  tải về. Thư mục model được kiểm tra TRƯỚC nên trường hợp đó fail rõ ràng thay vì âm thầm
  tải. Thiếu `tokenizer.json` trong thư mục đã convert thì faster-whisper cũng tự tải
  `openai/whisper-tiny` — `deploy/fetch-models.sh` bảo đảm file này luôn có.
- EasyOCR: `download_enabled=False` + `model_storage_directory` trỏ vào trọng số đã nạp sẵn.
- VietOCR: `Cfg.load_config_from_name()` tải YAML config TỪ MẠNG, và `Predictor` tải `.pth`
  khi `weights` bắt đầu bằng `http`. Nên đọc config từ file YAML đã nạp sẵn và ép `weights`
  thành đường dẫn tuyệt đối local.

## Thiết bị: CPU hoặc CUDA, KHÔNG có Metal/MPS

CTranslate2 (backend của faster-whisper) không có backend Metal, nên trên Apple Silicon chỉ
còn đường CPU — `device="mps"` bị chặn ngay ở `_lazy()` với thông báo rõ ràng. Trọng số
fetch-models.sh dựng ra là float16: nạp trên CPU thì ctranslate2 tự nở ngược lên float32
(`compute type ... converted to float32`), tốn gấp đôi RAM và chậm hơn. Đặt
`compute_type="int8"` để lượng tử hoá ngay lúc nạp, không cần convert lại trọng số.

Kiểm tra đường dẫn đặt TRƯỚC import thư viện: báo lỗi hữu ích ngay cả trên máy chưa cài
faster-whisper/easyocr/vietocr, và cho phép test guard mà không cần trọng số thật.

Trọng số lấy ở đâu: chạy `deploy/fetch-models.sh` trên máy CÓ Internet rồi copy thư mục
sang node air-gap. Xem deploy/README.md.
"""
from __future__ import annotations

from pathlib import Path

from pipeline.enrich import TranscriptSegment
from shared.storage import StoragePort, build_storage

_FETCH_HINT = "Chạy `deploy/fetch-models.sh` trên máy có Internet rồi copy sang node này"


class PhoWhisperTranscriber:
    language = "vi"

    def __init__(
        self,
        storage: StoragePort | None = None,
        model_dir: str = "./_data/models/PhoWhisper-large-ct2",
        device: str = "auto",  # 'auto' | 'cpu' | 'cuda' — CTranslate2 không có Metal/MPS
        compute_type: str = "default",  # 'int8' trên CPU, 'float16' trên GPU
    ) -> None:
        self._storage = storage or build_storage()
        self._model_dir = model_dir
        self._device = device
        self._compute_type = compute_type
        self._model = None

    def _lazy(self):
        """Nạp model MỘT lần cho cả vòng đời worker.

        `transcribe()` được gọi một lần cho mỗi video, nhưng worker xử lý nhiều video liên
        tiếp; khởi tạo lại model mỗi video là vài GB I/O mỗi lần.
        """
        if self._model is not None:
            return self._model

        model_dir = Path(self._model_dir)
        if not model_dir.is_dir():
            raise RuntimeError(
                f"Không thấy thư mục model PhoWhisper đã convert CTranslate2: {self._model_dir!r}. "
                f"{_FETCH_HINT} (ASR_MODEL_DIR). Để faster-whisper tự tải từ HuggingFace là "
                "vỡ air-gap (AD-14)."
            )
        if not (model_dir / "tokenizer.json").is_file():
            raise RuntimeError(
                f"Thiếu tokenizer.json trong {self._model_dir!r} — faster-whisper sẽ tải "
                f"`openai/whisper-tiny` từ HuggingFace lúc chạy (vỡ air-gap, AD-14). {_FETCH_HINT}."
            )

        if self._device == "mps":
            raise RuntimeError(
                "ASR_DEVICE='mps' không dùng được: CTranslate2 (backend của faster-whisper) "
                "chỉ có CPU và CUDA, không có backend Metal. Trên Apple Silicon đặt "
                "ASR_DEVICE=cpu kèm ASR_COMPUTE_TYPE=int8."
            )

        try:  # pragma: no cover - phụ thuộc production
            from faster_whisper import WhisperModel
        except ImportError as exc:  # pragma: no cover - phụ thuộc production
            raise RuntimeError(
                "Cần cài `faster-whisper`: `uv pip install -e '.[enrich]'`"
            ) from exc
        self._model = WhisperModel(  # pragma: no cover - phụ thuộc production
            str(model_dir), device=self._device, compute_type=self._compute_type
        )
        return self._model  # pragma: no cover - phụ thuộc production

    def transcribe(self, media_key: str) -> list[TranscriptSegment]:  # pragma: no cover - phụ thuộc production
        """Transcribe TRỌN video một lần; cắt theo scene do `transcript_for_range` lo.

        Mỗi lần gọi `WhisperModel.transcribe()` chạy trọn một encoder pass (audio pad lên
        cửa sổ 30s), nên gọi theo từng scene là O(số scene × 30s). `beam_size=1` (greedy)
        nhanh hơn beam mặc định 5 mà đủ cho lời thoại tin tức.

        `word_timestamps=True` trả mốc theo TỪ: timestamp mức câu quá thô (một câu có thể
        trải 20s), cắt theo scene bằng nó sẽ rỗng/ăn sai scene. Word-level cũng giữ chi phí
        gần như không đổi vì encoder vẫn chạy một lần.
        """
        model = self._lazy()
        path = self._storage.local_path(media_key)  # qua port (AD-23)
        segments, _ = model.transcribe(
            path, language="vi", beam_size=1, word_timestamps=True
        )
        pieces: list[TranscriptSegment] = []
        for seg in segments:
            words = getattr(seg, "words", None)
            if words:
                pieces.extend(
                    TranscriptSegment(int(w.start * 1000), int(w.end * 1000), w.word.strip())
                    for w in words
                )
            else:  # phòng khi model không trả word-level: dùng nguyên câu
                pieces.append(
                    TranscriptSegment(int(seg.start * 1000), int(seg.end * 1000), seg.text.strip())
                )
        return pieces


class VietOcrReader:
    """EasyOCR dò vùng chữ + VietOCR đọc nội dung.

    Tách đôi vì recognizer 'vi' sẵn có của EasyOCR đọc dấu tiếng Việt kém hơn hẳn VietOCR
    (vgg_transformer) — chữ chạy dưới màn hình tin tức gần như luôn có dấu.

    `detector_dir`/`recognizer_dir` không có giá trị mặc định: đường dẫn trọng số là hợp
    đồng air-gap, để lẫn một mặc định sai sẽ khiến cấu hình hỏng trôi tới tận runtime.
    """

    language = "vi"

    def __init__(
        self,
        detector_dir: str,
        recognizer_dir: str,
        model_name: str = "vgg_transformer",
        device: str = "cpu",
    ) -> None:
        self._detector_dir = detector_dir
        self._recognizer_dir = recognizer_dir
        self._model_name = model_name
        self._device = device
        self._detector = None
        self._recognizer = None

    def _weights_path(self) -> Path:
        return Path(self._recognizer_dir) / f"{self._model_name}.pth"

    def _config_path(self) -> Path:
        return Path(self._recognizer_dir) / f"{self._model_name}.yml"

    def _lazy(self):
        if self._detector is not None and self._recognizer is not None:
            return self._detector, self._recognizer

        # Kiểm tra TRƯỚC khi import: lỗi thiếu trọng số phải nói rõ phải làm gì.
        detector_dir = Path(self._detector_dir)
        if not (detector_dir / "craft_mlt_25k.pth").is_file():
            raise RuntimeError(
                f"Không thấy trọng số dò chữ EasyOCR (craft_mlt_25k.pth) trong "
                f"{self._detector_dir!r}. {_FETCH_HINT} (OCR_DETECTOR_DIR)."
            )
        for path, what in ((self._weights_path(), "trọng số"), (self._config_path(), "config")):
            if not path.is_file():
                raise RuntimeError(
                    f"Không thấy {what} VietOCR: {str(path)!r}. {_FETCH_HINT} "
                    "(OCR_RECOGNIZER_DIR)."
                )

        self._detector = self._build_detector(detector_dir)
        self._recognizer = self._build_recognizer()
        return self._detector, self._recognizer

    def _build_detector(self, detector_dir: Path):  # pragma: no cover - phụ thuộc production
        try:
            import easyocr
        except ImportError as exc:
            raise RuntimeError("Cần cài `easyocr`: `uv pip install -e '.[enrich]'`") from exc
        # recognizer=False: chỉ nạp phần dò vùng chữ (CRAFT), phần đọc để VietOCR lo.
        # download_enabled=False: thiếu trọng số thì fail, TUYỆT ĐỐI không tải (AD-14).
        return easyocr.Reader(
            ["vi"],
            gpu=self._device != "cpu",
            recognizer=False,
            model_storage_directory=str(detector_dir),
            download_enabled=False,
            verbose=False,
        )

    def _build_recognizer(self):  # pragma: no cover - phụ thuộc production
        try:
            import yaml
            from vietocr.tool.config import Cfg
            from vietocr.tool.predictor import Predictor
        except ImportError as exc:
            raise RuntimeError("Cần cài `vietocr`: `uv pip install -e '.[enrich]'`") from exc

        # Đọc YAML đã nạp sẵn thay vì Cfg.load_config_from_name() — hàm đó GỌI MẠNG để lấy
        # config. fetch-models.sh đã ghi ra bản config hợp nhất (base + model).
        with self._config_path().open(encoding="utf-8") as fh:
            cfg = Cfg(yaml.safe_load(fh))
        # Predictor chỉ tải khi weights bắt đầu bằng 'http' -> đường tuyệt đối = không tải.
        cfg["weights"] = str(self._weights_path().resolve())
        cfg["device"] = self._device
        cfg["predictor"]["beamsearch"] = False  # greedy: nhanh hơn nhiều, đủ cho chữ chạy
        return Predictor(cfg)

    def read_text(self, image: bytes) -> str:
        detector, recognizer = self._lazy()
        return self._read(detector, recognizer, image)

    @staticmethod
    def _read(detector, recognizer, image: bytes) -> str:  # pragma: no cover - phụ thuộc production
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

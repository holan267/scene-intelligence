"""Guard air-gap của adapter ASR/OCR (AD-14): thiếu trọng số phải FAIL, không được tải.

Chạy được dù chưa cài faster-whisper/easyocr/vietocr vì adapter kiểm tra đường dẫn TRƯỚC
khi import thư viện — đó cũng chính là điều test này khoá lại: một lần đảo thứ tự sẽ biến
lỗi "thiếu trọng số" thành lượt tải ngầm từ Internet trên node đáng lẽ air-gap.
"""
from __future__ import annotations

import sys
import types

import pytest

from pipeline.enrich import TranscriptSegment
from pipeline.enrich_backends import PhoWhisperTranscriber, VietOcrReader


class DummyStorage:
    def local_path(self, media_key: str) -> str:
        return f"/media/{media_key}"


def _asr(model_dir, **kwargs) -> PhoWhisperTranscriber:
    return PhoWhisperTranscriber(storage=DummyStorage(), model_dir=str(model_dir), **kwargs)


def _ready_model_dir(tmp_path):
    """Thư mục model qua được guard air-gap (model.bin + tokenizer.json)."""
    (tmp_path / "model.bin").write_bytes(b"x")
    (tmp_path / "tokenizer.json").write_text("{}")
    return tmp_path


def test_asr_rejects_missing_model_dir(tmp_path):
    # faster-whisper coi path không tồn tại là repo-id HuggingFace rồi TẢI VỀ -> phải chặn
    with pytest.raises(RuntimeError, match="fetch-models"):
        _asr(tmp_path / "khong-co")._lazy()


def test_asr_rejects_model_dir_without_tokenizer(tmp_path):
    # Thiếu tokenizer.json thì faster-whisper lặng lẽ tải openai/whisper-tiny từ HF
    (tmp_path / "model.bin").write_bytes(b"x")
    with pytest.raises(RuntimeError, match="tokenizer.json"):
        _asr(tmp_path)._lazy()


def test_asr_names_the_offending_path(tmp_path):
    missing = tmp_path / "PhoWhisper-large-ct2"
    with pytest.raises(RuntimeError, match=str(missing)):
        _asr(missing)._lazy()


def _ocr(detector_dir, recognizer_dir) -> VietOcrReader:
    return VietOcrReader(detector_dir=str(detector_dir), recognizer_dir=str(recognizer_dir))


def test_ocr_rejects_missing_craft_weights(tmp_path):
    with pytest.raises(RuntimeError, match="craft_mlt_25k.pth"):
        _ocr(tmp_path / "easyocr", tmp_path / "vietocr")._lazy()


def test_ocr_rejects_missing_vietocr_weights(tmp_path):
    detector_dir = tmp_path / "easyocr"
    detector_dir.mkdir()
    (detector_dir / "craft_mlt_25k.pth").write_bytes(b"x")
    with pytest.raises(RuntimeError, match=r"trọng số VietOCR"):
        _ocr(detector_dir, tmp_path / "vietocr")._lazy()


def test_ocr_rejects_missing_vietocr_config(tmp_path):
    # Có .pth nhưng thiếu .yml: Cfg.load_config_from_name() sẽ phải GỌI MẠNG lấy config
    detector_dir = tmp_path / "easyocr"
    detector_dir.mkdir()
    (detector_dir / "craft_mlt_25k.pth").write_bytes(b"x")
    recognizer_dir = tmp_path / "vietocr"
    recognizer_dir.mkdir()
    (recognizer_dir / "vgg_transformer.pth").write_bytes(b"x")
    with pytest.raises(RuntimeError, match="config VietOCR"):
        _ocr(detector_dir, recognizer_dir)._lazy()


def test_ocr_ad9_language_tag_survives_construction(tmp_path):
    # AD-9: worker_main guard đọc .language lúc boot, TRƯỚC khi nạp trọng số
    assert _ocr(tmp_path, tmp_path).language == "vi"
    assert _asr(tmp_path).language == "vi"


def test_asr_rejects_mps_device(tmp_path):
    # CTranslate2 không có backend Metal: 'mps' phải fail ở boot với hướng dẫn cpu+int8,
    # thay vì một lỗi khó hiểu từ thư viện sau khi đã nạp xong worker.
    with pytest.raises(RuntimeError, match="ASR_COMPUTE_TYPE=int8"):
        _asr(_ready_model_dir(tmp_path), device="mps")._lazy()


def test_asr_passes_device_and_compute_type_to_faster_whisper(tmp_path, monkeypatch):
    # Khoá đường dây cấu hình: ASR_DEVICE/ASR_COMPUTE_TYPE phải tới được WhisperModel.
    # Rơi ngược về mặc định 'default' nghĩa là trọng số float16 nở lên float32 trên CPU —
    # im lặng, chỉ thấy qua một dòng cảnh báo của ctranslate2.
    seen = {}

    class FakeWhisperModel:
        def __init__(self, model_dir, device, compute_type):
            seen.update(model_dir=model_dir, device=device, compute_type=compute_type)

    monkeypatch.setitem(
        sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=FakeWhisperModel)
    )
    model_dir = _ready_model_dir(tmp_path)
    _asr(model_dir, device="cpu", compute_type="int8")._lazy()

    assert seen == {"model_dir": str(model_dir), "device": "cpu", "compute_type": "int8"}


def test_asr_transcribe_is_greedy_word_level_and_returns_ms_segments(tmp_path, monkeypatch):
    # Hợp đồng mới: transcribe() chạy MỘT lần cho cả video, trả mảnh ở mức TỪ có mốc ms để
    # pipeline cắt theo scene; beam_size=1 + word_timestamps=True là chủ ý.
    seen = {}

    class FakeWord:
        def __init__(self, start, end, word):
            self.start, self.end, self.word = start, end, word

    class FakeSegment:
        def __init__(self, start, end, text, words=None):
            self.start, self.end, self.text, self.words = start, end, text, words

    class FakeWhisperModel:
        def __init__(self, model_dir, device, compute_type):
            pass

        def transcribe(self, path, **kwargs):
            seen.update(path=path, kwargs=kwargs)
            return iter([
                FakeSegment(0.0, 1.5, " Xin chào", [FakeWord(0.0, 0.5, " Xin"), FakeWord(0.5, 1.5, " chào")]),
                FakeSegment(2.0, 3.0, "cũ"),  # không có words -> fallback về mức câu
            ]), object()

    monkeypatch.setitem(
        sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=FakeWhisperModel)
    )
    segments = _asr(_ready_model_dir(tmp_path), device="cpu", compute_type="int8").transcribe("a.mp4")

    assert seen["path"] == "/media/a.mp4"  # qua storage-port, không phải path tuyệt đối
    assert seen["kwargs"] == {"language": "vi", "beam_size": 1, "word_timestamps": True}
    assert segments == [
        TranscriptSegment(0, 500, "Xin"),
        TranscriptSegment(500, 1500, "chào"),
        TranscriptSegment(2000, 3000, "cũ"),
    ]

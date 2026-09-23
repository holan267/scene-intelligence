"""Guard air-gap của adapter ASR/OCR (AD-14): thiếu trọng số phải FAIL, không được tải.

Chạy được dù chưa cài faster-whisper/easyocr/vietocr vì adapter kiểm tra đường dẫn TRƯỚC
khi import thư viện — đó cũng chính là điều test này khoá lại: một lần đảo thứ tự sẽ biến
lỗi "thiếu trọng số" thành lượt tải ngầm từ Internet trên node đáng lẽ air-gap.
"""
from __future__ import annotations

import pytest

from pipeline.enrich_backends import PhoWhisperTranscriber, VietOcrReader


class DummyStorage:
    def local_path(self, media_key: str) -> str:
        return f"/media/{media_key}"


def _asr(model_dir) -> PhoWhisperTranscriber:
    return PhoWhisperTranscriber(storage=DummyStorage(), model_dir=str(model_dir))


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

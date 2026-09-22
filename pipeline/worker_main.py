"""Entry point worker: vòng lặp drain hàng đợi ingest. Chạy: `python -m pipeline.worker_main`.

Wiring runtime cho AD-18 (orchestrator finalize job) + reclaim lease (NFR-2, Story 1.7) —
mỗi vòng lặp `drain()` tự requeue/expire task 'claimed' quá hạn, không cần scheduler riêng.
Đơn tiến trình cho MVP; không có `worker_id` (không cần định danh worker cụ thể ở quy mô này).

Đây cũng là nơi DUY NHẤT dựng adapter model thật (PySceneDetect/OpenCV cho detect,
PhoWhisper-large/VietOCR cho enrich) rồi tiêm vào drain() — pipeline.workers giữ thuần
logic hàng đợi, không phụ thuộc OpenCV/faster-whisper.
"""
from __future__ import annotations

import asyncio
import logging

from pipeline.enrich import assert_vietnamese_models
from pipeline.workers import drain
from shared.config import get_settings
from shared.db import get_sessionmaker
from shared.logging import configure_logging
from shared.storage import build_storage

log = logging.getLogger("worker")


def _build_detect_ports(settings, storage):
    """Dựng (detector, extractor) nếu bật DETECT_ON_INGEST; không thì (None, None).

    Import adapter ở đây (không ở module-level) để worker vẫn khởi động được khi tắt
    detect trên máy chưa có OpenCV/scenedetect.
    """
    if not settings.detect_on_ingest:
        log.info("detect tắt theo cấu hình", extra={"stage": "worker-boot"})
        return None, None
    from pipeline.detect_backends import OpenCVKeyframeExtractor, PySceneDetectDetector

    detector = PySceneDetectDetector(storage=storage, threshold=settings.detect_threshold)
    extractor = OpenCVKeyframeExtractor(storage=storage)
    return detector, extractor


def _build_enrich_ports(settings, storage):
    """Dựng (transcriber, ocr) nếu bật ENRICH_ON_INGEST; không thì (None, None).

    Import guarded như detect: faster-whisper/easyocr/vietocr không phải dependency của
    project (xem ghi chú `enrich_on_ingest` trong shared/config.py) nên chỉ chạm tới khi
    thật sự bật. Guard AD-9 chạy ngay ở boot: cấu hình sai model làm worker chết ngay,
    thay vì âm thầm đẩy từng task vào 'error'.
    """
    if not settings.enrich_on_ingest:
        log.info("enrich ASR/OCR tắt theo cấu hình", extra={"stage": "worker-boot"})
        return None, None
    from pipeline.enrich_backends import PhoWhisperTranscriber, VietOcrReader

    transcriber = PhoWhisperTranscriber(storage=storage, model_dir=settings.asr_model_dir)
    ocr = VietOcrReader()
    assert_vietnamese_models(transcriber, ocr)  # AD-9
    log.info("enrich ASR/OCR bật (PhoWhisper-large + VietOCR)", extra={"stage": "worker-boot"})
    return transcriber, ocr


async def _loop(poll_seconds: float = 2.0) -> None:
    configure_logging()
    settings = get_settings()
    # storage dựng vô điều kiện: enrich cần port đọc keyframe kể cả khi tắt detect.
    storage = build_storage(settings)
    detector, extractor = _build_detect_ports(settings, storage)
    transcriber, ocr = _build_enrich_ports(settings, storage)
    maker = get_sessionmaker()
    while True:
        async with maker() as session:
            result = await drain(
                session, detector=detector, extractor=extractor, storage=storage,
                transcriber=transcriber, ocr=ocr,
            )
            await session.commit()
        if result["processed"]:
            # JsonFormatter chỉ giữ các khoá trong _EXTRA_FIELDS -> số task vào message
            log.info(
                f"drained {result['processed']} task", extra={"stage": "ingest-drain"}
            )
        await asyncio.sleep(poll_seconds)


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(_loop())

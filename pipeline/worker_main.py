"""Entry point worker: vòng lặp drain hàng đợi ingest. Chạy: `python -m pipeline.worker_main`.

Wiring runtime cho AD-18 (orchestrator finalize job) + reclaim lease (NFR-2, Story 1.7) —
mỗi vòng lặp `drain()` tự requeue/expire task 'claimed' quá hạn, không cần scheduler riêng.
Đơn tiến trình cho MVP; không có `worker_id` (không cần định danh worker cụ thể ở quy mô này).

Đây cũng là nơi DUY NHẤT dựng adapter decode thật (PySceneDetect/OpenCV) rồi tiêm vào
drain() — pipeline.workers giữ thuần logic hàng đợi, không phụ thuộc OpenCV.
"""
from __future__ import annotations

import asyncio
import logging

from pipeline.workers import drain
from shared.config import get_settings
from shared.db import get_sessionmaker
from shared.logging import configure_logging
from shared.storage import build_storage

log = logging.getLogger("worker")


def _build_detect_ports(settings):
    """Dựng (detector, extractor, storage) nếu bật DETECT_ON_INGEST; không thì (None,)*3.

    Import adapter ở đây (không ở module-level) để worker vẫn khởi động được khi tắt
    detect trên máy chưa có OpenCV/scenedetect.
    """
    if not settings.detect_on_ingest:
        log.info("detect tắt theo cấu hình", extra={"stage": "worker-boot"})
        return None, None, None
    from pipeline.detect_backends import OpenCVKeyframeExtractor, PySceneDetectDetector

    storage = build_storage(settings)
    detector = PySceneDetectDetector(storage=storage, threshold=settings.detect_threshold)
    extractor = OpenCVKeyframeExtractor(storage=storage)
    return detector, extractor, storage


async def _loop(poll_seconds: float = 2.0) -> None:
    configure_logging()
    settings = get_settings()
    detector, extractor, storage = _build_detect_ports(settings)
    maker = get_sessionmaker()
    while True:
        async with maker() as session:
            result = await drain(
                session, detector=detector, extractor=extractor, storage=storage
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

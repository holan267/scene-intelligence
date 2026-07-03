"""Entry point worker: vòng lặp drain hàng đợi ingest. Chạy: `python -m pipeline.worker_main`.

Wiring runtime cho AD-18 (orchestrator finalize job) + reclaim lease (NFR-2, Story 1.7) —
mỗi vòng lặp `drain()` tự requeue/expire task 'claimed' quá hạn, không cần scheduler riêng.
Đơn tiến trình cho MVP; không có `worker_id` (không cần định danh worker cụ thể ở quy mô này).
"""
from __future__ import annotations

import asyncio
import logging

from pipeline.workers import drain
from shared.db import get_sessionmaker
from shared.logging import configure_logging

log = logging.getLogger("worker")


async def _loop(poll_seconds: float = 2.0) -> None:
    configure_logging()
    maker = get_sessionmaker()
    while True:
        async with maker() as session:
            result = await drain(session)
            await session.commit()
        if result["processed"]:
            log.info("drained", extra={"stage": "ingest-drain"})
        await asyncio.sleep(poll_seconds)


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(_loop())

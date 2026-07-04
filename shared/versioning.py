"""Freshness checksum cho derived-artifact (AD-16) — dùng chung giữa pipeline/ và search/.

Tách riêng vào shared/ (thay vì chỉ sống trong pipeline/embed_index.py) vì search/ không
được phép import từ pipeline/ (ranh giới CQRS-lite ingest/search — AD-2).
"""
from __future__ import annotations

import hashlib


def doc_version(scene_document: str) -> str:
    """Checksum sha256 của scene_document — freshness của derived-artifact (AD-16)."""
    return hashlib.sha256(scene_document.encode()).hexdigest()

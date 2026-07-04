from __future__ import annotations

from shared.versioning import doc_version


def test_doc_version_is_deterministic_sha256():
    v1 = doc_version("Bản tin thời sự")
    v2 = doc_version("Bản tin thời sự")
    v3 = doc_version("Bản tin khác")
    assert v1 == v2
    assert v1 != v3
    assert len(v1) == 64  # sha256 hex

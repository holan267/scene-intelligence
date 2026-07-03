from __future__ import annotations

from shared.config import Settings


def test_defaults():
    s = Settings(_env_file=None)
    assert s.media_backend == "filesystem"
    assert s.api_env == "dev"


def test_env_override(monkeypatch):
    monkeypatch.setenv("MEDIA_ROOT", "/mnt/nas/media")
    s = Settings(_env_file=None)
    assert s.media_root == "/mnt/nas/media"

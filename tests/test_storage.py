from __future__ import annotations

import pytest

from shared.storage import FilesystemStorage, StoragePort


def test_roundtrip(tmp_path):
    s = FilesystemStorage(tmp_path)
    s.put("a/b.bin", b"hello")
    assert s.exists("a/b.bin")
    assert s.get("a/b.bin") == b"hello"
    with s.open_stream("a/b.bin") as f:
        assert f.read() == b"hello"
    s.delete("a/b.bin")
    assert not s.exists("a/b.bin")


def test_traversal_blocked(tmp_path):
    # AD-23: media-key không được thoát khỏi MEDIA_ROOT
    s = FilesystemStorage(tmp_path)
    with pytest.raises(ValueError):
        s.put("../evil.bin", b"x")


def test_empty_key(tmp_path):
    s = FilesystemStorage(tmp_path)
    with pytest.raises(ValueError):
        s.get("")


def test_healthcheck(tmp_path):
    assert FilesystemStorage(tmp_path).healthcheck() is True


def test_satisfies_port(tmp_path):
    assert isinstance(FilesystemStorage(tmp_path), StoragePort)

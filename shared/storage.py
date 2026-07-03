"""Storage-port trừu tượng cho media (AD-23).

Mọi truy cập media qua port này theo media-key (không path tuyệt đối ở call-site). MVP hiện
thực bằng filesystem (NAS/local mounted volume). `local_path` cho phép thư viện decode video
(cv2/scenedetect) nhận đường dẫn mà vẫn đi qua port; adapter S3 sau sẽ stream ra temp.
"""
from __future__ import annotations

from pathlib import Path
from typing import BinaryIO, Protocol, runtime_checkable

from shared.config import Settings, get_settings


@runtime_checkable
class StoragePort(Protocol):
    """Hợp đồng put/get/stream/delete media theo media-key."""

    def put(self, media_key: str, data: bytes) -> None: ...
    def get(self, media_key: str) -> bytes: ...
    def open_stream(self, media_key: str) -> BinaryIO: ...
    def exists(self, media_key: str) -> bool: ...
    def delete(self, media_key: str) -> None: ...
    def local_path(self, media_key: str) -> str: ...
    def healthcheck(self) -> bool: ...


class FilesystemStorage:
    """Adapter filesystem: media-key -> đường dẫn dưới MEDIA_ROOT (chống path traversal)."""

    def __init__(self, root: str | Path) -> None:
        # KHÔNG auto-mkdir ở đây: để healthcheck phản ánh đúng khi NAS chưa mount.
        self._root = Path(root).resolve()

    def _resolve(self, media_key: str) -> Path:
        key = media_key.strip().lstrip("/\\")
        if not key:
            raise ValueError("media_key rỗng")
        target = (self._root / key).resolve()
        if self._root != target and self._root not in target.parents:
            raise ValueError(f"media_key thoát khỏi MEDIA_ROOT: {media_key!r}")
        return target

    def put(self, media_key: str, data: bytes) -> None:
        target = self._resolve(media_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def get(self, media_key: str) -> bytes:
        return self._resolve(media_key).read_bytes()

    def open_stream(self, media_key: str) -> BinaryIO:
        return self._resolve(media_key).open("rb")

    def exists(self, media_key: str) -> bool:
        return self._resolve(media_key).is_file()

    def delete(self, media_key: str) -> None:
        target = self._resolve(media_key)
        if target.is_file():
            target.unlink()

    def local_path(self, media_key: str) -> str:
        """Đường dẫn thật cho decoder (vẫn qua port; chỉ filesystem adapter có)."""
        return str(self._resolve(media_key))

    def healthcheck(self) -> bool:
        """Kho media THỰC SỰ ghi được? (write-probe -> bắt cả read-only mount)."""
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            probe = self._root / ".healthprobe"
            probe.write_bytes(b"ok")
            probe.unlink()
            return True
        except OSError:
            return False


def build_storage(settings: Settings | None = None) -> StoragePort:
    """Factory: chọn adapter theo config (MVP chỉ filesystem)."""
    settings = settings or get_settings()
    if settings.media_backend == "filesystem":
        return FilesystemStorage(settings.media_root)
    raise ValueError(f"media_backend chưa hỗ trợ: {settings.media_backend!r}")

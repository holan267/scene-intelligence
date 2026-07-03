"""Adapter decode video thật cho detect (PySceneDetect + OpenCV).

Import nặng lazy + guarded. Truy cập media QUA storage-port (`local_path`) thay vì tự ghép
path (AD-23). Cần `scenedetect`/`opencv-python`; wheel nạp sẵn cho air-gap (AD-14). CHƯA chạy
trong môi trường dev hiện tại.
"""
from __future__ import annotations

from pipeline.detect import DetectedScene, DetectedShot, Detection
from shared.storage import StoragePort, build_storage


class PySceneDetectDetector:
    """Tách scene/shot bằng PySceneDetect (ContentDetector)."""

    def __init__(self, storage: StoragePort | None = None, threshold: float = 27.0) -> None:
        self._storage = storage or build_storage()
        self._threshold = threshold

    def detect(self, media_key: str) -> Detection:
        try:
            from scenedetect import ContentDetector, SceneManager, open_video
        except ImportError as exc:  # pragma: no cover - phụ thuộc production
            raise RuntimeError("Cần cài `scenedetect` để chạy PySceneDetectDetector") from exc

        video = open_video(self._storage.local_path(media_key))  # qua port (AD-23)
        manager = SceneManager()
        manager.add_detector(ContentDetector(threshold=self._threshold))
        manager.detect_scenes(video)
        fps = float(video.frame_rate)
        scenes: list[DetectedScene] = []
        for start, end in manager.get_scene_list():
            s_ms = int(start.get_seconds() * 1000)
            e_ms = int(end.get_seconds() * 1000)
            scenes.append(DetectedScene(s_ms, e_ms, (DetectedShot(s_ms, e_ms),)))
        return Detection(framerate=fps, scenes=tuple(scenes))


class OpenCVKeyframeExtractor:
    """Trích keyframe tại timecode bằng OpenCV; trả (jpg bytes, pixels 8x8 grayscale)."""

    def __init__(self, storage: StoragePort | None = None) -> None:
        self._storage = storage or build_storage()

    def extract(self, media_key: str, at_ms: int) -> tuple[bytes, bytes]:
        try:
            import cv2
        except ImportError as exc:  # pragma: no cover - phụ thuộc production
            raise RuntimeError("Cần cài `opencv-python` để chạy OpenCVKeyframeExtractor") from exc

        cap = cv2.VideoCapture(self._storage.local_path(media_key))  # qua port (AD-23)
        cap.set(cv2.CAP_PROP_POS_MSEC, at_ms)
        ok, frame = cap.read()
        cap.release()
        if not ok:
            raise RuntimeError(f"Không đọc được keyframe tại {at_ms}ms: {media_key}")
        ok, buf = cv2.imencode(".jpg", frame)
        gray = cv2.cvtColor(cv2.resize(frame, (8, 8)), cv2.COLOR_BGR2GRAY)
        return bytes(buf), gray.tobytes()

"""Adapter face/object thật (Story 1.5). Guarded import — chưa chạy môi trường dev.

- InsightFaceRecognizer: InsightFace (buffalo_l) — phát hiện khuôn mặt + embedding.
- YoloObjectDetector: Ultralytics YOLO26 — phát hiện đối tượng kèm confidence.
Ảnh keyframe truyền vào `detect()` là bytes JPEG lấy qua storage-port ở caller
(`enrich_scene_vision`) — adapter chỉ decode bytes, không tự đọc storage (AD-23).
Cần `insightface`/`onnxruntime` và `ultralytics`.
"""
from __future__ import annotations

from pipeline.enrich_vision import FaceDetection, ObjectDetection


class InsightFaceRecognizer:
    """Phát hiện khuôn mặt + embedding bằng InsightFace (buffalo_l) — ⚠️ non-commercial license."""

    def __init__(self, model_name: str = "buffalo_l") -> None:
        self._app = None
        self._model_name = model_name

    def _lazy(self):  # pragma: no cover - phụ thuộc production
        if self._app is None:
            from insightface.app import FaceAnalysis

            self._app = FaceAnalysis(name=self._model_name)
            self._app.prepare(ctx_id=0)
        return self._app

    def detect(self, image: bytes) -> list[FaceDetection]:  # pragma: no cover - phụ thuộc production
        try:
            app = self._lazy()
        except ImportError as exc:
            raise RuntimeError("Cần cài `insightface` (+ onnxruntime) để nhận diện khuôn mặt") from exc
        import cv2
        import numpy as np

        arr = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR)
        if arr is None:
            raise RuntimeError("Không decode được keyframe (ảnh hỏng/rỗng)")
        faces = app.get(arr)
        return [FaceDetection(embedding=face.normed_embedding.tolist()) for face in faces]


class YoloObjectDetector:
    """Phát hiện đối tượng bằng Ultralytics YOLO26 — ⚠️ AGPL-3.0, rà license trước thương mại hoá."""

    def __init__(self, weights: str = "yolo26n.pt", confidence_threshold: float = 0.25) -> None:
        self._model = None
        self._weights = weights
        self._confidence_threshold = confidence_threshold

    def _lazy(self):  # pragma: no cover - phụ thuộc production
        if self._model is None:
            from ultralytics import YOLO

            self._model = YOLO(self._weights)
        return self._model

    def detect(self, image: bytes) -> list[ObjectDetection]:  # pragma: no cover - phụ thuộc production
        try:
            model = self._lazy()
        except ImportError as exc:
            raise RuntimeError("Cần cài `ultralytics` để nhận diện đối tượng") from exc
        import cv2
        import numpy as np

        arr = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR)
        if arr is None:
            raise RuntimeError("Không decode được keyframe (ảnh hỏng/rỗng)")
        results = model.predict(arr, conf=self._confidence_threshold, verbose=False)
        out: list[ObjectDetection] = []
        for r in results:
            for box in r.boxes:
                label = r.names[int(box.cls[0])]
                out.append(ObjectDetection(label=label, confidence=float(box.conf[0])))
        return out

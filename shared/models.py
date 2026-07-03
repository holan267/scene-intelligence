"""Schema cơ sở: Video & Scene (chỉ những gì Story 1.1 cần — AD-1, AD-4, AD-12).

Cột enrichment (transcript, ocr, faces, objects, scene_document, embedding...) được thêm
ở các story sau, mỗi story chỉ tạo cột nó cần. KHÔNG dựng toàn bộ schema ở đây.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Video(Base):
    __tablename__ = "video"

    video_id: Mapped[str] = mapped_column(String(64), primary_key=True)  # id ổn định (AD-1)
    # fps ở cấp Video (AD-12); nullable vì xác định lúc detect (Story 1.3), chưa biết khi ingest
    framerate: Mapped[float | None] = mapped_column(Float, nullable=True)
    # media-key (AD-23); UNIQUE -> một source_key = một Video (idempotent, AD-5)
    source_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    scenes: Mapped[list["Scene"]] = relationship(back_populates="video")


class Scene(Base):
    __tablename__ = "scene"

    # scene_id bất biến (UUID5 tất định), KHÔNG positional (AD-1)
    scene_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    video_id: Mapped[str] = mapped_column(ForeignKey("video.video_id"), nullable=False, index=True)
    start_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)  # timecode ms (AD-12)
    end_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # cổng hiển thị (AD-17): chỉ 'indexed' mới vào kết quả search (bật ở story sau)
    search_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    # Làm giàu tiếng Việt (Story 1.4, AD-5 cột riêng): điền bởi stage ASR/OCR
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)  # ASR (AD-9)
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)  # OCR (AD-9)
    # Làm giàu thị giác (Story 1.5, AD-5 cột riêng của stage object): JSON list [{label, confidence}]
    objects: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    video: Mapped[Video] = relationship(back_populates="scenes")


class Person(Base):
    """Registry danh tính đã đăng ký (MC, chính khách…) cho face-match (Story 1.5, AD-11)."""

    __tablename__ = "person"

    person_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    # JSON list[float] — face embedding tham chiếu để so cosine similarity (không pgvector ở story này)
    reference_embedding: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FaceAppearance(Base):
    """Một khuôn mặt phát hiện trên Scene, khớp (hoặc không) với Person đã đăng ký (AD-11).

    Bảng riêng của stage face (không phải cột JSONB dùng chung trên Scene — AD-5).
    """

    __tablename__ = "face_appearance"

    appearance_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scene_id: Mapped[str] = mapped_column(ForeignKey("scene.scene_id"), nullable=False, index=True)
    # None = "không xác định" (confidence < ngưỡng hoặc không khớp ai đã đăng ký — AD-11)
    person_id: Mapped[str | None] = mapped_column(ForeignKey("person.person_id"), nullable=True, index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Shot(Base):
    """Đoạn quay trong Scene; có 1 Keyframe đại diện (AD-6). Model thị giác chỉ chạy trên Keyframe."""

    __tablename__ = "shot"

    shot_id: Mapped[str] = mapped_column(String(64), primary_key=True)  # bất biến (AD-1)
    scene_id: Mapped[str] = mapped_column(ForeignKey("scene.scene_id"), nullable=False, index=True)
    video_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    start_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)  # timecode ms (AD-12)
    end_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    keyframe_key: Mapped[str | None] = mapped_column(String(512), nullable=True)  # media-key (AD-23)
    phash: Mapped[str | None] = mapped_column(String(64), nullable=True)  # perceptual hash hex (AD-6)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Job(Base):
    """Batch job (AD-10, AD-18) — domain do orchestrator sở hữu."""

    __tablename__ = "job"

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="ingest_batch")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IngestTask(Base):
    """Một task nạp/đăng ký một video trong lô. source_key unique -> idempotent (AD-5)."""

    __tablename__ = "ingest_task"

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("job.job_id"), nullable=False, index=True)
    source_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    video_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

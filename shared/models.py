"""Schema cơ sở: Video & Scene (chỉ những gì Story 1.1 cần — AD-1, AD-4, AD-12).

Cột enrichment (transcript, ocr, faces, objects, scene_document, embedding...) được thêm
ở các story sau, mỗi story chỉ tạo cột nó cần. KHÔNG dựng toàn bộ schema ở đây.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Video(Base):
    __tablename__ = "video"

    video_id: Mapped[str] = mapped_column(String(64), primary_key=True)  # id ổn định (AD-1)
    framerate: Mapped[float] = mapped_column(Float, nullable=False)  # fps ở cấp Video (AD-12)
    source_key: Mapped[str] = mapped_column(String(512), nullable=False)  # media-key (AD-23)
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    video: Mapped[Video] = relationship(back_populates="scenes")

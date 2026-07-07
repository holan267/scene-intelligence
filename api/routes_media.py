"""API phục vụ media — thumbnail Scene + stream Video gốc (Story 3.1, FR-9, AD-19, AD-23).

Không có auth/token (quyết định scope đã xác nhận với Lan — xem story 3.1 Scope
Decision #1): mạng nội bộ/air-gap (NFR-7) là ranh giới bảo mật duy nhất cho MVP.
Phần còn lại của AD-19 vẫn áp dụng: UI không bao giờ nhận media-key/path filesystem
thật — chỉ nhận bytes/stream qua endpoint này.
"""
from __future__ import annotations

import mimetypes
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db import get_session
from shared.models import Scene, Shot, Video
from shared.storage import build_storage

router = APIRouter(prefix="/api/v1")


@router.get("/scenes/{scene_id}/thumbnail", responses={404: {"description": "not found"}})
async def scene_thumbnail(
    scene_id: str, session: Annotated[AsyncSession, Depends(get_session)]
) -> Response:
    """Ảnh keyframe của Shot có start_ms nhỏ nhất trong Scene (AC #1, #2)."""
    scene = await session.get(Scene, scene_id)
    if scene is None:
        raise HTTPException(status_code=404, detail="scene not found")

    shot = (
        await session.execute(
            select(Shot)
            .where(Shot.scene_id == scene_id)
            .order_by(Shot.start_ms.asc(), Shot.shot_id.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    # `not shot.keyframe_key` (không phải `is None`) — review fix: chuỗi rỗng "" cũng
    # phải bị chặn ở đây, nếu không sẽ lọt xuống storage._resolve() raise ValueError.
    if shot is None or not shot.keyframe_key:
        raise HTTPException(status_code=404, detail="no keyframe available")

    storage = build_storage()
    # Review fix: DB có row nhưng file đã mất trên disk -> 404 sạch, không phải 500.
    if not storage.exists(shot.keyframe_key):
        raise HTTPException(status_code=404, detail="keyframe file missing")
    data = storage.get(shot.keyframe_key)  # [ASSUMPTION] keyframe luôn JPEG (Story 1.3)
    return Response(content=data, media_type="image/jpeg")


@router.get("/videos/{video_id}/stream", responses={404: {"description": "not found"}})
async def video_stream(
    video_id: str, session: Annotated[AsyncSession, Depends(get_session)]
) -> FileResponse:
    """Stream video gốc qua storage-port + HTTP Range (AC #3, #4).

    Dùng `storage.local_path()` (escape hatch có chủ đích — xem shared/storage.py) để
    Starlette FileResponse tự xử lý Range/206 trên path filesystem thật — KHÔNG tự
    viết logic Range thủ công. KHÔNG truyền `filename=` — mặc định sẽ ép
    Content-Disposition: attachment, phá phát inline trong <video> (AC #5).

    Giới hạn đã biết: trình duyệt HTML5 <video> chỉ phát được codec/container nó hỗ
    trợ (thường H.264/AAC trong MP4) — nguồn MOV/MXF/MPEG-TS (FR-1) có thể KHÔNG phát
    trực tiếp được. Transcode sang proxy web-compatible là việc riêng, xem
    deferred-work.md.
    """
    video = await session.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="video not found")

    storage = build_storage()
    # Review fix: DB có row nhưng file đã mất trên disk -> 404 sạch (FileResponse tự
    # stat() file lúc gửi response, không phải lúc khởi tạo -> raise muộn thành 500
    # nếu không kiểm tra trước ở đây).
    if not storage.exists(video.source_key):
        raise HTTPException(status_code=404, detail="video file missing")
    path = storage.local_path(video.source_key)
    media_type = mimetypes.guess_type(video.source_key)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type)

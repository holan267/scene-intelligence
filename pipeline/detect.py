"""Tách Scene→Shot→Keyframe + perceptual-hash dedupe + persist idempotent (Story 1.3).

Decode video thật ở adapter (detect_backends.py). Ở đây chỉ logic thuần (hash, dedupe,
upsert theo id tất định, reconcile row cũ) để test không cần video/GPU.
AD-1 (id bất biến + reconcile orphan), AD-6 (keyframe + dedupe), AD-11/AD-23 (ghi dẫn xuất qua port).

Lưu ý (defer, deferred-work.md): id suy từ boundary -> re-detect lệch ms vẫn re-mint;
reconcile dọn row mồ côi nhưng "id ổn định-qua-drift" là story riêng. aHash là placeholder.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.ids import scene_id as make_scene_id
from shared.ids import shot_id as make_shot_id
from shared.models import Scene, Shot, Video
from shared.storage import StoragePort


@dataclass(frozen=True)
class DetectedShot:
    start_ms: int
    end_ms: int


@dataclass(frozen=True)
class DetectedScene:
    start_ms: int
    end_ms: int
    shots: tuple[DetectedShot, ...]


@dataclass(frozen=True)
class Detection:
    framerate: float
    scenes: tuple[DetectedScene, ...]


class SceneDetector(Protocol):
    def detect(self, media_key: str) -> Detection: ...


class KeyframeExtractor(Protocol):
    def extract(self, media_key: str, at_ms: int) -> tuple[bytes, bytes]:
        """Trả (ảnh keyframe bytes để lưu, pixels grayscale nhỏ để hash)."""
        ...


def average_hash(pixels: bytes) -> int:
    """aHash: bit_i = 1 nếu pixel_i >= trung bình (AD-6, placeholder)."""
    if not pixels:
        raise ValueError("pixels rỗng")
    mean = sum(pixels) / len(pixels)
    bits = 0
    for i, p in enumerate(pixels):
        if p >= mean:
            bits |= 1 << i
    return bits


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def _validate_span(start_ms: int, end_ms: int, what: str) -> None:
    if start_ms < 0 or end_ms <= start_ms:
        raise ValueError(f"{what} có timecode không hợp lệ: start_ms={start_ms}, end_ms={end_ms}")


async def persist_detection(
    session: AsyncSession,
    storage: StoragePort,
    video_id: str,
    detection: Detection,
    extractor: KeyframeExtractor,
    *,
    phash_threshold: int = 5,
) -> dict:
    """Upsert Scene/Shot theo id tất định + keyframe (dedupe phash) + reconcile row cũ."""
    video = await session.get(Video, video_id)
    if video is None:
        raise ValueError(f"video không tồn tại: {video_id}")
    video.framerate = detection.framerate

    kept: list[tuple[int, str]] = []  # (phash, keyframe_key) đã lưu trong video này
    new_scene_ids: set[str] = set()
    new_shot_ids: set[str] = set()
    n_scenes = n_shots = kf_stored = kf_deduped = 0

    for sc in detection.scenes:
        _validate_span(sc.start_ms, sc.end_ms, "Scene")
        sid = make_scene_id(video_id, sc.start_ms, sc.end_ms)
        new_scene_ids.add(sid)
        scene = await session.get(Scene, sid)
        if scene is None:
            session.add(Scene(scene_id=sid, video_id=video_id, start_ms=sc.start_ms, end_ms=sc.end_ms))
            n_scenes += 1
        else:
            scene.start_ms, scene.end_ms = sc.start_ms, sc.end_ms

        for sh in sc.shots:
            _validate_span(sh.start_ms, sh.end_ms, "Shot")
            shid = make_shot_id(sid, sh.start_ms, sh.end_ms)
            new_shot_ids.add(shid)
            image, pixels = extractor.extract(video.source_key, sh.start_ms)
            h = average_hash(pixels)
            reuse = next(((ph, k) for (ph, k) in kept if hamming(ph, h) <= phash_threshold), None)
            if reuse is not None:
                kept_hash, kf_key = reuse  # phash nhất quán với keyframe được tái dùng (P3.1)
                kf_deduped += 1
            else:
                kept_hash = h
                kf_key = f"{video_id}/keyframes/{shid}.jpg"  # media-key dẫn xuất (AD-23)
                if not storage.exists(kf_key):  # re-detect không ghi lại (P3.2)
                    storage.put(kf_key, image)
                kept.append((h, kf_key))
                kf_stored += 1

            shot = await session.get(Shot, shid)
            phash_hex = format(kept_hash, "x")
            if shot is None:
                session.add(Shot(shot_id=shid, scene_id=sid, video_id=video_id,
                                 start_ms=sh.start_ms, end_ms=sh.end_ms,
                                 keyframe_key=kf_key, phash=phash_hex))
                n_shots += 1
            else:
                shot.start_ms, shot.end_ms = sh.start_ms, sh.end_ms
                shot.keyframe_key, shot.phash = kf_key, phash_hex

    await session.flush()
    deleted = await _reconcile(session, storage, video_id, new_scene_ids, new_shot_ids)
    await session.flush()
    return {
        "scenes": n_scenes,
        "shots": n_shots,
        "keyframes_stored": kf_stored,
        "keyframes_deduped": kf_deduped,
        "scenes_deleted": deleted["scenes"],
        "shots_deleted": deleted["shots"],
    }


async def _reconcile(
    session: AsyncSession,
    storage: StoragePort,
    video_id: str,
    keep_scene_ids: set[str],
    keep_shot_ids: set[str],
) -> dict:
    """Xoá Scene/Shot cũ không còn trong detection mới + keyframe mồ côi (AD-1 chống mồ côi)."""
    existing_shots = (
        await session.execute(select(Shot).where(Shot.video_id == video_id))
    ).scalars().all()
    removed_keys: set[str] = set()
    surviving_keys: set[str] = set()
    shots_deleted = 0
    for sh in existing_shots:
        if sh.shot_id not in keep_shot_ids:
            if sh.keyframe_key:
                removed_keys.add(sh.keyframe_key)
            await session.delete(sh)
            shots_deleted += 1
        elif sh.keyframe_key:
            surviving_keys.add(sh.keyframe_key)

    existing_scenes = (
        await session.execute(select(Scene).where(Scene.video_id == video_id))
    ).scalars().all()
    scenes_deleted = 0
    for scn in existing_scenes:
        if scn.scene_id not in keep_scene_ids:
            await session.delete(scn)
            scenes_deleted += 1

    for key in removed_keys - surviving_keys:  # chỉ xoá keyframe không còn shot nào dùng
        storage.delete(key)

    return {"scenes": scenes_deleted, "shots": shots_deleted}

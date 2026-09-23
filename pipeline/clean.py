"""Dọn dữ liệu ingest — xoá dữ liệu DẪN XUẤT để nạp lại từ đầu (AD-4, AD-23).

Chạy: `python -m pipeline.clean --dry-run` (xem trước) rồi `python -m pipeline.clean --yes`.

Phạm vi xoá (mọi thứ pipeline sinh ra từ media gốc):
  scene_embedding -> face_appearance -> shot -> scene -> video -> ingest_task -> job
  + keyframe dưới `<video_id>/keyframes/` (dẫn xuất — xem deploy/backup.sh, loại trừ khỏi backup).

KHÔNG đụng tới file video gốc trong MEDIA_ROOT: đó là dữ liệu đầu vào, không phải dữ liệu
ingest. Sau khi dọn, nạp lại bằng POST /ingest (api/routes_ingest.py) là dựng lại được 100%
(AD-4: Postgres là SoT, mọi thứ ở trên đều rebuild được từ SoT + media gốc).

Thứ tự xoá đi ngược chiều khoá ngoại nên chạy được cả khi DB bật FK cứng (Postgres) lẫn
sqlite trong test.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import get_settings
from shared.db import get_sessionmaker
from shared.logging import configure_logging
from shared.models import (
    FaceAppearance,
    IngestTask,
    Job,
    Scene,
    SceneEmbedding,
    Shot,
    Video,
)
from shared.storage import StoragePort, build_storage

log = logging.getLogger("clean")

KEYFRAME_DIR_NAME = "keyframes"  # khớp media-key dựng ở pipeline/detect.py


class Scope:
    """Tập video/source_key bị dọn. `all_videos=True` -> dọn sạch mọi thứ."""

    def __init__(self, *, all_videos: bool, video_ids: set[str], source_keys: set[str]) -> None:
        self.all_videos = all_videos
        self.video_ids = video_ids
        self.source_keys = source_keys

    def __repr__(self) -> str:  # pragma: no cover - chỉ để debug
        if self.all_videos:
            return "Scope(all)"
        return f"Scope(videos={len(self.video_ids)}, keys={len(self.source_keys)})"


async def resolve_scope(
    session: AsyncSession,
    *,
    video_ids: Sequence[str] | None = None,
    source_keys: Sequence[str] | None = None,
) -> Scope:
    """Đổi tham số CLI thành Scope. Không truyền gì -> dọn TẤT CẢ.

    Video khớp theo video_id HOẶC source_key; source_key của video khớp cũng được gom vào
    để ingest_task tương ứng bị xoá cùng (nếu không, task 'done' còn sót sẽ chặn nạp lại
    do dedupe trong enqueue_batch).
    """
    vids = {v for v in (video_ids or []) if v}
    keys = {k for k in (source_keys or []) if k}
    if not vids and not keys:
        return Scope(all_videos=True, video_ids=set(), source_keys=set())

    rows = (
        await session.execute(
            select(Video.video_id, Video.source_key).where(
                Video.video_id.in_(vids) | Video.source_key.in_(keys)
            )
        )
    ).all()
    for vid, key in rows:
        vids.add(vid)
        keys.add(key)
    return Scope(all_videos=False, video_ids=vids, source_keys=keys)


def _scene_ids_q(scope: Scope):
    q = select(Scene.scene_id)
    return q if scope.all_videos else q.where(Scene.video_id.in_(scope.video_ids))


def _shots_q(scope: Scope):
    q = select(Shot.shot_id)
    return q if scope.all_videos else q.where(Shot.video_id.in_(scope.video_ids))


async def _count(session: AsyncSession, model, *where) -> int:
    q = select(func.count()).select_from(model)
    if where:
        q = q.where(*where)
    return int((await session.execute(q)).scalar_one())


async def count_targets(session: AsyncSession, scope: Scope) -> dict[str, int]:
    """Đếm số dòng SẼ bị xoá — dùng cho --dry-run và cho dòng tổng kết."""
    scene_ids = _scene_ids_q(scope).scalar_subquery()
    if scope.all_videos:
        return {
            "scene_embeddings": await _count(session, SceneEmbedding),
            "face_appearances": await _count(session, FaceAppearance),
            "shots": await _count(session, Shot),
            "scenes": await _count(session, Scene),
            "videos": await _count(session, Video),
            "ingest_tasks": await _count(session, IngestTask),
            "jobs": await _count(session, Job),
        }
    return {
        "scene_embeddings": await _count(session, SceneEmbedding, SceneEmbedding.scene_id.in_(scene_ids)),
        "face_appearances": await _count(session, FaceAppearance, FaceAppearance.scene_id.in_(scene_ids)),
        "shots": await _count(session, Shot, Shot.video_id.in_(scope.video_ids)),
        "scenes": await _count(session, Scene, Scene.video_id.in_(scope.video_ids)),
        "videos": await _count(session, Video, Video.video_id.in_(scope.video_ids)),
        "ingest_tasks": await _count(session, IngestTask, IngestTask.source_key.in_(scope.source_keys)),
        "jobs": 0,  # job chỉ bị xoá khi không còn task nào -> đếm ở bước xoá
    }


async def _keyframe_keys(session: AsyncSession, scope: Scope) -> set[str]:
    q = select(Shot.keyframe_key).where(Shot.keyframe_key.is_not(None))
    if not scope.all_videos:
        q = q.where(Shot.video_id.in_(scope.video_ids))
    return {k for (k,) in (await session.execute(q)).all() if k}


def delete_keyframes(storage: StoragePort, keys: set[str]) -> int:
    """Xoá keyframe qua storage-port (AD-23). Best-effort: 1 key hỏng không chặn phần còn lại."""
    removed = 0
    for key in sorted(keys):
        try:
            storage.delete(key)
            removed += 1
        except (OSError, ValueError) as exc:
            log.warning(f"không xoá được keyframe {key}: {exc}", extra={"stage": "clean"})
    return removed


def sweep_keyframe_dirs(media_root: str | Path, *, purge: bool) -> int:
    """Dọn thư mục `<video_id>/keyframes/` còn lại dưới MEDIA_ROOT.

    `purge=True` (dọn toàn bộ) xoá cả cây, bắt được keyframe mồ côi khi DB đã mất dòng Shot
    trỏ tới nó. `purge=False` (dọn theo video) chỉ xoá thư mục RỖNG -> không bao giờ chạm
    vào keyframe của video ngoài phạm vi.
    """
    root = Path(media_root)
    if not root.is_dir():
        return 0
    swept = 0
    for d in sorted(root.rglob(KEYFRAME_DIR_NAME)):
        if not d.is_dir():
            continue
        if purge:
            shutil.rmtree(d, ignore_errors=True)
            swept += 1
        elif not any(d.iterdir()):
            d.rmdir()
            swept += 1
    return swept


async def clean_ingest(
    session: AsyncSession,
    storage: StoragePort | None = None,
    *,
    scope: Scope,
    drop_keyframes: bool = True,
    dry_run: bool = False,
) -> dict:
    """Xoá dữ liệu ingest trong `scope`. Trả về số lượng từng loại đã (hoặc sẽ) xoá.

    KHÔNG commit — caller quyết định (drain/worker giữ cùng quy ước). `dry_run=True` chỉ
    đếm, không xoá dòng nào và không chạm file.
    """
    counts = await count_targets(session, scope)
    keys = await _keyframe_keys(session, scope) if drop_keyframes else set()
    counts["keyframes"] = len(keys)
    if dry_run:
        counts["dry_run"] = True
        return counts

    scene_ids = _scene_ids_q(scope).scalar_subquery()
    # Ngược chiều FK: embedding/face -> shot -> scene -> video -> task -> job.
    if scope.all_videos:
        await session.execute(delete(SceneEmbedding))
        await session.execute(delete(FaceAppearance))
        await session.execute(delete(Shot))
        await session.execute(delete(Scene))
        await session.execute(delete(Video))
        await session.execute(delete(IngestTask))
        result = await session.execute(delete(Job))
        counts["jobs"] = result.rowcount or counts["jobs"]
    else:
        await session.execute(delete(SceneEmbedding).where(SceneEmbedding.scene_id.in_(scene_ids)))
        await session.execute(delete(FaceAppearance).where(FaceAppearance.scene_id.in_(scene_ids)))
        await session.execute(delete(Shot).where(Shot.video_id.in_(scope.video_ids)))
        await session.execute(delete(Scene).where(Scene.video_id.in_(scope.video_ids)))
        await session.execute(delete(Video).where(Video.video_id.in_(scope.video_ids)))
        await session.execute(delete(IngestTask).where(IngestTask.source_key.in_(scope.source_keys)))
        # Job rỗng (mọi task của nó đã bị xoá) -> xoá nốt, không để job mồ côi treo 'running'.
        orphan_jobs = (
            select(Job.job_id)
            .outerjoin(IngestTask, IngestTask.job_id == Job.job_id)
            .group_by(Job.job_id)
            .having(func.count(IngestTask.task_id) == 0)
        ).scalar_subquery()
        result = await session.execute(delete(Job).where(Job.job_id.in_(orphan_jobs)))
        counts["jobs"] = result.rowcount or 0

    await session.flush()
    if keys and storage is not None:
        counts["keyframes"] = delete_keyframes(storage, keys)
    return counts


def _format(counts: dict) -> str:
    order = ("videos", "scenes", "shots", "scene_embeddings", "face_appearances",
             "ingest_tasks", "jobs", "keyframes", "keyframe_dirs")
    return ", ".join(f"{k}={counts[k]}" for k in order if k in counts)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m pipeline.clean",
        description="Dọn dữ liệu ingest (video/scene/shot/embedding/task/job + keyframe). "
                    "File video gốc trong MEDIA_ROOT KHÔNG bị xoá.",
    )
    p.add_argument("--video-id", action="append", default=[], metavar="ID",
                   help="chỉ dọn video này (lặp lại được)")
    p.add_argument("--source-key", action="append", default=[], metavar="KEY",
                   help="chỉ dọn video có media-key này, vd 'news/a.mp4' (lặp lại được)")
    p.add_argument("--keep-keyframes", action="store_true",
                   help="giữ lại file keyframe, chỉ xoá dòng trong DB")
    p.add_argument("--dry-run", action="store_true", help="chỉ đếm, không xoá gì")
    p.add_argument("-y", "--yes", action="store_true", help="không hỏi xác nhận")
    return p.parse_args(argv)


def _confirm(scope: Scope, counts: dict) -> bool:
    what = "TOÀN BỘ dữ liệu ingest" if scope.all_videos else f"{len(scope.video_ids)} video"
    print(f"Sẽ xoá {what}: {_format(counts)}")
    if not sys.stdin.isatty():
        print("Không phải terminal tương tác -> huỷ. Thêm --yes để chạy thật.", file=sys.stderr)
        return False
    return input("Xác nhận? [y/N] ").strip().lower() in {"y", "yes"}


async def _main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    configure_logging()
    settings = get_settings()
    storage = build_storage(settings)
    maker = get_sessionmaker()

    async with maker() as session:
        scope = await resolve_scope(session, video_ids=args.video_id, source_keys=args.source_key)
        if not scope.all_videos and not scope.video_ids and not scope.source_keys:
            print("Không có video nào khớp --video-id/--source-key.", file=sys.stderr)
            return 1

        if args.dry_run:
            counts = await clean_ingest(session, storage, scope=scope,
                                        drop_keyframes=not args.keep_keyframes, dry_run=True)
            print(f"[dry-run] {_format(counts)}")
            return 0

        if not args.yes:
            preview = await clean_ingest(session, storage, scope=scope,
                                         drop_keyframes=not args.keep_keyframes, dry_run=True)
            if not _confirm(scope, preview):
                print("Đã huỷ.")
                return 1

        counts = await clean_ingest(session, storage, scope=scope,
                                    drop_keyframes=not args.keep_keyframes)
        await session.commit()

    if not args.keep_keyframes:
        counts["keyframe_dirs"] = sweep_keyframe_dirs(settings.media_root, purge=scope.all_videos)
    print(f"Đã dọn: {_format(counts)}")
    print(f"File video gốc trong {settings.media_root} được giữ nguyên — nạp lại bằng POST /ingest.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(asyncio.run(_main()))

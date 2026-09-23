from __future__ import annotations

from sqlalchemy import func, select

from pipeline.clean import Scope, clean_ingest, resolve_scope, sweep_keyframe_dirs
from shared.models import IngestTask, Job, Scene, SceneEmbedding, Shot, Video
from shared.storage import FilesystemStorage


async def _seed(session, media_root, *, video_id: str, source_key: str) -> str:
    """Dựng 1 video đầy đủ: Video + Scene + Shot(+keyframe file) + SceneEmbedding + Task."""
    job_id = f"job-{video_id}"
    if await session.get(Job, job_id) is None:
        session.add(Job(job_id=job_id, kind="ingest_batch", status="running"))
    session.add(Video(video_id=video_id, source_key=source_key, framerate=25.0))
    session.add(Scene(scene_id=f"{video_id}-s1", video_id=video_id, start_ms=0, end_ms=1000,
                      search_status="indexed"))
    kf_key = f"{video_id}/keyframes/{video_id}-sh1.jpg"
    session.add(Shot(shot_id=f"{video_id}-sh1", scene_id=f"{video_id}-s1", video_id=video_id,
                     start_ms=0, end_ms=1000, keyframe_key=kf_key, phash="ff00"))
    session.add(SceneEmbedding(scene_id=f"{video_id}-s1", embedding=[0.1] * 1024,
                               fts_text="xin chào", doc_version="v1"))
    session.add(IngestTask(task_id=f"t-{video_id}", job_id=job_id, source_key=source_key,
                           status="done", video_id=video_id))
    await session.flush()
    (media_root / video_id / "keyframes").mkdir(parents=True, exist_ok=True)
    (media_root / video_id / "keyframes" / f"{video_id}-sh1.jpg").write_bytes(b"jpg")
    return kf_key


async def _counts(session) -> dict:
    out = {}
    for model in (Video, Scene, Shot, SceneEmbedding, IngestTask, Job):
        out[model.__tablename__] = int(
            (await session.execute(select(func.count()).select_from(model))).scalar_one()
        )
    return out


async def test_clean_all_removes_everything(tmp_path, async_session):
    await _seed(async_session, tmp_path, video_id="v1", source_key="a.mp4")
    await _seed(async_session, tmp_path, video_id="v2", source_key="b.mp4")
    storage = FilesystemStorage(tmp_path)

    scope = await resolve_scope(async_session)
    assert scope.all_videos
    res = await clean_ingest(async_session, storage, scope=scope)

    assert res["videos"] == 2 and res["scenes"] == 2 and res["keyframes"] == 2
    assert await _counts(async_session) == {
        "video": 0, "scene": 0, "shot": 0, "scene_embedding": 0, "ingest_task": 0, "job": 0,
    }
    assert not (tmp_path / "v1" / "keyframes" / "v1-sh1.jpg").exists()


async def test_dry_run_changes_nothing(tmp_path, async_session):
    await _seed(async_session, tmp_path, video_id="v1", source_key="a.mp4")
    storage = FilesystemStorage(tmp_path)
    before = await _counts(async_session)

    res = await clean_ingest(async_session, storage, scope=Scope(
        all_videos=True, video_ids=set(), source_keys=set()), dry_run=True)

    assert res["dry_run"] is True and res["videos"] == 1 and res["keyframes"] == 1
    assert await _counts(async_session) == before
    assert (tmp_path / "v1" / "keyframes" / "v1-sh1.jpg").exists()


async def test_scope_by_source_key_spares_other_videos(tmp_path, async_session):
    await _seed(async_session, tmp_path, video_id="v1", source_key="a.mp4")
    await _seed(async_session, tmp_path, video_id="v2", source_key="b.mp4")
    storage = FilesystemStorage(tmp_path)

    scope = await resolve_scope(async_session, source_keys=["a.mp4"])
    assert scope.video_ids == {"v1"} and scope.source_keys == {"a.mp4"}
    await clean_ingest(async_session, storage, scope=scope)

    assert await _counts(async_session) == {
        "video": 1, "scene": 1, "shot": 1, "scene_embedding": 1, "ingest_task": 1, "job": 1,
    }
    remaining = (await async_session.execute(select(Video.video_id))).scalars().all()
    assert remaining == ["v2"]
    assert not (tmp_path / "v1" / "keyframes" / "v1-sh1.jpg").exists()
    assert (tmp_path / "v2" / "keyframes" / "v2-sh1.jpg").exists()


async def test_keep_keyframes_leaves_files(tmp_path, async_session):
    await _seed(async_session, tmp_path, video_id="v1", source_key="a.mp4")
    storage = FilesystemStorage(tmp_path)

    res = await clean_ingest(async_session, storage, scope=await resolve_scope(async_session),
                             drop_keyframes=False)

    assert res["keyframes"] == 0
    assert (tmp_path / "v1" / "keyframes" / "v1-sh1.jpg").exists()


async def test_resolve_scope_no_match(async_session):
    scope = await resolve_scope(async_session, video_ids=["khong-ton-tai"])
    assert not scope.all_videos and scope.video_ids == {"khong-ton-tai"}


def test_sweep_purge_removes_only_keyframe_dirs(tmp_path):
    (tmp_path / "v1" / "keyframes").mkdir(parents=True)
    (tmp_path / "v1" / "keyframes" / "x.jpg").write_bytes(b"jpg")
    (tmp_path / "v1.mp4").write_bytes(b"video")

    assert sweep_keyframe_dirs(tmp_path, purge=True) == 1
    assert not (tmp_path / "v1" / "keyframes").exists()
    assert (tmp_path / "v1.mp4").exists()  # media gốc không bị đụng


def test_sweep_without_purge_keeps_non_empty_dir(tmp_path):
    (tmp_path / "v1" / "keyframes").mkdir(parents=True)
    (tmp_path / "v1" / "keyframes" / "x.jpg").write_bytes(b"jpg")
    (tmp_path / "v2" / "keyframes").mkdir(parents=True)

    assert sweep_keyframe_dirs(tmp_path, purge=False) == 1  # chỉ thư mục rỗng v2
    assert (tmp_path / "v1" / "keyframes" / "x.jpg").exists()
    assert not (tmp_path / "v2" / "keyframes").exists()

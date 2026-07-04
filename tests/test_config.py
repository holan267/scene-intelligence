from __future__ import annotations

import pytest
from pydantic import ValidationError

from shared.config import Settings


def test_defaults():
    s = Settings(_env_file=None)
    assert s.media_backend == "filesystem"
    assert s.api_env == "dev"


def test_env_override(monkeypatch):
    monkeypatch.setenv("MEDIA_ROOT", "/mnt/nas/media")
    s = Settings(_env_file=None)
    assert s.media_root == "/mnt/nas/media"


def test_lease_and_metrics_settings_defaults():
    s = Settings(_env_file=None)
    assert s.task_lease_seconds == 900
    assert s.task_max_attempts == 3
    assert s.metrics_window_seconds == 300


@pytest.mark.parametrize(
    "field", ["task_lease_seconds", "task_max_attempts", "metrics_window_seconds"]
)
def test_zero_or_negative_rejected(field):
    # Review fix: gt=0 chặn ZeroDivisionError ở collect_metrics()/reclaim_stale_tasks()
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: 0})


def test_search_settings_defaults():
    s = Settings(_env_file=None)
    assert s.search_pool_size == 20
    assert s.rerank_skip_gap == 0.15


def test_search_pool_size_zero_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, search_pool_size=0)


@pytest.mark.parametrize("value", [-0.1, 1.1])
def test_rerank_skip_gap_out_of_range_rejected(value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, rerank_skip_gap=value)

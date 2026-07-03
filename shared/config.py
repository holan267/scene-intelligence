"""Cấu hình nạp từ env/.env (AD: config qua env, không hardcode).

Xem Consistency Conventions trong ARCHITECTURE-SPINE.md.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://scene:scene@localhost:5432/scene_intelligence"
    media_backend: str = "filesystem"
    media_root: str = "./_data/media"
    api_env: str = "dev"


@lru_cache
def get_settings() -> Settings:
    """Trả về Settings (cache 1 lần cho cả process)."""
    return Settings()

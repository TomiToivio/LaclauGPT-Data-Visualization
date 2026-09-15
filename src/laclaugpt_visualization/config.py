"""Configuration for local-first and optional distributed visualization backends.

Secrets are read from environment variables or an untracked .env file. Never
commit credentials, tokens, host-specific paths, or project data to this repo.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings with safe local defaults.

    The default profile needs no services: CSV/JSON files, SQLite, and the local
    filesystem are sufficient. Remote services are opt-in via environment vars.
    """

    model_config = SettingsConfigDict(
        env_prefix="LACLAUGPT_VIS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    profile: Literal["local", "server"] = "local"
    data_backend: Literal["files", "sqlite", "mongodb"] = "files"
    cache_backend: Literal["memory", "redis"] = "memory"
    object_backend: Literal["local", "s3"] = "local"

    data_dir: Path = Path("data")
    output_dir: Path = Path("outputs")
    sqlite_path: Path = Path("data/laclaugpt.sqlite3")

    mongodb_uri: str | None = Field(default=None, repr=False)
    mongodb_database: str = "laclaugpt"
    mongodb_collection: str = "annotations"

    redis_url: str | None = Field(default=None, repr=False)

    s3_endpoint_url: str | None = None
    s3_bucket: str | None = None
    s3_access_key_id: str | None = Field(default=None, repr=False)
    s3_secret_access_key: str | None = Field(default=None, repr=False)
    s3_region: str | None = None

    def validate_remote_requirements(self) -> None:
        if self.data_backend == "mongodb" and not self.mongodb_uri:
            raise ValueError("mongodb backend requires LACLAUGPT_VIS_MONGODB_URI")
        if self.cache_backend == "redis" and not self.redis_url:
            raise ValueError("redis backend requires LACLAUGPT_VIS_REDIS_URL")
        if self.object_backend == "s3" and not (self.s3_endpoint_url and self.s3_bucket):
            raise ValueError("s3 backend requires endpoint URL and bucket")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_remote_requirements()
    return settings

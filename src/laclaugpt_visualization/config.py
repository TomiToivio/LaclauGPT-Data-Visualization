"""Configuration for local-first and optional distributed visualization backends."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .distributed import ProjectNamespace

DATA_SUBDIRS = (
    "logs",
    "database",
    "config",
    "files",
    "csv",
    "jsonl",
    "codebooks",
    "sources",
    "downloads",
    "media",
    "models/ollama",
    "models/whisper",
    "cache",
    "tmp",
    "exports",
    "artifacts",
    "runs",
)


class Settings(BaseSettings):
    """Runtime settings with one private repository-local data root."""

    model_config = SettingsConfigDict(
        env_prefix="LACLAUGPT_VIS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    project_id: str = "default"
    profile: Literal["local", "server"] = "local"
    data_backend: Literal["files", "sqlite", "mongodb"] = "files"
    cache_backend: Literal["memory", "redis"] = "memory"
    object_backend: Literal["local", "s3"] = "local"

    data_dir: Path = Path("data")
    output_dir: Path = Path("data/exports")
    sqlite_path: Path = Path("data/database/visualization.sqlite3")
    analysis_data_dir: Path | None = None

    mongodb_uri: str | None = Field(default=None, repr=False)
    mongodb_database: str = "laclaugpt"
    mongodb_collection: str | None = None

    redis_url: str | None = Field(default=None, repr=False)
    redis_key_prefix: str = "laclaugpt"

    s3_endpoint_url: str | None = None
    s3_bucket: str | None = None
    s3_access_key_id: str | None = Field(default=None, repr=False)
    s3_secret_access_key: str | None = Field(default=None, repr=False)
    s3_region: str | None = None
    s3_prefix_root: str = "projects"

    @property
    def distributed_namespace(self) -> ProjectNamespace:
        return ProjectNamespace(
            project_id=self.project_id,
            redis_prefix=self.redis_key_prefix,
            mongo_database=self.mongodb_database,
            s3_prefix_root=self.s3_prefix_root,
        )

    @property
    def resolved_mongodb_collection(self) -> str:
        return self.mongodb_collection or self.distributed_namespace.mongo_collection("annotations")

    def data_path(self, *parts: str) -> Path:
        return self.data_dir.joinpath(*parts)

    def ensure_local_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        for relative in DATA_SUBDIRS:
            self.data_path(*relative.split("/")).mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)

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

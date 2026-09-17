"""Configuration for local-first and optional distributed visualization backends."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .distributed import ProjectNamespace
from .profiles import DeploymentProfile

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
    "reports",
)


class Settings(BaseSettings):
    """Runtime settings with one private repository-local data root."""

    model_config = SettingsConfigDict(
        env_prefix="LACLAUGPT_VIS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    project_id: str = "default"
    profile: Literal["local", "server", "custom"] = "local"
    machine: Literal["laptop", "linux-server", "custom"] = "laptop"
    execution: Literal["cli", "web-service", "agent"] = "cli"
    storage: Literal["local", "distributed", "custom"] = "local"
    caller: str = "human-cli"

    data_backend: Literal["files", "sqlite", "mongodb"] = "files"
    cache_backend: Literal["memory", "redis"] = "memory"
    object_backend: Literal["local", "s3"] = "local"
    messaging_backend: Literal["none", "redis"] = "none"

    data_dir: Path = Path("data")
    output_dir: Path = Path("data/exports")
    sqlite_path: Path = Path("data/database/visualization.sqlite3")
    analysis_data_dir: Path | None = None

    server_host: str = "127.0.0.1"
    server_port: int = 8501
    cache_max_entries: int = 512

    mongodb_uri: str | None = Field(default=None, repr=False)
    mongodb_database: str = "laclaugpt"
    mongodb_collection: str | None = None

    # The umbrella messaging contract uses LACLAUGPT_REDIS_URL. Keep the historical
    # visualization-specific alias for compatibility, but never place the value in Git.
    redis_url: str | None = Field(
        default=None,
        repr=False,
        validation_alias=AliasChoices("LACLAUGPT_REDIS_URL", "LACLAUGPT_VIS_REDIS_URL"),
    )
    redis_key_prefix: str = "laclaugpt"
    redis_heartbeat_ttl_seconds: int = 60
    redis_event_limit: int = 25

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

    @property
    def deployment_profile(self) -> DeploymentProfile:
        machine = self.machine
        execution = self.execution
        if self.profile == "server" and self.machine == "laptop" and self.execution == "cli":
            machine = "linux-server"
            execution = "web-service"
        return DeploymentProfile(
            machine=machine,
            execution=execution,
            storage=self.storage,
            cache=self.cache_backend,
            analysis_data_root=self.analysis_data_dir or self.data_path("analysis"),
        )

    def data_path(self, *parts: str) -> Path:
        return self.data_dir.joinpath(*parts)

    def ensure_local_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        for relative in DATA_SUBDIRS:
            self.data_path(*relative.split("/")).mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    def safe_summary(self) -> dict[str, object]:
        """Return effective non-secret configuration for logs, health and agents."""
        profile = self.deployment_profile
        return {
            "project_id": self.project_id,
            "profile": self.profile,
            "machine": profile.machine,
            "execution": profile.execution,
            "storage": profile.storage,
            "caller": self.caller,
            "data_backend": self.data_backend,
            "cache_backend": self.cache_backend,
            "object_backend": self.object_backend,
            "messaging_backend": self.messaging_backend,
            "data_dir": str(self.data_dir),
            "analysis_data_dir": str(profile.analysis_data_root),
            "output_dir": str(self.output_dir),
            "server_host": self.server_host,
            "server_port": self.server_port,
            "cache_max_entries": self.cache_max_entries,
            "mongodb_database": self.mongodb_database,
            "mongodb_collection": self.resolved_mongodb_collection,
            "redis_heartbeat_ttl_seconds": self.redis_heartbeat_ttl_seconds,
            "redis_event_limit": self.redis_event_limit,
            "s3_bucket": self.s3_bucket or "",
        }

    def validate_remote_requirements(self) -> None:
        self.deployment_profile.validate()
        if not (1 <= self.server_port <= 65535):
            raise ValueError("server port must be between 1 and 65535")
        if self.cache_max_entries < 1:
            raise ValueError("cache_max_entries must be positive")
        if self.redis_heartbeat_ttl_seconds < 5:
            raise ValueError("redis heartbeat TTL must be at least 5 seconds")
        if self.redis_event_limit < 0:
            raise ValueError("redis event limit must not be negative")
        if self.data_backend == "mongodb" and not self.mongodb_uri:
            raise ValueError("mongodb backend requires LACLAUGPT_VIS_MONGODB_URI")
        if self.cache_backend == "redis" and not self.redis_url:
            raise ValueError("redis cache backend requires LACLAUGPT_REDIS_URL")
        if self.messaging_backend == "redis" and not self.redis_url:
            raise ValueError("redis messaging backend requires LACLAUGPT_REDIS_URL")
        if self.object_backend == "s3" and not (self.s3_endpoint_url and self.s3_bucket):
            raise ValueError("s3 backend requires endpoint URL and bucket")
        if self.storage == "distributed":
            if self.data_backend != "mongodb":
                raise ValueError("distributed storage requires data_backend=mongodb")
            if self.cache_backend != "redis":
                raise ValueError("distributed storage requires cache_backend=redis")
            if self.object_backend != "s3":
                raise ValueError("distributed storage requires object_backend=s3")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_remote_requirements()
    return settings

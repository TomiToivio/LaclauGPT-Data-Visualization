"""Composable deployment profiles; no connections are made here."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DeploymentProfile:
    machine: str = "laptop"
    execution: str = "cli"
    storage: str = "local"
    cache: str = "memory"
    analysis_data_root: Path = Path("data/analysis")

    def validate(self) -> None:
        if self.machine not in {"laptop", "linux-server", "custom"}:
            raise ValueError("unknown machine profile")
        if self.execution not in {"cli", "web-service", "agent"}:
            raise ValueError("unknown execution profile")
        if self.storage not in {"local", "distributed", "custom"}:
            raise ValueError("unknown storage profile")
        if self.cache not in {"memory", "redis"}:
            raise ValueError("unknown cache profile")
        if self.storage == "local" and self.cache == "redis":
            raise ValueError("redis cache requires distributed/custom storage")

    @property
    def runtime_root(self) -> Path:
        return Path("data")


def laptop(analysis_data_root: str | Path = "data/analysis") -> DeploymentProfile:
    return DeploymentProfile(analysis_data_root=Path(analysis_data_root))


def linux_service(
    analysis_data_root: str | Path = "data/analysis", storage: str = "local"
) -> DeploymentProfile:
    return DeploymentProfile(
        machine="linux-server",
        execution="web-service",
        storage=storage,
        cache="redis" if storage == "distributed" else "memory",
        analysis_data_root=Path(analysis_data_root),
    )

"""Project-level visualization configuration with safe public/private composition."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

SECRET_TOKENS = (
    "password",
    "passwd",
    "secret",
    "token",
    "access_key",
    "private_key",
    "mongodb_uri",
    "redis_url",
    "endpoint_url",
)


class FormationPresentation(BaseModel):
    """Presentation-only metadata for an upstream formation identifier."""

    model_config = ConfigDict(extra="forbid")

    display_label: str
    description: str | None = None
    provisional: bool = True
    multi_label: bool = True


class DashboardLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table_page_size: int = Field(default=100, ge=10, le=5000)
    graph_max_nodes: int = Field(default=500, ge=1, le=10000)
    graph_max_edges: int = Field(default=1000, ge=1, le=50000)
    refresh_seconds: int = Field(default=30, ge=5, le=3600)


class AI26DashboardProfile(BaseModel):
    """Public-safe dashboard semantics. Scientific classification remains upstream."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1"
    project_id: str
    title: str
    mode: str = "ai26-research-dashboard"
    storage: str = "distributed"
    data_backend: str = "mongodb"
    cache_backend: str = "redis"
    messaging_backend: str = "redis"
    canonical_analysis_codebook: str
    arenas: dict[str, str] = Field(default_factory=dict)
    formations: dict[str, FormationPresentation] = Field(default_factory=dict)
    filters: list[str] = Field(default_factory=list)
    tabs: list[str] = Field(default_factory=list)
    optional_capabilities: dict[str, bool] = Field(default_factory=dict)
    semantic_safeguards: list[str] = Field(default_factory=list)
    limits: DashboardLimits = Field(default_factory=DashboardLimits)
    private_overlay_required: bool = False

    @model_validator(mode="after")
    def enforce_ai26_identity(self) -> "AI26DashboardProfile":
        if self.project_id != "ai26":
            raise ValueError("AI26 dashboard profile project_id must remain 'ai26'")
        return self

    def safe_summary(self) -> dict[str, Any]:
        return sanitize_mapping(self.model_dump(mode="json"))

    def revision(self) -> str:
        payload = json.dumps(self.safe_summary(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_yaml_mapping(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"configuration root must be a mapping: {path}")
    return data


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Merge mappings recursively; lists/scalars are explicitly replaced by the overlay."""
    result = deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def compose_ai26_profile(
    public_path: Path,
    *,
    private_overlay_path: Path | None = None,
    machine_overlay_path: Path | None = None,
    require_private: bool | None = None,
) -> AI26DashboardProfile:
    """Compose public -> private -> machine layers while preserving AI26 identity."""
    merged = load_yaml_mapping(public_path)
    public_project_id = merged.get("project_id")
    required = bool(merged.get("private_overlay_required")) if require_private is None else require_private

    if private_overlay_path is not None:
        if not private_overlay_path.exists():
            if required:
                raise FileNotFoundError(f"required private overlay missing: {private_overlay_path}")
        else:
            merged = deep_merge(merged, load_yaml_mapping(private_overlay_path))
    elif required:
        raise FileNotFoundError("AI26 production profile requires a private overlay")

    if machine_overlay_path is not None:
        if not machine_overlay_path.exists():
            raise FileNotFoundError(f"machine overlay missing: {machine_overlay_path}")
        merged = deep_merge(merged, load_yaml_mapping(machine_overlay_path))

    if merged.get("project_id") != public_project_id or public_project_id != "ai26":
        raise ValueError("configuration overlays may not change the canonical AI26 project_id")
    return AI26DashboardProfile.model_validate(merged)


def sanitize_mapping(value: Any) -> Any:
    """Remove secret-bearing values from diagnostic/provenance serialization."""
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(token in lowered for token in SECRET_TOKENS):
                safe[key] = "<redacted>"
            else:
                safe[key] = sanitize_mapping(item)
        return safe
    if isinstance(value, list):
        return [sanitize_mapping(item) for item in value]
    return value

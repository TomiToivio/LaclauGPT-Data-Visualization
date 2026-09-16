"""Permission, audit, and service-port primitives for full-system UI actions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol

from .plugins import Permission


@dataclass(frozen=True, slots=True)
class Principal:
    id: str
    permissions: frozenset[Permission] = frozenset({Permission.VIEW})
    actor_type: str = "human"

    def require(self, permission: Permission) -> None:
        if Permission.ADMIN not in self.permissions and permission not in self.permissions:
            raise PermissionError(f"{self.id!r} lacks permission {permission.value!r}")


@dataclass(frozen=True, slots=True)
class AuditEvent:
    actor_id: str
    actor_type: str
    project: str
    action: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    target_id: str | None = None
    before: Mapping[str, Any] | None = None
    after: Mapping[str, Any] | None = None
    reason: str | None = None
    job_id: str | None = None


class AuditSink(Protocol):
    def append(self, event: AuditEvent) -> None: ...


@dataclass(slots=True)
class InMemoryAuditSink:
    events: list[AuditEvent] = field(default_factory=list)

    def append(self, event: AuditEvent) -> None:
        self.events.append(event)


class CollectionService(Protocol):
    def status(self, project: str) -> Mapping[str, Any]: ...
    def run(self, project: str, *, source: str | None = None) -> str: ...
    def update_config(self, project: str, changes: Mapping[str, Any]) -> Mapping[str, Any]: ...


class AnalysisService(Protocol):
    def status(self, project: str) -> Mapping[str, Any]: ...
    def run(self, project: str, *, record_ids: tuple[str, ...] = ()) -> str: ...
    def update_config(self, project: str, changes: Mapping[str, Any]) -> Mapping[str, Any]: ...


@dataclass(slots=True)
class ActionBroker:
    """Small orchestration boundary: UI requests actions, services own domain logic."""

    audit: AuditSink
    collection: CollectionService | None = None
    analysis: AnalysisService | None = None

    def run_collection(self, principal: Principal, project: str, *, source: str | None = None) -> str:
        principal.require(Permission.RUN_COLLECTION)
        if self.collection is None:
            raise RuntimeError("collection service is not configured")
        job_id = self.collection.run(project, source=source)
        self.audit.append(AuditEvent(principal.id, principal.actor_type, project, "run_collection", job_id=job_id, after={"source": source}))
        return job_id

    def run_analysis(self, principal: Principal, project: str, *, record_ids: tuple[str, ...] = ()) -> str:
        principal.require(Permission.RUN_ANALYSIS)
        if self.analysis is None:
            raise RuntimeError("analysis service is not configured")
        job_id = self.analysis.run(project, record_ids=record_ids)
        self.audit.append(AuditEvent(principal.id, principal.actor_type, project, "run_analysis", job_id=job_id, after={"record_ids": record_ids}))
        return job_id

    def update_collection_config(self, principal: Principal, project: str, changes: Mapping[str, Any], *, reason: str | None = None) -> Mapping[str, Any]:
        principal.require(Permission.EDIT_COLLECTION_CONFIG)
        if self.collection is None:
            raise RuntimeError("collection service is not configured")
        result = self.collection.update_config(project, changes)
        self.audit.append(AuditEvent(principal.id, principal.actor_type, project, "update_collection_config", after=dict(changes), reason=reason))
        return result

    def update_analysis_config(self, principal: Principal, project: str, changes: Mapping[str, Any], *, reason: str | None = None) -> Mapping[str, Any]:
        principal.require(Permission.EDIT_ANALYSIS_CONFIG)
        if self.analysis is None:
            raise RuntimeError("analysis service is not configured")
        result = self.analysis.update_config(project, changes)
        self.audit.append(AuditEvent(principal.id, principal.actor_type, project, "update_analysis_config", after=dict(changes), reason=reason))
        return result

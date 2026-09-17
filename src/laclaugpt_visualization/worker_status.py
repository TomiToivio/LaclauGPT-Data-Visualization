"""Optional, read-only Redis operational status for the visualization workbench.

Redis is deliberately treated as transient coordination state. This module exposes only
small public-contract identifiers from worker heartbeats and workflow events; it never
returns queue payloads or arbitrary heartbeat metadata and never owns durable research state.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

WORKER_STATES = frozenset({"starting", "idle", "busy", "draining", "stopped", "error"})
WORKER_ROLES = frozenset({"collection", "analysis", "visualization", "orchestration"})
SAFE_EVENT_FIELDS = (
    "message_id",
    "task_id",
    "project_id",
    "run_id",
    "task_type",
    "producer",
    "created_at",
)


def _decode(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _mapping(value: Any) -> dict[str, Any] | None:
    """Decode JSON or Redis hashes without exposing non-contract payload fields."""
    if isinstance(value, Mapping):
        return {_decode(key): _decode(item) for key, item in value.items()}
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        return dict(parsed) if isinstance(parsed, Mapping) else None
    return None


def _timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    text = _decode(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class WorkerHeartbeat:
    project_id: str
    run_id: str
    worker_id: str
    worker_role: str
    status: str
    current_task_id: str | None
    updated_at: datetime
    stale: bool
    age_seconds: float


@dataclass(frozen=True, slots=True)
class WorkflowEvent:
    stream: str
    message_id: str | None = None
    task_id: str | None = None
    project_id: str | None = None
    run_id: str | None = None
    task_type: str | None = None
    producer: str | None = None
    created_at: str | None = None


@dataclass(frozen=True, slots=True)
class OperationalSnapshot:
    available: bool
    workers: tuple[WorkerHeartbeat, ...] = ()
    events: tuple[WorkflowEvent, ...] = ()
    note: str = ""


@dataclass(slots=True)
class RedisOperationalStatus:
    """Read small transient worker/event projections from an injected Redis client."""

    client: Any
    prefix: str = "laclaugpt"
    heartbeat_ttl_seconds: int = 60
    event_limit: int = 25

    def __post_init__(self) -> None:
        if self.heartbeat_ttl_seconds < 5:
            raise ValueError("heartbeat_ttl_seconds must be at least 5")
        if self.event_limit < 0:
            raise ValueError("event_limit must not be negative")

    def snapshot(
        self,
        project_id: str,
        *,
        run_ids: Iterable[str] = (),
        now: datetime | None = None,
    ) -> OperationalSnapshot:
        """Return a safe best-effort snapshot; Redis failure is data, not an exception."""
        if not project_id:
            raise ValueError("project_id is required")
        current = (now or datetime.now(UTC)).astimezone(UTC)
        allowed_runs = {str(value) for value in run_ids if str(value)}
        try:
            workers = self._workers(project_id, allowed_runs, current)
            events = self._events(project_id, allowed_runs)
        except Exception:  # Redis/network/client errors must not break durable dashboard views.
            return OperationalSnapshot(
                available=False,
                note="Live Redis status unavailable; durable research data is unaffected.",
            )
        return OperationalSnapshot(
            available=True,
            workers=tuple(workers),
            events=tuple(events),
            note="Live operational status is transient and not audit history.",
        )

    def _workers(
        self,
        project_id: str,
        run_ids: set[str],
        now: datetime,
    ) -> list[WorkerHeartbeat]:
        results: list[WorkerHeartbeat] = []
        pattern = f"{self.prefix}:{project_id}:worker:*"
        for raw_key in self.client.scan_iter(match=pattern):
            key = _decode(raw_key)
            payload = _mapping(self.client.get(raw_key))
            if payload is None and hasattr(self.client, "hgetall"):
                payload = _mapping(self.client.hgetall(raw_key))
            if not payload:
                continue
            heartbeat = self._heartbeat(payload, project_id, run_ids, now)
            if heartbeat is not None:
                results.append(heartbeat)
        return sorted(results, key=lambda item: (item.stale, item.worker_role, item.worker_id))

    def _heartbeat(
        self,
        payload: Mapping[str, Any],
        project_id: str,
        run_ids: set[str],
        now: datetime,
    ) -> WorkerHeartbeat | None:
        if _decode(payload.get("schema_version", "")) != "1.0":
            return None
        if _decode(payload.get("project_id", "")) != project_id:
            return None
        run_id = _decode(payload.get("run_id", ""))
        if not run_id or (run_ids and run_id not in run_ids):
            return None
        worker_id = _decode(payload.get("worker_id", ""))
        role = _decode(payload.get("worker_role", ""))
        status = _decode(payload.get("status", ""))
        updated_at = _timestamp(payload.get("updated_at"))
        if not worker_id or role not in WORKER_ROLES or status not in WORKER_STATES or updated_at is None:
            return None
        age = max(0.0, (now - updated_at).total_seconds())
        task = payload.get("current_task_id")
        current_task_id = None if task in (None, "", b"") else _decode(task)
        return WorkerHeartbeat(
            project_id=project_id,
            run_id=run_id,
            worker_id=worker_id,
            worker_role=role,
            status=status,
            current_task_id=current_task_id,
            updated_at=updated_at,
            stale=age > self.heartbeat_ttl_seconds,
            age_seconds=age,
        )

    def _events(self, project_id: str, run_ids: set[str]) -> list[WorkflowEvent]:
        if self.event_limit == 0 or not hasattr(self.client, "scan_iter"):
            return []
        events: list[WorkflowEvent] = []
        pattern = f"{self.prefix}:{project_id}:stream:*"
        for raw_stream in self.client.scan_iter(match=pattern):
            if not hasattr(self.client, "xrevrange"):
                break
            stream = _decode(raw_stream)
            rows = self.client.xrevrange(raw_stream, count=self.event_limit)
            for _redis_id, raw_values in rows:
                values = _mapping(raw_values) or {}
                safe = {field: values.get(field) for field in SAFE_EVENT_FIELDS}
                if safe.get("project_id") not in (None, project_id):
                    continue
                run_id = None if safe.get("run_id") is None else _decode(safe["run_id"])
                if run_ids and run_id not in run_ids:
                    continue
                events.append(
                    WorkflowEvent(
                        stream=stream.rsplit(":", 1)[-1],
                        message_id=self._optional(safe.get("message_id")),
                        task_id=self._optional(safe.get("task_id")),
                        project_id=self._optional(safe.get("project_id")),
                        run_id=run_id,
                        task_type=self._optional(safe.get("task_type")),
                        producer=self._optional(safe.get("producer")),
                        created_at=self._optional(safe.get("created_at")),
                    )
                )
                if len(events) >= self.event_limit:
                    return events
        return events

    @staticmethod
    def _optional(value: Any) -> str | None:
        return None if value in (None, "", b"") else _decode(value)

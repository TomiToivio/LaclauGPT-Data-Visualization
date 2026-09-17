"""Safe service adapters for dashboard UI plugins.

These adapters deliberately accept already-created client/collection objects. Importing this
module never opens MongoDB/Redis connections, so local/offline dashboard use stays safe.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Mapping
from uuid import uuid4


_SECRET_TOKENS = ("password", "secret", "token", "credential", "private_key", "api_key")


def _contains_secret_key(value: Mapping[str, Any]) -> bool:
    for key, item in value.items():
        lowered = str(key).lower()
        if any(token in lowered for token in _SECRET_TOKENS):
            return True
        if isinstance(item, Mapping) and _contains_secret_key(item):
            return True
    return False


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class MutationReceipt:
    action: str
    target_id: str
    actor: str
    timestamp: str
    changed_fields: tuple[str, ...] = ()
    task_id: str | None = None


@dataclass(slots=True)
class MongoRecordService:
    """Whitelist-based edits and recoverable exclusion for canonical records."""

    collection: Any
    editable_fields: frozenset[str]

    def update_fields(
        self,
        record_id: str,
        changes: Mapping[str, Any],
        *,
        actor: str,
        reason: str,
    ) -> MutationReceipt:
        if not reason.strip():
            raise ValueError("a reason is required for record edits")
        unknown = set(changes) - set(self.editable_fields)
        if unknown:
            raise ValueError("fields are not editable: " + ", ".join(sorted(unknown)))
        if not changes:
            raise ValueError("no changes supplied")
        audit = {
            "actor": actor,
            "reason": reason,
            "timestamp": _utc_now(),
            "fields": sorted(changes),
        }
        result = self.collection.update_one(
            {"_id": record_id},
            {"$set": dict(changes), "$push": {"ui_audit": audit}},
        )
        if getattr(result, "matched_count", 1) == 0:
            raise KeyError(record_id)
        return MutationReceipt(
            action="update_fields",
            target_id=record_id,
            actor=actor,
            timestamp=audit["timestamp"],
            changed_fields=tuple(sorted(changes)),
        )

    def quarantine(self, record_id: str, *, actor: str, reason: str) -> MutationReceipt:
        if not reason.strip():
            raise ValueError("a reason is required for quarantine")
        timestamp = _utc_now()
        payload = {
            "review.excluded": True,
            "review.exclusion_reason": reason,
            "review.excluded_by": actor,
            "review.excluded_at": timestamp,
        }
        result = self.collection.update_one(
            {"_id": record_id},
            {
                "$set": payload,
                "$push": {
                    "ui_audit": {
                        "actor": actor,
                        "reason": reason,
                        "timestamp": timestamp,
                        "action": "quarantine",
                    }
                },
            },
        )
        if getattr(result, "matched_count", 1) == 0:
            raise KeyError(record_id)
        return MutationReceipt("quarantine", record_id, actor, timestamp, tuple(payload))


@dataclass(slots=True)
class RedisConfigService:
    """Versioned JSON configuration stored behind a namespaced Redis key."""

    client: Any
    prefix: str = "laclaugpt:config"

    def _key(self, project: str, module: str) -> str:
        return f"{self.prefix}:{project}:{module}"

    def get(self, project: str, module: str) -> dict[str, Any]:
        raw = self.client.get(self._key(project, module))
        if raw is None:
            return {"version": 0, "values": {}}
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("distributed configuration must be a JSON object")
        return data

    def update(
        self,
        project: str,
        module: str,
        changes: Mapping[str, Any],
        *,
        actor: str,
        reason: str,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        if _contains_secret_key(changes):
            raise ValueError("secret-like keys may not be published through dashboard configuration")
        current = self.get(project, module)
        version = int(current.get("version", 0))
        if expected_version is not None and version != expected_version:
            raise RuntimeError(f"configuration version changed: expected {expected_version}, found {version}")
        values = dict(current.get("values") or {})
        values.update(changes)
        updated = {
            "version": version + 1,
            "values": values,
            "updated_at": _utc_now(),
            "updated_by": actor,
            "reason": reason,
        }
        self.client.set(self._key(project, module), json.dumps(updated, sort_keys=True))
        return updated


@dataclass(slots=True)
class RedisTaskQueueService:
    """Enqueue bounded work requests; workers remain responsible for execution."""

    client: Any
    queue_key: str = "laclaugpt:tasks"

    def enqueue(
        self,
        task_type: str,
        payload: Mapping[str, Any],
        *,
        actor: str,
        project: str,
        idempotency_key: str | None = None,
    ) -> str:
        if not task_type.strip():
            raise ValueError("task_type is required")
        task_id = idempotency_key or str(uuid4())
        envelope = {
            "task_id": task_id,
            "task_type": task_type,
            "payload": dict(payload),
            "actor": actor,
            "project": project,
            "created_at": _utc_now(),
        }
        self.client.rpush(self.queue_key, json.dumps(envelope, sort_keys=True))
        return task_id


@dataclass(slots=True)
class RedisMessageQueueService:
    """Send chat/agent messages without giving the dashboard direct process or shell access."""

    client: Any
    queue_key: str = "laclaugpt:messages"

    def send(
        self,
        message: str,
        *,
        actor: str,
        project: str,
        context: Mapping[str, Any] | None = None,
    ) -> str:
        if not message.strip():
            raise ValueError("message must not be empty")
        message_id = str(uuid4())
        envelope = {
            "message_id": message_id,
            "message": message,
            "actor": actor,
            "project": project,
            "context": dict(context or {}),
            "created_at": _utc_now(),
        }
        self.client.rpush(self.queue_key, json.dumps(envelope, sort_keys=True))
        return message_id


@dataclass(slots=True)
class SQLiteNotesStore:
    """Local-first research/digital-ethnography note store with evidence links."""

    path: Path

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS research_notes (
                note_id TEXT PRIMARY KEY,
                project TEXT NOT NULL,
                actor TEXT NOT NULL,
                kind TEXT NOT NULL,
                body TEXT NOT NULL,
                tags_json TEXT NOT NULL,
                links_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        return connection

    def add(
        self,
        project: str,
        body: str,
        *,
        actor: str,
        kind: str = "research_note",
        tags: Iterable[str] = (),
        links: Mapping[str, Any] | None = None,
    ) -> str:
        if not body.strip():
            raise ValueError("note body must not be empty")
        note_id = str(uuid4())
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO research_notes VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    note_id,
                    project,
                    actor,
                    kind,
                    body,
                    json.dumps(sorted(set(tags))),
                    json.dumps(dict(links or {}), sort_keys=True),
                    _utc_now(),
                ),
            )
        return note_id

    def list(self, project: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT note_id, actor, kind, body, tags_json, links_json, created_at "
                "FROM research_notes WHERE project = ? ORDER BY created_at DESC",
                (project,),
            ).fetchall()
        return [
            {
                "note_id": row[0],
                "actor": row[1],
                "kind": row[2],
                "body": row[3],
                "tags": json.loads(row[4]),
                "links": json.loads(row[5]),
                "created_at": row[6],
            }
            for row in rows
        ]

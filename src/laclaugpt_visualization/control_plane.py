"""Optional Redis control plane for configuration, messaging and task coordination.

Redis is operational transport, never canonical research memory. Mutating operations are
permission-gated and emit compact reference-based events. Published configuration is also
snapshotted to private local storage for reproducibility.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Mapping

ActorKind = Literal["human", "agent", "cli", "system"]
Permission = Literal["config.publish", "message.send", "task.trigger", "task.retry", "task.cancel"]
SECRET_MARKERS = ("password", "secret", "token", "credential", "api_key", "access_key", "private_key")
ALLOWED_MESSAGE_TYPES = frozenset({
    "rag.query", "rag.response", "agent.request", "agent.plan", "agent.action_started",
    "agent.action_completed", "analysis.run.requested", "collection.run.requested",
    "config.updated", "human.annotation.created", "worker.status",
})
ALLOWED_TASK_TYPES = frozenset({"collection.run", "analysis.run", "reprocess", "media.download"})


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(10)}"


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def redact_config(value: Any) -> Any:
    """Recursively remove secret-bearing fields before display, Redis or snapshots."""
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            text = str(key).lower()
            result[str(key)] = "<redacted>" if any(marker in text for marker in SECRET_MARKERS) else redact_config(item)
        return result
    if isinstance(value, list):
        return [redact_config(item) for item in value]
    return value


def config_hash(config: Mapping[str, Any]) -> str:
    return hashlib.sha256(_json(redact_config(config)).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class Actor:
    actor_id: str
    kind: ActorKind = "human"
    permissions: frozenset[str] = frozenset()

    def require(self, permission: Permission) -> None:
        if permission not in self.permissions:
            raise PermissionError(f"actor lacks permission: {permission}")


@dataclass(frozen=True, slots=True)
class ConfigRevision:
    project_id: str
    revision: str
    config: dict[str, Any]
    config_hash: str
    actor_id: str
    actor_kind: ActorKind
    created_at: str
    previous_revision: str | None = None


@dataclass(frozen=True, slots=True)
class MessageReceipt:
    request_id: str
    message_id: str
    stream: str


@dataclass(frozen=True, slots=True)
class TaskReceipt:
    task_id: str
    message_id: str
    stream: str
    config_revision: str | None


@dataclass(slots=True)
class RedisControlPlane:
    client: Any
    project_id: str
    prefix: str = "laclaugpt"
    snapshot_dir: Path = Path("data/config/snapshots")
    actor: Actor = field(default_factory=lambda: Actor("anonymous", "human", frozenset()))

    def _key(self, *parts: str) -> str:
        return ":".join((self.prefix, self.project_id, *parts))

    @property
    def config_current_key(self) -> str:
        return self._key("config", "current")

    @property
    def config_history_stream(self) -> str:
        return self._key("stream", "config")

    @property
    def request_stream(self) -> str:
        return self._key("stream", "requests")

    @property
    def response_stream(self) -> str:
        return self._key("stream", "responses")

    @property
    def task_stream(self) -> str:
        return self._key("stream", "tasks")

    def current_config(self) -> ConfigRevision | None:
        raw = self.client.get(self.config_current_key)
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode()
        return self._decode_revision(json.loads(raw))

    def publish_config(self, config: Mapping[str, Any], *, expected_revision: str | None = None) -> ConfigRevision:
        self.actor.require("config.publish")
        clean = redact_config(dict(config))
        current = self.current_config()
        current_revision = current.revision if current else None
        if expected_revision is not None and expected_revision != current_revision:
            raise RuntimeError("configuration revision conflict")
        revision = new_id("cfg")
        record = ConfigRevision(
            project_id=self.project_id,
            revision=revision,
            config=clean,
            config_hash=config_hash(clean),
            actor_id=self.actor.actor_id,
            actor_kind=self.actor.kind,
            created_at=utc_now(),
            previous_revision=current_revision,
        )
        payload = self._revision_dict(record)
        encoded = _json(payload)
        self.client.set(self.config_current_key, encoded)
        self.client.xadd(self.config_history_stream, {"type": "config.updated", "payload": encoded})
        self._snapshot(record)
        return record

    def send_request(self, message_type: str, payload: Mapping[str, Any], *, request_id: str | None = None) -> MessageReceipt:
        self.actor.require("message.send")
        if message_type not in ALLOWED_MESSAGE_TYPES:
            raise ValueError(f"unsupported message type: {message_type}")
        rid = request_id or new_id("req")
        body = {
            "schema_version": "1.0", "type": message_type, "project_id": self.project_id,
            "request_id": rid, "actor_id": self.actor.actor_id, "actor_kind": self.actor.kind,
            "created_at": utc_now(), "payload": redact_config(dict(payload)),
        }
        mid = self.client.xadd(self.request_stream, {"payload": _json(body)})
        return MessageReceipt(rid, self._decode(mid), self.request_stream)

    def correlated_responses(self, request_id: str, *, count: int = 100) -> list[dict[str, Any]]:
        rows = self.client.xrevrange(self.response_stream, count=count)
        found = []
        for message_id, fields in rows:
            raw = fields.get(b"payload") if isinstance(fields, Mapping) else None
            raw = raw if raw is not None else fields.get("payload")
            if isinstance(raw, bytes):
                raw = raw.decode()
            if not raw:
                continue
            event = json.loads(raw)
            if event.get("request_id") == request_id:
                event["message_id"] = self._decode(message_id)
                found.append(event)
        return found

    def trigger_task(self, task_type: str, refs: Mapping[str, Any], *, config_revision: str | None = None) -> TaskReceipt:
        self.actor.require("task.trigger")
        if task_type not in ALLOWED_TASK_TYPES:
            raise ValueError(f"unsupported task type: {task_type}")
        task_id = new_id("task")
        revision = config_revision or (self.current_config().revision if self.current_config() else None)
        payload = {
            "schema_version": "1.0", "type": "task.requested", "task_id": task_id,
            "task_type": task_type, "project_id": self.project_id, "config_revision": revision,
            "requested_by": self.actor.actor_id, "actor_kind": self.actor.kind,
            "created_at": utc_now(), "refs": redact_config(dict(refs)),
        }
        mid = self.client.xadd(self.task_stream, {"payload": _json(payload)})
        return TaskReceipt(task_id, self._decode(mid), self.task_stream, revision)

    def task_command(self, task_id: str, action: Literal["retry", "cancel"]) -> str:
        permission: Permission = "task.retry" if action == "retry" else "task.cancel"
        self.actor.require(permission)
        payload = {
            "schema_version": "1.0", "type": f"task.{action}.requested", "task_id": task_id,
            "project_id": self.project_id, "requested_by": self.actor.actor_id,
            "actor_kind": self.actor.kind, "created_at": utc_now(),
        }
        return self._decode(self.client.xadd(self.task_stream, {"payload": _json(payload)}))

    def task_events(self, *, count: int = 100) -> list[dict[str, Any]]:
        result = []
        for message_id, fields in self.client.xrevrange(self.task_stream, count=count):
            raw = fields.get(b"payload") if isinstance(fields, Mapping) else None
            raw = raw if raw is not None else fields.get("payload")
            if isinstance(raw, bytes):
                raw = raw.decode()
            if raw:
                item = json.loads(raw)
                item["message_id"] = self._decode(message_id)
                result.append(item)
        return result

    def _snapshot(self, revision: ConfigRevision) -> None:
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        path = self.snapshot_dir / f"{self.project_id}-{revision.revision}.json"
        path.write_text(json.dumps(self._revision_dict(revision), indent=2, sort_keys=True), encoding="utf-8")

    @staticmethod
    def _decode(value: Any) -> str:
        return value.decode() if isinstance(value, bytes) else str(value)

    @staticmethod
    def _revision_dict(revision: ConfigRevision) -> dict[str, Any]:
        return {
            "project_id": revision.project_id, "revision": revision.revision,
            "config": revision.config, "config_hash": revision.config_hash,
            "actor_id": revision.actor_id, "actor_kind": revision.actor_kind,
            "created_at": revision.created_at, "previous_revision": revision.previous_revision,
        }

    @staticmethod
    def _decode_revision(value: Mapping[str, Any]) -> ConfigRevision:
        return ConfigRevision(**dict(value))

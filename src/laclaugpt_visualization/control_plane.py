"""Optional Redis control plane using the shared LaclauGPT coordination contract.

The wire shapes and project namespaces intentionally match Data Analysis coordination.py
and task_queue.py. Redis is operational transport only; durable configuration snapshots and
research results remain outside Redis.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, Mapping

from .distributed import ProjectNamespace

ActorKind = Literal["human", "agent", "cli", "system"]
Permission = Literal["config.publish", "message.send", "task.trigger", "task.retry", "task.cancel"]
SECRET_MARKERS = ("password", "secret", "token", "credential", "api_key", "access_key", "private_key")
MODULES = frozenset({"collection", "analysis", "visualization", "storage", "simulation"})


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _revision(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _decode(value: Any) -> str:
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else str(value)


def _decode_fields(fields: Mapping[Any, Any]) -> dict[str, Any]:
    return {_decode(key): _decode(value) for key, value in fields.items()}


def secret_paths(value: Any, prefix: str = "") -> tuple[str, ...]:
    """Return secret-looking config paths so shared config can reject them before publication."""
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            name = str(key)
            path = f"{prefix}.{name}" if prefix else name
            if any(marker in name.lower() for marker in SECRET_MARKERS):
                found.append(path)
            else:
                found.extend(secret_paths(item, path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(secret_paths(item, f"{prefix}[{index}]"))
    return tuple(found)


def redact_config(value: Any) -> Any:
    """Redact secret-looking fields for safe previews/import/export diagnostics."""
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            name = str(key)
            if any(marker in name.lower() for marker in SECRET_MARKERS):
                result[name] = "<redacted>"
            else:
                result[name] = redact_config(item)
        return result
    if isinstance(value, list):
        return [redact_config(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class Actor:
    actor_id: str
    kind: ActorKind = "human"
    permissions: frozenset[str] = frozenset()

    def require(self, permission: Permission) -> None:
        if permission not in self.permissions:
            raise PermissionError(f"actor lacks permission: {permission}")

    @property
    def publisher(self) -> str:
        return f"{self.kind}:{self.actor_id}"


@dataclass(frozen=True, slots=True)
class ConfigRevision:
    """Wire-compatible with Data Analysis coordination.ConfigRevision."""

    project_id: str
    module: str
    revision: str
    payload: dict[str, Any]
    created_at: float
    publisher: str

    @classmethod
    def build(
        cls,
        *,
        project_id: str,
        module: str,
        payload: Mapping[str, Any],
        publisher: str,
    ) -> "ConfigRevision":
        clean = dict(payload)
        return cls(project_id, module, _revision(clean), clean, time.time(), publisher)

    def validate(self) -> None:
        if self.module not in MODULES:
            raise ValueError(f"unknown module: {self.module}")
        if not self.project_id or not self.publisher:
            raise ValueError("configuration revision is missing routing/provenance fields")
        if self.revision != _revision(self.payload):
            raise ValueError("configuration revision hash does not match payload")


@dataclass(frozen=True, slots=True)
class MessageEnvelope:
    """Wire-compatible with Data Analysis coordination.MessageEnvelope."""

    project_id: str
    run_id: str
    request_id: str
    correlation_id: str
    sender: str
    recipient: str
    message_type: str
    created_at: float
    config_revision: str
    source_record_id: str = ""
    task_id: str = ""
    payload_ref: str = ""
    body: dict[str, Any] | None = None

    @classmethod
    def build(
        cls,
        *,
        project_id: str,
        run_id: str,
        sender: str,
        recipient: str,
        message_type: str,
        config_revision: str,
        correlation_id: str | None = None,
        source_record_id: str = "",
        task_id: str = "",
        payload_ref: str = "",
        body: Mapping[str, Any] | None = None,
    ) -> "MessageEnvelope":
        request_id = str(uuid.uuid4())
        return cls(
            project_id=project_id,
            run_id=run_id,
            request_id=request_id,
            correlation_id=correlation_id or request_id,
            sender=sender,
            recipient=recipient,
            message_type=message_type,
            created_at=time.time(),
            config_revision=config_revision,
            source_record_id=source_record_id,
            task_id=task_id,
            payload_ref=payload_ref,
            body=dict(body) if body is not None else None,
        )

    def validate(self) -> None:
        required = (
            self.project_id,
            self.run_id,
            self.request_id,
            self.correlation_id,
            self.sender,
            self.recipient,
            self.message_type,
            self.config_revision,
        )
        if any(not str(value).strip() for value in required):
            raise ValueError("message envelope is missing required routing/provenance fields")
        if self.body is not None and len(_canonical_json(self.body).encode("utf-8")) > 64 * 1024:
            raise ValueError("message body is too large; store payload durably and send a reference")

    def to_fields(self) -> dict[str, str]:
        self.validate()
        values = asdict(self)
        body = values.pop("body")
        fields = {key: str(value) for key, value in values.items()}
        fields["body_json"] = _canonical_json(body or {})
        return fields

    @classmethod
    def from_fields(cls, fields: Mapping[Any, Any]) -> "MessageEnvelope":
        values = _decode_fields(fields)
        message = cls(
            project_id=values["project_id"],
            run_id=values["run_id"],
            request_id=values["request_id"],
            correlation_id=values["correlation_id"],
            sender=values["sender"],
            recipient=values["recipient"],
            message_type=values["message_type"],
            created_at=float(values["created_at"]),
            config_revision=values["config_revision"],
            source_record_id=values.get("source_record_id", ""),
            task_id=values.get("task_id", ""),
            payload_ref=values.get("payload_ref", ""),
            body=json.loads(values.get("body_json", "{}")) or None,
        )
        message.validate()
        return message


@dataclass(frozen=True, slots=True)
class TaskEnvelope:
    """Wire-compatible with Data Analysis task_queue.TaskEnvelope."""

    task_id: str
    idempotency_key: str
    project_id: str
    run_id: str
    task_type: str
    record_ref: str
    schema_version: str
    config_revision: str
    codebook_revision: str
    attempt: int = 1

    def validate(self) -> None:
        required = asdict(self)
        missing = [name for name, value in required.items() if name != "attempt" and not str(value).strip()]
        if missing:
            raise ValueError("task envelope missing: " + ", ".join(sorted(missing)))
        if self.attempt < 1:
            raise ValueError("attempt must be >= 1")

    def to_fields(self) -> dict[str, str]:
        self.validate()
        return {key: str(value) for key, value in asdict(self).items()}

    @classmethod
    def from_fields(cls, fields: Mapping[Any, Any]) -> "TaskEnvelope":
        values = _decode_fields(fields)
        task = cls(
            task_id=values["task_id"],
            idempotency_key=values["idempotency_key"],
            project_id=values["project_id"],
            run_id=values["run_id"],
            task_type=values["task_type"],
            record_ref=values["record_ref"],
            schema_version=values["schema_version"],
            config_revision=values["config_revision"],
            codebook_revision=values["codebook_revision"],
            attempt=int(values.get("attempt", "1")),
        )
        task.validate()
        return task


@dataclass(frozen=True, slots=True)
class MessageReceipt:
    request_id: str
    correlation_id: str
    message_id: str
    stream: str


@dataclass(frozen=True, slots=True)
class TaskReceipt:
    task_id: str
    message_id: str
    stream: str
    config_revision: str


@dataclass(slots=True)
class RedisControlPlane:
    client: Any
    project_id: str
    prefix: str = "laclaugpt"
    snapshot_dir: Path = Path("data/config/snapshots")
    actor: Actor = field(default_factory=lambda: Actor("anonymous", "human", frozenset()))

    @property
    def namespace(self) -> ProjectNamespace:
        return ProjectNamespace(project_id=self.project_id, redis_prefix=self.prefix)

    def current_config(self, module: str = "visualization") -> ConfigRevision | None:
        key = self.namespace.settings_key(module, "current")
        raw = self.client.get(key)
        if raw:
            return self._decode_revision(raw)
        return self._load_snapshot(module, "current")

    def publish_config(
        self,
        payload: Mapping[str, Any],
        *,
        module: str = "visualization",
        expected_revision: str | None = None,
    ) -> ConfigRevision:
        self.actor.require("config.publish")
        if module not in MODULES:
            raise ValueError(f"unknown module: {module}")
        secrets = secret_paths(payload)
        if secrets:
            raise ValueError("shared configuration contains secret-like fields: " + ", ".join(secrets))
        current = self.current_config(module)
        if expected_revision is not None and expected_revision != (current.revision if current else None):
            raise RuntimeError("configuration revision conflict")
        revision = ConfigRevision.build(
            project_id=self.project_id,
            module=module,
            payload=payload,
            publisher=self.actor.publisher,
        )
        revision.validate()
        # Durable snapshot first, matching the shared Analysis contract.
        self._snapshot(revision)
        encoded = json.dumps(asdict(revision), ensure_ascii=False, sort_keys=True)
        version_key = self.namespace.settings_key(module, revision.revision)
        current_key = self.namespace.settings_key(module, "current")
        existing = self.client.get(version_key)
        if existing and _decode(existing) != encoded:
            raise ValueError("immutable configuration revision collision")
        self.client.set(version_key, encoded)
        self.client.set(current_key, encoded)
        self.client.xadd(
            self.namespace.stream_key("config-events"),
            {
                "project_id": revision.project_id,
                "module": revision.module,
                "revision": revision.revision,
                "publisher": revision.publisher,
                "created_at": str(revision.created_at),
            },
        )
        return revision

    def send_request(
        self,
        service: str,
        *,
        run_id: str,
        message_type: str,
        config_revision: str,
        body: Mapping[str, Any] | None = None,
        payload_ref: str = "",
        source_record_id: str = "",
        task_id: str = "",
        correlation_id: str | None = None,
    ) -> MessageReceipt:
        self.actor.require("message.send")
        message = MessageEnvelope.build(
            project_id=self.project_id,
            run_id=run_id,
            sender=self.actor.publisher,
            recipient=service,
            message_type=message_type,
            config_revision=config_revision,
            correlation_id=correlation_id,
            source_record_id=source_record_id,
            task_id=task_id,
            payload_ref=payload_ref,
            body=redact_config(dict(body)) if body is not None else None,
        )
        stream = self.namespace.stream_key(f"messages:{service}")
        message_id = _decode(self.client.xadd(stream, message.to_fields()))
        return MessageReceipt(message.request_id, message.correlation_id, message_id, stream)

    def correlated_responses(
        self,
        correlation_id: str,
        *,
        service: str = "visualization",
        count: int = 100,
    ) -> list[dict[str, Any]]:
        stream = self.namespace.stream_key(f"messages:{service}")
        found: list[dict[str, Any]] = []
        for message_id, fields in self.client.xrevrange(stream, count=count):
            try:
                message = MessageEnvelope.from_fields(fields)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
            if message.correlation_id == correlation_id:
                row = asdict(message)
                row["message_id"] = _decode(message_id)
                found.append(row)
        return found

    def request_run(
        self,
        module: Literal["collection", "analysis"],
        *,
        run_id: str,
        config_revision: str,
        payload_ref: str = "",
        body: Mapping[str, Any] | None = None,
    ) -> MessageReceipt:
        self.actor.require("task.trigger")
        return self._send_authorized(
            module,
            run_id=run_id,
            message_type=f"{module}.run.requested",
            config_revision=config_revision,
            payload_ref=payload_ref,
            body=body,
        )

    def publish_analysis_task(self, task: TaskEnvelope) -> TaskReceipt:
        self.actor.require("task.trigger")
        task.validate()
        if task.project_id != self.project_id:
            raise ValueError("task project_id does not match control-plane project")
        stream = self.namespace.stream_key(f"analysis:{task.run_id}:tasks")
        message_id = _decode(self.client.xadd(stream, task.to_fields()))
        return TaskReceipt(task.task_id, message_id, stream, task.config_revision)

    def task_command(
        self,
        module: Literal["collection", "analysis"],
        *,
        run_id: str,
        task_id: str,
        action: Literal["retry", "cancel"],
        config_revision: str,
    ) -> MessageReceipt:
        permission: Permission = "task.retry" if action == "retry" else "task.cancel"
        self.actor.require(permission)
        return self._send_authorized(
            module,
            run_id=run_id,
            message_type=f"task.{action}.requested",
            config_revision=config_revision,
            task_id=task_id,
            body={"task_id": task_id},
        )

    def analysis_tasks(self, run_id: str, *, count: int = 100) -> list[dict[str, Any]]:
        stream = self.namespace.stream_key(f"analysis:{run_id}:tasks")
        result: list[dict[str, Any]] = []
        for message_id, fields in self.client.xrevrange(stream, count=count):
            try:
                task = TaskEnvelope.from_fields(fields)
            except (KeyError, TypeError, ValueError):
                continue
            row = asdict(task)
            row["message_id"] = _decode(message_id)
            result.append(row)
        return result

    def _send_authorized(self, service: str, **kwargs: Any) -> MessageReceipt:
        message = MessageEnvelope.build(
            project_id=self.project_id,
            sender=self.actor.publisher,
            recipient=service,
            **kwargs,
        )
        stream = self.namespace.stream_key(f"messages:{service}")
        message_id = _decode(self.client.xadd(stream, message.to_fields()))
        return MessageReceipt(message.request_id, message.correlation_id, message_id, stream)

    def _snapshot(self, revision: ConfigRevision) -> None:
        root = self.snapshot_dir / self.project_id / revision.module
        root.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(asdict(revision), ensure_ascii=False, sort_keys=True, indent=2)
        version = root / f"{revision.revision}.json"
        if version.exists() and version.read_text(encoding="utf-8") != encoded:
            raise ValueError("immutable configuration revision collision")
        if not version.exists():
            version.write_text(encoded, encoding="utf-8")
        (root / "current.json").write_text(encoded, encoding="utf-8")

    def _load_snapshot(self, module: str, revision: str) -> ConfigRevision | None:
        path = self.snapshot_dir / self.project_id / module / f"{revision}.json"
        if not path.exists():
            return None
        value = ConfigRevision(**json.loads(path.read_text(encoding="utf-8")))
        value.validate()
        return value

    @staticmethod
    def _decode_revision(value: Any) -> ConfigRevision:
        raw = _decode(value)
        revision = ConfigRevision(**json.loads(raw))
        revision.validate()
        return revision

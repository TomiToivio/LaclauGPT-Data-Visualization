import json
from pathlib import Path

import pytest

from laclaugpt_visualization.control_plane import Actor, RedisControlPlane, redact_config


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.streams = {}
        self.counter = 0

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value):
        self.values[key] = value
        return True

    def xadd(self, key, fields):
        self.counter += 1
        message_id = f"{self.counter}-0"
        self.streams.setdefault(key, []).insert(0, (message_id, fields))
        return message_id

    def xrevrange(self, key, count=100):
        return self.streams.get(key, [])[:count]


def actor(*permissions):
    return Actor("researcher-1", "human", frozenset(permissions))


def test_redis_disabled_boundary_is_plain_dependency_injection(tmp_path: Path):
    service = RedisControlPlane(FakeRedis(), "ai26", snapshot_dir=tmp_path)
    assert service.current_config() is None
    with pytest.raises(PermissionError):
        service.publish_config({"enabled": True})


def test_config_revision_flow_redacts_and_snapshots(tmp_path: Path):
    redis = FakeRedis()
    service = RedisControlPlane(
        redis,
        "ai26",
        snapshot_dir=tmp_path,
        actor=actor("config.publish"),
    )
    first = service.publish_config({"collection": {"enabled": True}, "api_token": "do-not-store"})
    assert first.config["api_token"] == "<redacted>"
    assert service.current_config().revision == first.revision
    assert list(tmp_path.glob("ai26-cfg_*.json"))

    second = service.publish_config(
        {"collection": {"enabled": False}}, expected_revision=first.revision
    )
    assert second.previous_revision == first.revision
    with pytest.raises(RuntimeError):
        service.publish_config({}, expected_revision=first.revision)


def test_request_response_correlation_and_actor_audit(tmp_path: Path):
    redis = FakeRedis()
    service = RedisControlPlane(
        redis,
        "ai26",
        snapshot_dir=tmp_path,
        actor=actor("message.send"),
    )
    receipt = service.send_request("rag.query", {"query": "synthetic question"})
    response = {
        "schema_version": "1.0",
        "type": "rag.response",
        "project_id": "ai26",
        "request_id": receipt.request_id,
        "producer": "synthetic-rag",
        "result_ref": "record:synthetic-1",
    }
    redis.xadd(service.response_stream, {"payload": json.dumps(response)})
    found = service.correlated_responses(receipt.request_id)
    assert len(found) == 1
    assert found[0]["result_ref"] == "record:synthetic-1"


def test_task_permission_revision_and_commands(tmp_path: Path):
    redis = FakeRedis()
    service = RedisControlPlane(
        redis,
        "ai26",
        snapshot_dir=tmp_path,
        actor=actor("config.publish", "task.trigger", "task.retry", "task.cancel"),
    )
    revision = service.publish_config({"analysis": {"plugins": ["laclau"]}})
    task = service.trigger_task("analysis.run", {"run_id": "synthetic-run"})
    assert task.config_revision == revision.revision
    assert service.task_command(task.task_id, "retry")
    assert service.task_command(task.task_id, "cancel")
    events = service.task_events()
    assert {item["type"] for item in events} >= {
        "task.requested",
        "task.retry.requested",
        "task.cancel.requested",
    }


def test_secret_redaction_is_recursive():
    clean = redact_config({"nested": {"password": "x", "model": "m"}, "tokens": [{"api_key": "y"}]})
    assert clean["nested"]["password"] == "<redacted>"
    assert clean["nested"]["model"] == "m"
    assert clean["tokens"][0]["api_key"] == "<redacted>"

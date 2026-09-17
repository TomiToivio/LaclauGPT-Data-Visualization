from pathlib import Path

import pytest

from laclaugpt_visualization.control_plane import (
    Actor,
    MessageEnvelope,
    RedisControlPlane,
    TaskEnvelope,
    redact_config,
)


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


def test_read_only_default_and_local_snapshot_fallback(tmp_path: Path):
    service = RedisControlPlane(FakeRedis(), "ai26", snapshot_dir=tmp_path)
    assert service.current_config("visualization") is None
    with pytest.raises(PermissionError):
        service.publish_config({"enabled": True})


def test_config_revision_uses_shared_namespace_and_content_hash(tmp_path: Path):
    redis = FakeRedis()
    service = RedisControlPlane(
        redis,
        "ai26",
        snapshot_dir=tmp_path,
        actor=actor("config.publish"),
    )
    first = service.publish_config({"collection": {"enabled": True}}, module="collection")
    assert service.current_config("collection").revision == first.revision
    assert redis.get(f"laclaugpt:ai26:settings:collection:{first.revision}")
    assert redis.get("laclaugpt:ai26:settings:collection:current")
    assert redis.streams["laclaugpt:ai26:stream:config-events"]
    assert (tmp_path / "ai26" / "collection" / f"{first.revision}.json").exists()
    assert (tmp_path / "ai26" / "collection" / "current.json").exists()

    second = service.publish_config(
        {"collection": {"enabled": False}},
        module="collection",
        expected_revision=first.revision,
    )
    assert second.revision != first.revision
    with pytest.raises(RuntimeError):
        service.publish_config(
            {}, module="collection", expected_revision=first.revision
        )


def test_shared_config_rejects_secret_fields(tmp_path: Path):
    service = RedisControlPlane(
        FakeRedis(),
        "ai26",
        snapshot_dir=tmp_path,
        actor=actor("config.publish"),
    )
    with pytest.raises(ValueError, match="secret-like"):
        service.publish_config({"api_token": "must-not-enter-redis"})


def test_message_contract_and_response_correlation(tmp_path: Path):
    redis = FakeRedis()
    service = RedisControlPlane(
        redis,
        "ai26",
        snapshot_dir=tmp_path,
        actor=actor("message.send"),
    )
    receipt = service.send_request(
        "rag",
        run_id="run-1",
        message_type="rag.query",
        config_revision="cfg-1",
        body={"query": "synthetic question"},
        payload_ref="record:synthetic-1",
    )
    sent = redis.streams["laclaugpt:ai26:stream:messages:rag"][0][1]
    assert sent["project_id"] == "ai26"
    assert sent["run_id"] == "run-1"
    assert sent["correlation_id"] == receipt.correlation_id
    assert sent["sender"] == "human:researcher-1"

    response = MessageEnvelope.build(
        project_id="ai26",
        run_id="run-1",
        sender="rag:synthetic",
        recipient="visualization",
        message_type="rag.response",
        config_revision="cfg-1",
        correlation_id=receipt.correlation_id,
        payload_ref="result:synthetic-1",
    )
    redis.xadd("laclaugpt:ai26:stream:messages:visualization", response.to_fields())
    found = service.correlated_responses(receipt.correlation_id)
    assert len(found) == 1
    assert found[0]["payload_ref"] == "result:synthetic-1"


def test_run_requests_and_analysis_tasks_reuse_shared_streams(tmp_path: Path):
    redis = FakeRedis()
    service = RedisControlPlane(
        redis,
        "ai26",
        snapshot_dir=tmp_path,
        actor=actor("task.trigger", "task.retry", "task.cancel"),
    )
    run_request = service.request_run(
        "analysis",
        run_id="run-1",
        config_revision="cfg-1",
        payload_ref="manifest:run-1",
    )
    assert run_request.stream == "laclaugpt:ai26:stream:messages:analysis"

    task = TaskEnvelope(
        task_id="task-1",
        idempotency_key="idem-1",
        project_id="ai26",
        run_id="run-1",
        task_type="laclau",
        record_ref="record:1",
        schema_version="1.0",
        config_revision="cfg-1",
        codebook_revision="codebook-1",
    )
    receipt = service.publish_analysis_task(task)
    assert receipt.stream == "laclaugpt:ai26:stream:analysis:run-1:tasks"
    assert service.analysis_tasks("run-1")[0]["task_id"] == "task-1"

    retry = service.task_command(
        "analysis",
        run_id="run-1",
        task_id="task-1",
        action="retry",
        config_revision="cfg-1",
    )
    cancel = service.task_command(
        "analysis",
        run_id="run-1",
        task_id="task-1",
        action="cancel",
        config_revision="cfg-1",
    )
    assert retry.stream == cancel.stream == "laclaugpt:ai26:stream:messages:analysis"


def test_secret_redaction_is_recursive():
    clean = redact_config(
        {"nested": {"password": "x", "model": "m"}, "tokens": [{"api_key": "y"}]}
    )
    assert clean["nested"]["password"] == "<redacted>"
    assert clean["nested"]["model"] == "m"
    assert clean["tokens"] == "<redacted>"

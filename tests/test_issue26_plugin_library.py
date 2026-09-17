import json

import pytest

from laclaugpt_visualization.plugins import PluginKind, default_registry
from laclaugpt_visualization.products import DataProduct, InMemoryProvider, ProductKind
from laclaugpt_visualization.services import (
    MongoRecordService,
    RedisConfigService,
    RedisMessageQueueService,
    RedisTaskQueueService,
)


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.lists = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value):
        self.values[key] = value
        return True

    def rpush(self, key, value):
        self.lists.setdefault(key, []).append(value)
        return len(self.lists[key])


class Result:
    matched_count = 1


class FakeCollection:
    def __init__(self):
        self.calls = []

    def update_one(self, query, update):
        self.calls.append((query, update))
        return Result()


def provider(*kinds):
    return InMemoryProvider({kind: DataProduct(kind, []) for kind in kinds})


def test_public_plugin_model_has_two_top_level_kinds_with_legacy_aliases():
    assert set(PluginKind) == {PluginKind.VISUALIZATION, PluginKind.USER_INTERFACE}
    assert PluginKind.INTERACTION is PluginKind.USER_INTERFACE
    assert PluginKind.RESEARCH_ASSISTANT is PluginKind.USER_INTERFACE


def test_catalog_contains_requested_visualization_and_ui_families():
    registry = default_registry()
    names = {plugin.spec.name for plugin in registry.all()}
    assert {
        "table",
        "record_evidence",
        "data_quality",
        "timeline",
        "discourse_graph",
        "map",
        "multimodal_evidence",
        "legacy_ep24",
        "researcher_review",
        "ethnography_notes",
        "mongodb_editor",
        "distributed_settings",
        "task_launcher",
        "rag_chat",
        "agent_console",
        "backend_status",
        "plugin_manager",
    } <= names


def test_backend_and_field_gating_explains_unavailable_plugins():
    registry = default_registry()
    p = provider(ProductKind.RECORDS)

    status = registry.status(
        "mongodb_editor",
        p,
        backend_capabilities=(),
        fields={"source_url"},
        mode="canonical_live",
    )
    assert not status.available
    assert status.missing_backends == frozenset({"mongodb"})
    assert "missing backends: mongodb" in status.reasons

    status = registry.status(
        "record_evidence",
        p,
        backend_capabilities=(),
        fields={"summary"},
        mode="canonical_live",
    )
    assert not status.available
    assert status.missing_fields == frozenset({"source_url"})


def test_visualizations_are_read_only_and_mutations_are_audited():
    registry = default_registry()
    for plugin in registry.all():
        if plugin.spec.kind == PluginKind.VISUALIZATION:
            assert not plugin.spec.mutates_state
        if plugin.spec.mutates_state:
            assert plugin.spec.kind == PluginKind.USER_INTERFACE
            assert plugin.spec.audit_required


def test_redis_config_is_versioned_and_rejects_secret_like_settings():
    redis = FakeRedis()
    service = RedisConfigService(redis)
    first = service.update(
        "AI26",
        "analysis",
        {"window_hours": 24},
        actor="researcher",
        reason="test",
        expected_version=0,
    )
    assert first["version"] == 1
    assert service.get("AI26", "analysis")["values"]["window_hours"] == 24

    with pytest.raises(RuntimeError):
        service.update(
            "AI26",
            "analysis",
            {"window_hours": 12},
            actor="researcher",
            reason="stale form",
            expected_version=0,
        )

    with pytest.raises(ValueError):
        service.update(
            "AI26",
            "analysis",
            {"api_token": "nope"},
            actor="researcher",
            reason="must not leak secrets",
        )


def test_redis_task_and_message_adapters_only_enqueue_structured_envelopes():
    redis = FakeRedis()
    tasks = RedisTaskQueueService(redis)
    messages = RedisMessageQueueService(redis)

    task_id = tasks.enqueue(
        "reprocess",
        {"record_ids": ["r1", "r2"]},
        actor="researcher",
        project="AI26",
        idempotency_key="task-1",
    )
    assert task_id == "task-1"
    task = json.loads(redis.lists["laclaugpt:tasks"][0])
    assert task["task_type"] == "reprocess"
    assert task["payload"]["record_ids"] == ["r1", "r2"]

    message_id = messages.send(
        "Summarize this selection",
        actor="researcher",
        project="AI26",
        context={"record_ids": ["r1"]},
    )
    assert message_id
    message = json.loads(redis.lists["laclaugpt:messages"][0])
    assert message["context"]["record_ids"] == ["r1"]


def test_mongo_edits_are_whitelisted_and_quarantine_is_recoverable():
    collection = FakeCollection()
    service = MongoRecordService(collection, frozenset({"review.note", "tags"}))

    receipt = service.update_fields(
        "r1",
        {"tags": ["checked"]},
        actor="researcher",
        reason="manual review",
    )
    assert receipt.changed_fields == ("tags",)

    with pytest.raises(ValueError):
        service.update_fields(
            "r1",
            {"raw_capture": "overwrite"},
            actor="researcher",
            reason="not editable",
        )

    receipt = service.quarantine("r1", actor="researcher", reason="duplicate")
    assert receipt.action == "quarantine"
    _, update = collection.calls[-1]
    assert update["$set"]["review.excluded"] is True
    assert "$push" in update

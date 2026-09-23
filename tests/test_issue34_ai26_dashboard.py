from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from laclaugpt_visualization.ai26_dashboard import (
    LiveSnapshot,
    RedisAI26ControlPlane,
    _merge_record,
    ai26_collection_names,
    ai26_redis_contract,
    apply_ai26_filters,
)
from laclaugpt_visualization.config import Settings
from laclaugpt_visualization.data import normalize_frame


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.streams = {}

    def get(self, key):
        return self.values.get(key)

    def xadd(self, key, fields, maxlen=None, approximate=None):
        stream = self.streams.setdefault(key, [])
        message_id = f"{len(stream) + 1}-0".encode()
        encoded = {
            (k.encode() if isinstance(k, str) else k): (v.encode() if isinstance(v, str) else v)
            for k, v in fields.items()
        }
        stream.append((message_id, encoded))
        return message_id

    def xrevrange(self, key, count=100):
        return list(reversed(self.streams.get(key, [])))[:count]


def settings(**overrides):
    values = {
        "project_id": "ai26",
        "profile": "server",
        "machine": "linux-server",
        "execution": "web-service",
        "storage": "distributed",
        "storage_backend": "mongodb",
        "data_backend": "mongodb",
        "cache_backend": "redis",
        "object_backend": "s3",
        "messaging_backend": "redis",
        "mongodb_uri": "mongodb://example.invalid",
        "redis_url": "redis://example.invalid",
        "s3_endpoint_url": "https://object.example.invalid",
        "s3_bucket": "private-bucket",
    }
    values.update(overrides)
    return Settings(**values)


def test_ai26_uses_current_pipeline_collections_and_project_namespace():
    cfg = settings()
    names = ai26_collection_names(cfg)
    assert names["records"] == "ai26__records"
    assert names["processing"] == "ai26__processing"
    # Results come from the durable store the current Analysis worker writes.
    assert names["results"] == "ai26__analysis_results"
    # The legacy collection is still addressable, but only under a name that
    # says so; it must not be the source of a progress or freshness metric.
    assert names["legacy_analyzed"] == "ai26__analyzed"
    assert names["relations"] == "ai26__relations"

    redis = ai26_redis_contract(cfg)
    assert redis["visualization_settings"] == "laclaugpt:ai26:settings:visualization:current"
    assert redis["config_events"] == "laclaugpt:ai26:stream:config-events"
    assert redis["rag_messages"] == "laclaugpt:ai26:stream:messages:rag"


def test_ai26_rejects_cross_project_configuration():
    with pytest.raises(ValueError, match="requires"):
        ai26_collection_names(settings(project_id="ep24"))


def test_merge_preserves_multilabel_formations_and_source_identity():
    merged = _merge_record(
        {"source_url": "https://example.test/post/1", "text": "hello"},
        {"formations": ["critical_ai", "left_techno_optimism"], "uncertainties": ["provisional"]},
    )
    assert merged["source_url"] == "https://example.test/post/1"
    assert merged["formations"] == ["critical_ai", "left_techno_optimism"]
    assert merged["uncertainties"] == ["provisional"]


def test_filters_keep_multilabel_records():
    frame = normalize_frame(
        pd.DataFrame(
            [
                {
                    "source_url": "a",
                    "source_platform": "x",
                    "source_country": "FI",
                    "source_language": "fi",
                    "formations": ["critical_ai", "accelerationist"],
                    "summary": "AI debate",
                },
                {
                    "source_url": "b",
                    "source_platform": "telegram",
                    "source_country": "US",
                    "source_language": "en",
                    "formations": ["doomer"],
                    "summary": "risk debate",
                },
            ]
        )
    )
    filtered = apply_ai26_filters(frame, {"formations": ["critical_ai"]})
    assert filtered["source_url"].tolist() == ["a"]


def test_config_publish_is_allowlisted_and_stream_based():
    client = FakeRedis()
    cfg = settings()
    control = RedisAI26ControlPlane(client, cfg)
    request_id = control.publish_visualization_config(
        {"refresh_seconds": 15}, actor="researcher", reason="faster monitoring"
    )
    assert request_id
    stream = client.streams["laclaugpt:ai26:stream:config-events"]
    _, payload = stream[-1]
    decoded = {k.decode(): v.decode() for k, v in payload.items()}
    assert decoded["message_type"] == "config.publish"
    assert json.loads(decoded["body"])["changes"] == {"refresh_seconds": 15}

    with pytest.raises(ValueError, match="read-only"):
        control.publish_visualization_config(
            {"mongodb_uri": "secret"}, actor="researcher", reason="must fail"
        )


def test_rag_request_and_response_preserve_correlation_and_evidence_ids():
    client = FakeRedis()
    cfg = settings()
    control = RedisAI26ControlPlane(client, cfg)
    request_id = control.rag_request(
        "What changed?", actor="researcher", filters={"formations": ["critical_ai"]}
    )
    key = "laclaugpt:ai26:stream:messages:rag"
    client.xadd(
        key,
        {
            "project_id": "ai26",
            "request_id": "response-1",
            "correlation_id": request_id,
            "sender": "rag",
            "recipient": "visualization-ui",
            "message_type": "rag.response",
            "created_at": "2026-09-17T12:00:00+00:00",
            "body": json.dumps(
                {
                    "answer": "A bounded synthetic answer",
                    "evidence": [{"source_record_id": "record-123"}],
                }
            ),
        },
    )
    response = control.rag_response(request_id)
    assert response["answer"] == "A bounded synthetic answer"
    assert response["evidence"][0]["source_record_id"] == "record-123"


def test_live_snapshot_freshness_fields_are_explicit():
    now = datetime.now(UTC)
    snapshot = LiveSnapshot(
        frame=pd.DataFrame(),
        counts={"records": 0, "analyzed": 1, "processing": 0},
        failures=(),
        loaded_at=now.isoformat(),
        query_ms=1,
        page_size=100,
        newest_analyzed_at=(now - timedelta(hours=2)).isoformat(),
        analyzed_age_hours=2.0,
    )
    assert snapshot.newest_analyzed_at
    assert snapshot.analyzed_age_hours == 2.0

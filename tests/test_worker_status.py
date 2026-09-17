import json
from datetime import UTC, datetime, timedelta

from laclaugpt_visualization.config import Settings
from laclaugpt_visualization.worker_status import RedisOperationalStatus


class FakeRedis:
    def __init__(self, values=None, streams=None, *, fail=False):
        self.values = values or {}
        self.streams = streams or {}
        self.fail = fail

    def scan_iter(self, match):
        if self.fail:
            raise ConnectionError("synthetic outage")
        prefix = match.removesuffix("*")
        keys = [*self.values, *self.streams]
        return iter(key for key in keys if key.startswith(prefix))

    def get(self, key):
        if self.fail:
            raise ConnectionError("synthetic outage")
        return self.values.get(key)

    def hgetall(self, key):
        return {}

    def xrevrange(self, key, count=25):
        if self.fail:
            raise ConnectionError("synthetic outage")
        return self.streams.get(key, [])[:count]


def heartbeat(*, updated_at, status="busy", run_id="run-1", worker_id="worker-1"):
    return json.dumps(
        {
            "schema_version": "1.0",
            "project_id": "demo26",
            "run_id": run_id,
            "worker_id": worker_id,
            "worker_role": "analysis",
            "status": status,
            "current_task_id": "task-7",
            "updated_at": updated_at,
            "metadata": {"private_detail": "must never be projected"},
        }
    )


def test_redis_disabled_is_the_default_and_needs_no_url():
    settings = Settings(_env_file=None)
    assert settings.messaging_backend == "none"
    assert settings.redis_url is None
    settings.validate_remote_requirements()


def test_heartbeat_status_is_joinable_and_stale_is_explicit():
    now = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)
    redis = FakeRedis(
        values={
            "laclaugpt:demo26:worker:analysis:fresh": heartbeat(
                updated_at=(now - timedelta(seconds=10)).isoformat(),
                worker_id="fresh",
            ),
            "laclaugpt:demo26:worker:analysis:old": heartbeat(
                updated_at=(now - timedelta(seconds=90)).isoformat(),
                worker_id="old",
                status="idle",
            ),
            "laclaugpt:other:worker:analysis:nope": heartbeat(
                updated_at=now.isoformat(),
                worker_id="wrong-project",
            ),
        }
    )
    snapshot = RedisOperationalStatus(redis, heartbeat_ttl_seconds=60).snapshot(
        "demo26", run_ids={"run-1"}, now=now
    )
    assert snapshot.available
    assert [worker.worker_id for worker in snapshot.workers] == ["fresh", "old"]
    assert snapshot.workers[0].stale is False
    assert snapshot.workers[1].stale is True
    assert snapshot.workers[0].current_task_id == "task-7"


def test_workflow_events_expose_identifiers_not_payloads():
    redis = FakeRedis(
        streams={
            "laclaugpt:demo26:stream:analyzed": [
                (
                    "1-0",
                    {
                        "project_id": "demo26",
                        "run_id": "run-1",
                        "message_id": "msg-1",
                        "task_id": "task-1",
                        "task_type": "analysis.document",
                        "producer": "worker-public-id",
                        "created_at": "2026-09-17T12:00:00Z",
                        "payload": "PRIVATE LARGE PAYLOAD",
                        "token": "SECRET",
                    },
                )
            ]
        }
    )
    snapshot = RedisOperationalStatus(redis).snapshot("demo26", run_ids={"run-1"})
    assert snapshot.available
    assert len(snapshot.events) == 1
    event = snapshot.events[0]
    assert event.task_id == "task-1"
    assert event.task_type == "analysis.document"
    assert not hasattr(event, "payload")
    assert "SECRET" not in repr(event)
    assert "PRIVATE" not in repr(event)


def test_redis_outage_degrades_to_unavailable_snapshot():
    snapshot = RedisOperationalStatus(FakeRedis(fail=True)).snapshot("demo26")
    assert snapshot.available is False
    assert snapshot.workers == ()
    assert snapshot.events == ()
    assert "durable research data is unaffected" in snapshot.note


class FakeRedisRaisingRedisError(FakeRedis):
    """A client that fails the way the real one does.

    ``redis.exceptions.ConnectionError`` derives from ``RedisError``, not from
    the builtin ``ConnectionError`` or ``OSError``, so a handler built from
    builtins alone lets a genuine outage escape (issue #41).
    """

    def scan_iter(self, match):
        raise _redis_connection_error("synthetic outage")

    def get(self, key):
        raise _redis_connection_error("synthetic outage")

    def xrevrange(self, key, count=25):
        raise _redis_connection_error("synthetic outage")


def _redis_connection_error(message: str) -> BaseException:
    from redis.exceptions import ConnectionError as RedisConnectionError

    return RedisConnectionError(message)


def test_redis_client_error_is_treated_as_operational() -> None:
    """The default error set must include the redis client's own hierarchy."""
    from redis.exceptions import RedisError

    errors = RedisOperationalStatus(client=FakeRedis()).error_types
    assert RedisError in errors


def test_real_redis_error_type_is_caught_not_raised() -> None:
    """Regression for #41: a real redis outage must degrade, never propagate."""
    snapshot = RedisOperationalStatus(FakeRedisRaisingRedisError()).snapshot("demo26")
    assert snapshot.available is False
    assert snapshot.workers == ()
    assert snapshot.events == ()
    assert "durable research data is unaffected" in snapshot.note


def test_unreachable_redis_endpoint_degrades() -> None:
    """End-to-end: a client pointed at a closed port must not raise."""
    import pytest

    redis_lib = pytest.importorskip("redis")
    client = redis_lib.from_url("redis://127.0.0.1:6399/0", socket_connect_timeout=1)
    snapshot = RedisOperationalStatus(client=client).snapshot("demo26")
    assert snapshot.available is False


def test_explicit_error_types_are_respected() -> None:
    """A caller that injects its own tuple does not get the redis hierarchy."""
    errors = RedisOperationalStatus(
        client=FakeRedis(), error_types=(ValueError,)
    ).error_types
    assert errors == (ValueError,)


def test_run_filter_prevents_cross_run_status_mix():
    now = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)
    redis = FakeRedis(
        values={
            "laclaugpt:demo26:worker:analysis:a": heartbeat(
                updated_at=now.isoformat(), run_id="run-a", worker_id="a"
            ),
            "laclaugpt:demo26:worker:analysis:b": heartbeat(
                updated_at=now.isoformat(), run_id="run-b", worker_id="b"
            ),
        }
    )
    snapshot = RedisOperationalStatus(redis).snapshot("demo26", run_ids={"run-a"}, now=now)
    assert [worker.worker_id for worker in snapshot.workers] == ["a"]

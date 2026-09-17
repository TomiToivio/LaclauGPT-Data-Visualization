# Optional Redis worker and workflow status

Visualization remains **durable-data-first**. CSV, SQLite, filesystem and MongoDB views do not require Redis. Redis may optionally enrich the workbench with transient worker heartbeats and a small projection of workflow-event identifiers.

The cross-module contract lives in the umbrella repository at `schemas/messaging-task.schema.json` and `docs/MESSAGING_TASK_QUEUE.md`. Visualization follows its `worker_heartbeat` states (`starting`, `idle`, `busy`, `draining`, `stopped`, `error`) and the project-scoped namespace convention:

```text
laclaugpt:<project_id>:worker:<role>:<worker_id>
laclaugpt:<project_id>:stream:<stream-name>
```

## Configuration

The default is no Redis messaging:

```text
LACLAUGPT_VIS_MESSAGING_BACKEND=none
```

To enable only live operational enrichment, configure privately at runtime:

```text
LACLAUGPT_VIS_MESSAGING_BACKEND=redis
LACLAUGPT_REDIS_URL=<private runtime value>
LACLAUGPT_VIS_REDIS_HEARTBEAT_TTL_SECONDS=60
LACLAUGPT_VIS_REDIS_EVENT_LIMIT=25
```

`LACLAUGPT_REDIS_URL` is the canonical umbrella-contract variable. `LACLAUGPT_VIS_REDIS_URL` remains accepted as a compatibility alias. Neither value belongs in tracked configuration.

The optional `redis` Python package is only imported when the live-status tab is opened with Redis messaging enabled. Local/offline use therefore continues to work when Redis is neither installed nor running.

## Safety boundary

`RedisOperationalStatus` is read-only. It exposes only:

- `project_id`, `run_id`, worker ID and role;
- reported worker state and current task ID;
- heartbeat timestamp, age and computed stale flag;
- selected workflow identifiers: stream name, message/task/run IDs, task type, producer and creation timestamp.

It deliberately does **not** expose arbitrary heartbeat metadata, queue payloads, source text, credentials, tokens, notes or large artifacts. Redis errors are converted into an unavailable snapshot rather than propagated into durable dashboard views.

## Freshness and joins

Heartbeats older than `redis_heartbeat_ttl_seconds` are displayed as **stale**. A stale heartbeat is not interpreted as evidence that a worker is still idle, busy, stopped or in error. It is merely an expired transient report.

The dashboard narrows live state to the active project and, where durable provenance contains run IDs, to those run IDs. This joins operational state to durable data by identifiers without turning Redis into historical truth.

If durable run/task history is needed, it must be read from the owning durable store. The Redis panel is an operational convenience only.

## Outage behavior

If Redis is disabled, uninstalled, unreachable, malformed or expired:

1. all durable research tabs remain usable;
2. the Live Status tab reports that live state is disabled or unavailable;
3. no durable record/result is hidden, changed or corrupted;
4. no Redis exception or private connection value is rendered to the user.

This generic adapter is project-neutral and can be reused by AI26 and other distributed studies without making Redis a global Visualization dependency.

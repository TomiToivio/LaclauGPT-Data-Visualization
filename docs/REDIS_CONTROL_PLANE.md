# Redis control plane

Visualization is the human-facing control plane. Redis is optional operational transport; durable stores remain research memory.

## Modes

The normal dashboard works with no Redis. When `LACLAUGPT_REDIS_URL` is configured, Streamlit exposes the multipage **Control Plane** page. The page lazily imports Redis support, so local/offline installations do not require Redis.

The control page is read-only unless explicit permissions are supplied at runtime:

```bash
export LACLAUGPT_VIS_ACTOR_ID=researcher
export LACLAUGPT_VIS_ACTOR_KIND=human
export LACLAUGPT_VIS_CONTROL_PERMISSIONS=config.publish,message.send,task.trigger,task.retry,task.cancel
```

Agents and CLI callers use the same permission names and service API. No actor type bypasses authorization.

## Shared cross-module contract

Visualization deliberately reuses the same namespace and envelope shapes already implemented in Data Analysis coordination/task-queue code.

Examples for project `ai26`:

```text
laclaugpt:ai26:settings:collection:<revision>
laclaugpt:ai26:settings:analysis:<revision>
laclaugpt:ai26:settings:visualization:<revision>
laclaugpt:ai26:settings:<module>:current
laclaugpt:ai26:stream:config-events
laclaugpt:ai26:stream:messages:rag
laclaugpt:ai26:stream:messages:analysis
laclaugpt:ai26:stream:messages:collection
laclaugpt:ai26:stream:messages:visualization
laclaugpt:ai26:stream:analysis:<run_id>:tasks
laclaugpt:ai26:worker:<module>:<worker_id>
laclaugpt:ai26:lock:<name>
```

The shared module vocabulary is `collection`, `analysis`, `visualization`, `storage`, and `simulation`.

## Configuration revisions

The configuration record is wire-compatible with Data Analysis `ConfigRevision`:

```text
project_id
module
revision
payload
created_at
publisher
```

`revision` is the SHA-256 of canonical JSON payload content. Publishing does the following:

1. requires `config.publish`;
2. rejects secret-looking keys rather than sending credentials into shared config;
3. checks an optional expected current revision to prevent lost updates;
4. writes an immutable durable snapshot under `data/config/snapshots/<project>/<module>/` **before** Redis;
5. mirrors the revision to `settings:<module>:<revision>` and `settings:<module>:current`;
6. emits the shared `config-events` stream event.

Redis therefore never becomes the sole copy required for reproducibility. Workers should pin the chosen config revision into run/task/result provenance.

The Streamlit page provides a structured JSON editor, before/after diff, explicit confirmation, local JSON import and sanitized export.

## Messaging

Visualization uses the shared `MessageEnvelope` fields:

```text
project_id
run_id
request_id
correlation_id
sender
recipient
message_type
created_at
config_revision
source_record_id
task_id
payload_ref
body_json
```

Messages are written to `stream:messages:<service>`. Requests and responses preserve `correlation_id`, so the UI can follow a RAG/agent interaction without treating Redis as conversational memory.

Large research payloads must not travel through Redis. Store them in MongoDB/files/object storage and send `payload_ref` or another stable identifier. Inline bodies follow the same bounded-message rule as Analysis.

Typical flows:

```text
Visualization UI -> messages:rag -> RAG service -> messages:visualization
Visualization UI -> messages:analysis -> analysis control service
Visualization UI -> messages:collection -> collection control service
```

Human/agent/CLI origin is visible in `sender`/`publisher`, for example `human:researcher` or `agent:assistant-1`.

## Tasks and workers

High-level collection/analysis run requests use the shared message bus with `collection.run.requested` / `analysis.run.requested`. Visualization does not execute worker logic.

Existing Analysis worker tasks use the canonical `TaskEnvelope` and stream:

```text
laclaugpt:<project>:stream:analysis:<run_id>:tasks
```

The envelope contains task ID, idempotency key, project/run, task type, record reference, schema version, config revision, codebook revision and attempt. Visualization can inspect this operational stream and may publish an authorized task only using the same envelope shape.

Retry/cancel are control requests sent through `messages:<module>`, not invented queue entries. A service that supports the command decides how to apply it. Durable result/failure history remains in the owning module's durable task store.

The existing `RedisOperationalStatus` adapter remains the read-only worker/heartbeat/event projection. It computes stale workers from heartbeat age and deliberately does not expose arbitrary queue payloads. Redis task/worker state is operational telemetry, not historical research truth.

## Safety and privacy

- No Redis URL, credentials, tokens or private endpoints belong in Git.
- Secret-like keys are rejected from shared configuration and redacted from previews/exports.
- Mutation is denied by default.
- Human, agent and CLI origin is recorded on config/message/task actions.
- Impactful configuration/run actions require explicit UI confirmation in addition to permission checks.
- Redis failure falls back to durable dashboard data and local config snapshots.
- `data/config/snapshots/` is under the repository's ignored runtime tree.

## Tests

`tests/test_control_plane.py` uses a synthetic Redis double and covers:

- read-only/local fallback behavior;
- permission enforcement;
- shared namespace compatibility;
- content-addressed config revisions, conflict detection and durable snapshots;
- secret rejection/redaction;
- canonical request/response correlation;
- canonical Analysis task-stream rendering;
- run launch plus retry/cancel messaging.

Together with `tests/test_worker_status.py`, this covers the mutation and telemetry halves of the optional control plane without requiring a live Redis service in CI.

# Redis control plane

Visualization is the human-facing control plane. Redis is optional operational transport; durable stores remain research memory.

## Modes

The normal dashboard works with no Redis. When `LACLAUGPT_REDIS_URL` is configured and either the Redis cache or messaging backend is enabled, Streamlit exposes the multipage **Control Plane** page. The page lazily imports the Redis client, so local/offline installations do not require Redis.

The control page is read-only unless explicit permissions are supplied at runtime:

```bash
export LACLAUGPT_VIS_ACTOR_ID=tomi
export LACLAUGPT_VIS_ACTOR_KIND=human
export LACLAUGPT_VIS_CONTROL_PERMISSIONS=config.publish,message.send,task.trigger,task.retry,task.cancel
```

Agents and CLI callers use the same permission names and service API. No actor type bypasses authorization.

## Shared namespaces

The implementation deliberately reuses the existing project-scoped Redis convention:

```text
laclaugpt:<project>:config:current
laclaugpt:<project>:stream:config
laclaugpt:<project>:stream:requests
laclaugpt:<project>:stream:responses
laclaugpt:<project>:stream:tasks
laclaugpt:<project>:worker:<role>:<worker-id>
laclaugpt:<project>:stream:<workflow-event-stream>
```

The request, response and task streams use compact JSON envelopes with `schema_version=1.0`, project identity, actor/origin metadata, timestamps and reference-based payloads. Large documents, model output, media and research results remain in MongoDB/object storage/files and are referenced by IDs or URIs.

## Configuration revisions

`RedisControlPlane.publish_config()`:

1. requires `config.publish`;
2. recursively redacts secret-looking keys;
3. performs optimistic revision checking when an expected revision is supplied;
4. generates a revision ID and SHA-256 hash of the sanitized configuration;
5. stores the current revision in Redis;
6. appends a `config.updated` event to the configuration stream;
7. writes the same sanitized revision under ignored `data/config/snapshots/`.

That local durable snapshot is intentional. Redis is not sufficient for reproducibility. Project-specific versioned configuration should additionally be captured by the owning Collection/Analysis run provenance when a job starts.

The Streamlit page shows a before/after unified diff and requires an explicit confirmation checkbox before publication.

## Messaging

`send_request()` supports the shared message vocabulary, including `rag.query`, `rag.response`, `agent.request`, lifecycle events, run requests, configuration updates and human annotations. Every outbound request has a correlation/request ID. `correlated_responses()` reads the response stream and selects matching responses/events.

This is transport, not conversational memory. The durable assistant/research result should live outside Redis and be referenced from the response envelope.

## Tasks and workers

`trigger_task()` writes reference-only task requests and includes the effective configuration revision. Visualization does not execute Collection or Analysis logic. Retry/cancel commands are explicit events requiring `task.retry` or `task.cancel`.

The existing `RedisOperationalStatus` adapter remains the read-only worker/heartbeat/event projection. It computes stale workers from heartbeat age and deliberately refuses to display arbitrary queue payloads. Task/event state in Redis is operational telemetry, not historical research truth.

## Safety and privacy

- No Redis URL, credentials, tokens or private endpoints belong in Git.
- Secret-like configuration keys are redacted before Redis publication, local snapshots or UI display.
- Mutation is denied by default.
- Human, agent and CLI origin is recorded on config/message/task actions.
- Impactful configuration/task actions require explicit UI confirmation in addition to permission checks.
- Redis failure does not remove access to durable research data.
- `data/config/snapshots/` is under the repository's ignored `data/` runtime tree.

## Tests

`tests/test_control_plane.py` uses a synthetic in-memory Redis double and covers:

- Redis-disabled/read-only behavior;
- permission enforcement;
- configuration revision conflict detection and durable snapshots;
- recursive secret redaction;
- request/response correlation;
- task launch with config revision provenance;
- retry/cancel commands and auditable actor identity.

Together with `tests/test_worker_status.py`, this covers the mutation and telemetry halves of the optional control plane without requiring a live Redis service in CI.

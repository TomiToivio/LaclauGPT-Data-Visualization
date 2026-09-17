"""Optional human-facing Redis control plane. Redis is never durable research memory."""
from __future__ import annotations

import difflib
import json
import os
from pathlib import Path

import streamlit as st

from laclaugpt_visualization.config import get_settings
from laclaugpt_visualization.control_plane import (
    MODULES,
    Actor,
    RedisControlPlane,
    redact_config,
    secret_paths,
)
from laclaugpt_visualization.task_status import task_status_rows
from laclaugpt_visualization.worker_status import RedisOperationalStatus

st.set_page_config(page_title="LaclauGPT Control Plane", layout="wide")
st.title("LaclauGPT Control Plane")
st.caption(
    "Optional operational control plane. Redis carries shared configuration revisions, "
    "request/response messages and task coordination; durable stores remain research memory."
)

settings = get_settings()
settings.ensure_local_directories()
permissions = frozenset(
    item.strip()
    for item in os.getenv("LACLAUGPT_VIS_CONTROL_PERMISSIONS", "").split(",")
    if item.strip()
)
actor_kind = os.getenv("LACLAUGPT_VIS_ACTOR_KIND", "human")
if actor_kind not in {"human", "agent", "cli", "system"}:
    actor_kind = "human"
actor = Actor(
    os.getenv("LACLAUGPT_VIS_ACTOR_ID", "dashboard-user"),
    actor_kind,
    permissions,
)
snapshot_dir = settings.data_path("config", "snapshots")


def _local_snapshots() -> list[Path]:
    root = snapshot_dir / settings.project_id
    return sorted(root.glob("*/current.json")) if root.exists() else []


def _render_local_snapshots() -> None:
    snapshots = _local_snapshots()
    if not snapshots:
        st.caption("No local control-plane snapshots yet.")
        return
    selected = st.selectbox(
        "Local durable snapshot",
        snapshots,
        format_func=lambda path: f"{path.parent.name} / current",
    )
    payload = json.loads(selected.read_text(encoding="utf-8"))
    safe = redact_config(payload)
    st.json(safe)
    st.download_button(
        "Export sanitized JSON snapshot",
        data=json.dumps(safe, indent=2, sort_keys=True),
        file_name=f"{settings.project_id}-{selected.parent.name}-config.json",
        mime="application/json",
    )


if not settings.redis_url:
    st.info(
        "Redis control plane is disabled. The normal dashboard remains fully usable in local "
        "mode; durable sanitized configuration snapshots can still be inspected/exported."
    )
    _render_local_snapshots()
    st.stop()

try:
    import redis
except ImportError:
    st.error("Install the optional remote dependencies to use the Redis control plane.")
    _render_local_snapshots()
    st.stop()

try:
    client = redis.Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=1.5,
        socket_timeout=1.5,
        decode_responses=False,
    )
    client.ping()
except (ValueError, redis.exceptions.RedisError):
    st.warning(
        "Redis control plane is unavailable. Durable dashboard data and local configuration "
        "snapshots remain available."
    )
    _render_local_snapshots()
    st.stop()

control = RedisControlPlane(
    client,
    settings.project_id,
    prefix=settings.redis_key_prefix,
    snapshot_dir=snapshot_dir,
    actor=actor,
)
operational = RedisOperationalStatus(
    client,
    prefix=settings.redis_key_prefix,
    heartbeat_ttl_seconds=settings.redis_heartbeat_ttl_seconds,
    event_limit=settings.redis_event_limit,
    error_types=(redis.exceptions.RedisError, ConnectionError, OSError, TimeoutError, ValueError),
).snapshot(settings.project_id)

config_tab, messages_tab, tasks_tab, workers_tab = st.tabs(
    ["Configuration", "RAG / Agent messages", "Tasks", "Workers / events"]
)

with config_tab:
    module = st.selectbox("Configuration module", sorted(MODULES))
    current = control.current_config(module)
    current_payload = current.payload if current else {}
    st.caption(
        f"Current revision: {current.revision if current else 'none'} · "
        f"publisher: {current.publisher if current else 'n/a'}"
    )

    imported = st.file_uploader("Import local JSON snapshot", type=["json"], key="config-import")
    initial = current_payload
    if imported is not None:
        try:
            loaded = json.loads(imported.getvalue().decode("utf-8"))
            initial = loaded.get("payload", loaded) if isinstance(loaded, dict) else loaded
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            st.error(f"Could not import JSON: {exc}")

    editor = st.text_area(
        "Shared project configuration (JSON)",
        value=json.dumps(redact_config(initial), indent=2, sort_keys=True),
        height=360,
    )
    proposed = None
    try:
        parsed = json.loads(editor or "{}")
        if not isinstance(parsed, dict):
            raise ValueError("top-level configuration must be an object")
        secrets = secret_paths(parsed)
        if secrets:
            raise ValueError("secret-like fields are not allowed in shared config: " + ", ".join(secrets))
        proposed = parsed
        before = json.dumps(current_payload, indent=2, sort_keys=True).splitlines()
        after = json.dumps(proposed, indent=2, sort_keys=True).splitlines()
        diff = "\n".join(difflib.unified_diff(before, after, fromfile="current", tofile="proposed"))
        st.code(diff or "No changes", language="diff")
        st.download_button(
            "Export proposed JSON snapshot",
            data=json.dumps(redact_config(proposed), indent=2, sort_keys=True),
            file_name=f"{settings.project_id}-{module}-proposed.json",
            mime="application/json",
        )
    except (json.JSONDecodeError, ValueError) as exc:
        st.error(f"Configuration is invalid: {exc}")

    can_publish = "config.publish" in permissions
    confirm = st.checkbox("I confirm publishing this project-wide configuration revision")
    if st.button("Publish revision", disabled=not (can_publish and confirm and proposed is not None)):
        try:
            published = control.publish_config(
                proposed or {},
                module=module,
                expected_revision=current.revision if current else None,
            )
        except (PermissionError, RuntimeError, ValueError, redis.exceptions.RedisError) as exc:
            st.error(str(exc))
        else:
            st.success(
                f"Published {published.revision}; durable snapshot written before Redis update."
            )
    if not can_publish:
        st.caption("Read-only: this actor does not have `config.publish` permission.")

with messages_tab:
    st.caption(
        "Messages use the shared MessageEnvelope contract. Large research payloads stay in "
        "durable storage and travel as payload/source references."
    )
    service = st.selectbox("Recipient service", ["rag", "analysis", "collection", "simulation"])
    message_type = st.selectbox(
        "Message type",
        ["rag.query", "agent.request", "human.annotation.created"],
    )
    run_id = st.text_input("Run ID", key="message-run")
    config_revision = st.text_input("Pinned config revision", key="message-config")
    text = st.text_area("Question / instruction")
    payload_ref = st.text_input("Optional durable payload reference")
    if st.button(
        "Send request",
        disabled=(
            "message.send" not in permissions
            or not text.strip()
            or not run_id.strip()
            or not config_revision.strip()
        ),
    ):
        try:
            receipt = control.send_request(
                service,
                run_id=run_id,
                message_type=message_type,
                config_revision=config_revision,
                body={"text": text},
                payload_ref=payload_ref,
            )
        except (PermissionError, ValueError, redis.exceptions.RedisError) as exc:
            st.error(str(exc))
        else:
            st.session_state["control_correlation_id"] = receipt.correlation_id
            st.success(f"Sent request {receipt.request_id} / correlation {receipt.correlation_id}")

    correlation_id = st.text_input(
        "Correlation ID",
        value=st.session_state.get("control_correlation_id", ""),
    )
    if correlation_id:
        try:
            st.json(control.correlated_responses(correlation_id, service="visualization"))
        except redis.exceptions.RedisError as exc:
            st.warning(f"Response stream unavailable: {exc}")

with tasks_tab:
    st.caption(
        "Run launch/cancel/retry commands use the shared MessageEnvelope bus. Existing Analysis "
        "worker tasks are shown from the canonical analysis:<run>:tasks stream."
    )
    module = st.selectbox("Run service", ["collection", "analysis"])
    run_id = st.text_input("Run ID", key="task-run")
    module_config = control.current_config(module) if run_id else None
    default_revision = module_config.revision if module_config else ""
    config_revision = st.text_input(
        "Pinned config revision",
        value=default_revision,
        key="task-config",
    )
    payload_ref = st.text_input("Optional run manifest / durable payload reference")
    confirm_task = st.checkbox("I confirm launching this distributed run")
    if st.button(
        "Request run",
        disabled=(
            "task.trigger" not in permissions
            or not confirm_task
            or not run_id.strip()
            or not config_revision.strip()
        ),
    ):
        try:
            receipt = control.request_run(
                module,
                run_id=run_id,
                config_revision=config_revision,
                payload_ref=payload_ref,
            )
        except (PermissionError, ValueError, redis.exceptions.RedisError) as exc:
            st.error(str(exc))
        else:
            st.success(f"Run request sent with correlation ID {receipt.correlation_id}")

    if module == "analysis" and run_id:
        try:
            tasks = control.analysis_tasks(run_id, count=100)
        except redis.exceptions.RedisError as exc:
            st.warning(f"Analysis task stream unavailable: {exc}")
            tasks = []
        if tasks:
            st.dataframe(
                task_status_rows(tasks, operational.workers),
                use_container_width=True,
                hide_index=True,
            )
            st.caption(
                "Redis can show current worker/lease visibility. `queued_or_acknowledged` is "
                "intentionally ambiguous: completed/failed truth must come from durable task stores."
            )
            task_ids = sorted({str(item["task_id"]) for item in tasks if item.get("task_id")})
            chosen = st.selectbox("Task command target", task_ids)
            c1, c2 = st.columns(2)
            if c1.button("Retry", disabled="task.retry" not in permissions):
                try:
                    control.task_command(
                        "analysis",
                        run_id=run_id,
                        task_id=chosen,
                        action="retry",
                        config_revision=config_revision,
                    )
                except (PermissionError, ValueError, redis.exceptions.RedisError) as exc:
                    st.error(str(exc))
                else:
                    st.success("Retry request sent through shared message bus")
            if c2.button("Cancel", disabled="task.cancel" not in permissions):
                try:
                    control.task_command(
                        "analysis",
                        run_id=run_id,
                        task_id=chosen,
                        action="cancel",
                        config_revision=config_revision,
                    )
                except (PermissionError, ValueError, redis.exceptions.RedisError) as exc:
                    st.error(str(exc))
                else:
                    st.success("Cancellation request sent through shared message bus")
        else:
            st.caption("No analysis tasks visible for this run.")

with workers_tab:
    st.caption(operational.note)
    st.dataframe(
        [
            {
                "worker_id": item.worker_id,
                "role": item.worker_role,
                "run_id": item.run_id,
                "state": "stale" if item.stale else item.status,
                "task_id": item.current_task_id or "",
                "age_seconds": round(item.age_seconds, 1),
            }
            for item in operational.workers
        ],
        use_container_width=True,
        hide_index=True,
    )
    st.caption(
        "Worker/task telemetry is transient operational state, not canonical research history."
    )

st.sidebar.markdown("### Permissions")
st.sidebar.write(sorted(permissions) if permissions else ["read-only"])
st.sidebar.caption("Agents use exactly the same permission boundary as humans and CLI callers.")

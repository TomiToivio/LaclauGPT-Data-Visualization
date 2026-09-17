"""Optional human-facing Redis control plane. Redis is never durable research memory."""
from __future__ import annotations

import difflib
import json
import os
from pathlib import Path

import streamlit as st

from laclaugpt_visualization.config import get_settings
from laclaugpt_visualization.control_plane import Actor, RedisControlPlane, redact_config
from laclaugpt_visualization.worker_status import RedisOperationalStatus

st.set_page_config(page_title="LaclauGPT Control Plane", layout="wide")
st.title("LaclauGPT Control Plane")
st.caption(
    "Optional operational control plane. Redis carries configuration revisions, requests and "
    "task coordination; durable stores and local snapshots remain the research memory."
)

settings = get_settings()
settings.ensure_local_directories()
permissions = frozenset(
    item.strip()
    for item in os.getenv("LACLAUGPT_VIS_CONTROL_PERMISSIONS", "").split(",")
    if item.strip()
)
actor = Actor(
    os.getenv("LACLAUGPT_VIS_ACTOR_ID", "dashboard-user"),
    os.getenv("LACLAUGPT_VIS_ACTOR_KIND", "human"),
    permissions,
)

snapshot_dir = settings.data_path("config", "snapshots")
redis_enabled = settings.redis_url is not None and (
    settings.cache_backend == "redis" or settings.messaging_backend == "redis"
)

if not redis_enabled:
    st.info(
        "Redis control plane is disabled. The normal dashboard remains fully usable. "
        "Local sanitized configuration snapshots can still be inspected below."
    )
    snapshots = sorted(snapshot_dir.glob(f"{settings.project_id}-cfg_*.json"), reverse=True)
    if snapshots:
        selected = st.selectbox("Local snapshot", snapshots, format_func=lambda path: path.name)
        st.json(json.loads(selected.read_text(encoding="utf-8")))
    else:
        st.caption("No local control-plane snapshots yet.")
    st.stop()

try:
    import redis
except ImportError:
    st.error("Install the optional remote dependencies to use the Redis control plane.")
    st.stop()

try:
    client = redis.Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=1.5,
        socket_timeout=1.5,
        decode_responses=False,
    )
except ValueError:
    st.error("The private runtime Redis URL is invalid.")
    st.stop()

control = RedisControlPlane(
    client,
    settings.project_id,
    prefix=settings.redis_key_prefix,
    snapshot_dir=snapshot_dir,
    actor=actor,
)

config_tab, messages_tab, tasks_tab, workers_tab = st.tabs(
    ["Configuration", "RAG / Agent messages", "Tasks", "Workers / events"]
)

with config_tab:
    current = control.current_config()
    current_dict = current.config if current else {}
    st.caption(
        f"Current revision: {current.revision if current else 'none'} · "
        f"actor: {current.actor_kind + ':' + current.actor_id if current else 'n/a'}"
    )
    editor = st.text_area(
        "Sanitized project configuration (JSON)",
        value=json.dumps(current_dict, indent=2, sort_keys=True),
        height=360,
    )
    try:
        proposed = redact_config(json.loads(editor or "{}"))
        if not isinstance(proposed, dict):
            raise ValueError("top-level configuration must be an object")
        before = json.dumps(current_dict, indent=2, sort_keys=True).splitlines()
        after = json.dumps(proposed, indent=2, sort_keys=True).splitlines()
        diff = "\n".join(difflib.unified_diff(before, after, fromfile="current", tofile="proposed"))
        st.code(diff or "No changes", language="diff")
    except (json.JSONDecodeError, ValueError) as exc:
        proposed = None
        st.error(f"Configuration is invalid: {exc}")

    can_publish = "config.publish" in permissions
    confirm = st.checkbox("I confirm publishing this project-wide configuration revision")
    if st.button("Publish revision", disabled=not (can_publish and confirm and proposed is not None)):
        try:
            published = control.publish_config(
                proposed or {}, expected_revision=current.revision if current else None
            )
        except (PermissionError, RuntimeError) as exc:
            st.error(str(exc))
        else:
            st.success(f"Published {published.revision}; durable local snapshot written.")
    if not can_publish:
        st.caption("Read-only: this actor does not have `config.publish` permission.")

with messages_tab:
    st.caption("Requests are small reference-based messages. Large results stay in durable storage.")
    message_type = st.selectbox("Message type", ["rag.query", "agent.request"])
    text = st.text_area("Question / instruction")
    refs = st.text_input("Optional reference IDs (comma-separated)")
    if st.button("Send request", disabled="message.send" not in permissions or not text.strip()):
        receipt = control.send_request(
            message_type,
            {"text": text, "refs": [item.strip() for item in refs.split(",") if item.strip()]},
        )
        st.session_state["control_request_id"] = receipt.request_id
        st.success(f"Sent request {receipt.request_id}")
    request_id = st.text_input(
        "Correlation/request ID", value=st.session_state.get("control_request_id", "")
    )
    if request_id:
        st.json(control.correlated_responses(request_id))

with tasks_tab:
    task_type = st.selectbox("Task type", ["collection.run", "analysis.run", "reprocess", "media.download"])
    run_ref = st.text_input("Run/source/reference ID")
    confirm_task = st.checkbox("I confirm launching this distributed task")
    if st.button(
        "Trigger task",
        disabled="task.trigger" not in permissions or not confirm_task or not run_ref.strip(),
    ):
        receipt = control.trigger_task(task_type, {"ref": run_ref})
        st.success(
            f"Queued {receipt.task_id} with config revision {receipt.config_revision or 'none'}"
        )
    events = control.task_events(count=100)
    if events:
        st.dataframe(events, use_container_width=True, hide_index=True)
        task_ids = sorted({str(item.get("task_id")) for item in events if item.get("task_id")})
        chosen = st.selectbox("Task command target", task_ids) if task_ids else ""
        c1, c2 = st.columns(2)
        if c1.button("Retry", disabled="task.retry" not in permissions or not chosen):
            control.task_command(chosen, "retry")
            st.success("Retry requested")
        if c2.button("Cancel", disabled="task.cancel" not in permissions or not chosen):
            control.task_command(chosen, "cancel")
            st.success("Cancellation requested")
    else:
        st.caption("No task events visible.")

with workers_tab:
    status = RedisOperationalStatus(
        client,
        prefix=settings.redis_key_prefix,
        heartbeat_ttl_seconds=settings.redis_heartbeat_ttl_seconds,
        event_limit=settings.redis_event_limit,
        error_types=(redis.exceptions.RedisError, ConnectionError, OSError, TimeoutError, ValueError),
    ).snapshot(settings.project_id)
    st.caption(status.note)
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
            for item in status.workers
        ],
        use_container_width=True,
        hide_index=True,
    )
    st.caption("Worker/task telemetry is transient operational state, not canonical history.")

st.sidebar.markdown("### Permissions")
st.sidebar.write(sorted(permissions) if permissions else ["read-only"])
st.sidebar.caption("Agents use the same permission boundary as humans and CLI callers.")

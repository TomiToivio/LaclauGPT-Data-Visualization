"""Safe transient task-status projections for the Redis control plane.

Redis can show queued/pending work and worker leases, but it cannot prove durable completion
or failure. Those states belong to the owning module's durable task/result store.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .worker_status import WorkerHeartbeat


def task_status_rows(
    tasks: Iterable[Mapping[str, Any]],
    workers: Iterable[WorkerHeartbeat],
) -> list[dict[str, Any]]:
    """Join task envelopes to current worker heartbeats without inventing durable outcomes."""
    by_task = {
        worker.current_task_id: worker
        for worker in workers
        if worker.current_task_id
    }
    rows: list[dict[str, Any]] = []
    for task in tasks:
        task_id = str(task.get("task_id") or "")
        worker = by_task.get(task_id)
        if worker is None:
            state = "queued_or_acknowledged"
            worker_id = ""
            lease = "not_visible"
        elif worker.stale:
            state = "worker_stale"
            worker_id = worker.worker_id
            lease = "stale"
        else:
            state = "running"
            worker_id = worker.worker_id
            lease = "active"
        rows.append(
            {
                **dict(task),
                "operational_state": state,
                "worker_id": worker_id,
                "lease_status": lease,
            }
        )
    return rows

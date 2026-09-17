from datetime import UTC, datetime

from laclaugpt_visualization.task_status import task_status_rows
from laclaugpt_visualization.worker_status import WorkerHeartbeat


def worker(task_id: str, *, stale: bool = False) -> WorkerHeartbeat:
    return WorkerHeartbeat(
        project_id="ai26",
        run_id="run-1",
        worker_id="worker-1",
        worker_role="analysis",
        status="busy",
        current_task_id=task_id,
        updated_at=datetime(2026, 9, 17, tzinfo=UTC),
        stale=stale,
        age_seconds=5.0 if not stale else 120.0,
    )


def test_task_status_renders_running_and_stale_worker_without_claiming_completion():
    tasks = [
        {"task_id": "task-running", "task_type": "laclau"},
        {"task_id": "task-stale", "task_type": "embedding"},
        {"task_id": "task-unknown", "task_type": "topic"},
    ]
    rows = task_status_rows(
        tasks,
        [worker("task-running"), worker("task-stale", stale=True)],
    )
    states = {row["task_id"]: row["operational_state"] for row in rows}
    assert states == {
        "task-running": "running",
        "task-stale": "worker_stale",
        "task-unknown": "queued_or_acknowledged",
    }
    assert all(row["operational_state"] not in {"completed", "failed"} for row in rows)

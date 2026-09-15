from laclaugpt_visualization.runtime import dashboard_runtime_violation


def test_runtime_rejects_slurm_jobs() -> None:
    reason = dashboard_runtime_violation({"SLURM_JOB_ID": "123"}, hostname="node")
    assert reason == "interactive visualization is disabled inside Slurm/HPC allocations"


def test_runtime_rejects_roihu() -> None:
    reason = dashboard_runtime_violation({}, hostname="roihu-login")
    assert reason == "interactive visualization is disabled on CSC Roihu"


def test_runtime_accepts_local_workstation() -> None:
    assert dashboard_runtime_violation({}, hostname="laptop") is None

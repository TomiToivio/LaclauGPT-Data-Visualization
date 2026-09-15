"""Runtime policy extracted from the original LaclauGPT visualization package."""
from __future__ import annotations

import os
import socket
from collections.abc import Mapping


def dashboard_runtime_violation(
    environment: Mapping[str, str] | None = None,
    hostname: str | None = None,
) -> str | None:
    """Return a reason when an interactive dashboard should not run here.

    Interactive Streamlit visualization belongs on a laptop/workstation or a
    persistent web host such as CSC Pouta, not inside Slurm/Roihu batch jobs.
    """
    env = dict(os.environ if environment is None else environment)
    host = (hostname or socket.gethostname()).casefold()
    cluster = " ".join(
        str(env.get(key, ""))
        for key in (
            "SLURM_CLUSTER_NAME",
            "CSC_COMPUTING_ENV",
            "LACLAUGPT_RUNTIME",
            "HOSTNAME",
        )
    ).casefold()
    if env.get("SLURM_JOB_ID"):
        return "interactive visualization is disabled inside Slurm/HPC allocations"
    if "roihu" in host or "roihu" in cluster:
        return "interactive visualization is disabled on CSC Roihu"
    return None


def require_dashboard_runtime() -> None:
    """Raise when the dashboard is launched on an unsuitable batch host."""
    reason = dashboard_runtime_violation()
    if reason:
        raise RuntimeError(
            f"{reason}; run the dashboard locally or on a persistent Linux web server "
            "such as CSC Pouta instead"
        )

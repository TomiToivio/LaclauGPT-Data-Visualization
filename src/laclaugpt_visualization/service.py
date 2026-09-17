"""Web-service planning and offline health/readiness checks."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .config import Settings
from .runtime import dashboard_runtime_violation

AI26_PROJECT_ID = "ai26"
AI26_DASHBOARD_MODULE = "ai26_dashboard.py"


def dashboard_module(settings: Settings) -> Path:
    """Return the Streamlit module that serves this profile.

    The AI26 research workbench (`ai26_dashboard.py`) is not the same surface as
    the legacy generic workbench (`app.py`): it carries the AI26 Monitor /
    Explore / Networks / Records / Reports / RAG / Configuration views. Serving
    the generic module for an AI26 profile would report healthy while showing
    the wrong dashboard, so the project id decides which module is launched
    (issue #44).
    """
    directory = Path(__file__).parent
    if settings.project_id == AI26_PROJECT_ID:
        return directory / AI26_DASHBOARD_MODULE
    return directory / "app.py"


def streamlit_command(settings: Settings) -> list[str]:
    """Return the canonical Streamlit launch command without executing it."""
    app = dashboard_module(settings)
    return [
        "python",
        "-m",
        "streamlit",
        "run",
        str(app),
        "--server.address",
        settings.server_host,
        "--server.port",
        str(settings.server_port),
        "--server.headless",
        "true",
    ]


def readiness(
    settings: Settings,
    *,
    environment: dict[str, str] | None = None,
    hostname: str | None = None,
) -> dict[str, Any]:
    """Validate deployment configuration without contacting external services."""
    errors: list[str] = []
    try:
        settings.validate_remote_requirements()
    except ValueError as exc:
        errors.append(str(exc))

    violation = dashboard_runtime_violation(environment=environment, hostname=hostname)
    if violation:
        errors.append(violation)

    if settings.analysis_data_dir is not None and not settings.analysis_data_dir.exists():
        errors.append("configured Analysis data directory does not exist")

    # A deployment that cannot serve the dashboard for its own project must not
    # report healthy (issue #44).
    module = dashboard_module(settings)
    if not module.is_file():
        errors.append(f"dashboard module missing for project {settings.project_id!r}: {module.name}")

    runtime_root = settings.data_dir.resolve()
    output_root = settings.output_dir.resolve()
    try:
        output_root.relative_to(runtime_root)
    except ValueError:
        errors.append("output_dir must stay below the private data_dir runtime tree")

    return {
        "status": "ready" if not errors else "not-ready",
        "errors": errors,
        "config": settings.safe_summary(),
        "pid": os.getpid(),
    }

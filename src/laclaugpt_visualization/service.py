"""Web-service planning and offline health/readiness checks."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .config import Settings
from .runtime import dashboard_runtime_violation


def streamlit_command(settings: Settings) -> list[str]:
    """Return the canonical Streamlit launch command without executing it."""
    app = Path(__file__).with_name("app.py")
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

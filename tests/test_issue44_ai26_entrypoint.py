"""The AI26 deployment must serve the AI26 dashboard (issue #44).

The repository shipped two entrypoints: the deployment service example ran
`laclaugpt-visualize serve`, which launched the legacy generic workbench
(`app.py`), while the operator guide and launcher script launched the AI26
research dashboard (`ai26_dashboard.py`). Following the deployment example
produced a healthy service showing the wrong dashboard, silently, because
readiness validated configuration rather than the served module.

These tests pin the contract: the project decides the module.
"""

from __future__ import annotations

from pathlib import Path

from laclaugpt_visualization.config import Settings
from laclaugpt_visualization.service import (
    AI26_DASHBOARD_MODULE,
    dashboard_module,
    readiness,
    streamlit_command,
)

REPO_ROOT = Path(__file__).parents[1]


def _ai26_settings() -> Settings:
    return Settings(project_id="ai26")


def test_ai26_profile_serves_the_ai26_dashboard() -> None:
    module = dashboard_module(_ai26_settings())
    assert module.name == AI26_DASHBOARD_MODULE
    assert module.is_file(), "the AI26 dashboard module must exist in the package"


def test_ai26_serve_command_launches_the_ai26_dashboard() -> None:
    command = streamlit_command(_ai26_settings())
    assert command[:3] == ["python", "-m", "streamlit"]
    assert command[3] == "run"
    assert command[4].endswith(AI26_DASHBOARD_MODULE)
    assert not command[4].endswith("/app.py")


def test_non_ai26_profile_keeps_the_generic_workbench() -> None:
    """Project-awareness must not change behaviour for other projects."""
    module = dashboard_module(Settings(project_id="default"))
    assert module.name == "app.py"


def test_deployment_service_example_uses_the_project_aware_command() -> None:
    """The installed service must run the command that serves the AI26 module."""
    example = (
        REPO_ROOT / "deploy" / "laclaugpt-visualization-laskin-ai26.service.example"
    ).read_text(encoding="utf-8")
    assert "ExecStart=" in example
    exec_line = next(
        line for line in example.splitlines() if line.startswith("ExecStart=")
    )
    assert "laclaugpt-visualize serve" in exec_line


def test_readiness_reports_missing_dashboard_module(monkeypatch, tmp_path) -> None:
    """A profile whose dashboard module is absent must not report ready."""
    settings = _ai26_settings()
    monkeypatch.setattr(
        "laclaugpt_visualization.service.dashboard_module",
        lambda _settings: tmp_path / "definitely-absent.py",
    )
    result = readiness(settings)
    assert result["status"] == "not-ready"
    assert any("dashboard module missing" in error for error in result["errors"])


def test_documented_start_commands_agree() -> None:
    """The operator guide must not document a different module than serve uses."""
    guide = (REPO_ROOT / "docs" / "AI26_DASHBOARD.md").read_text(encoding="utf-8")
    assert "laclaugpt-visualize serve" in guide or "run_ai26_dashboard.sh" in guide
    launcher = (REPO_ROOT / "scripts" / "run_ai26_dashboard.sh").read_text(
        encoding="utf-8"
    )
    assert AI26_DASHBOARD_MODULE in launcher

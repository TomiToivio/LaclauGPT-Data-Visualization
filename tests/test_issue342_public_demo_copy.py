"""A public demo copy of the AI26 dashboard (#342).

The copy uses the same maintained code and the same entrypoint as the development service; what
changes is the data scope and the served surface. These tests pin both, because a demo that
silently serves raw corpus text, configuration or agent operations is worse than no demo.
"""

from __future__ import annotations

from pathlib import Path

from laclaugpt_visualization.ai26_dashboard import PUBLIC_DEMO_TABS, RESEARCH_TABS, visible_tabs
from laclaugpt_visualization.config import Settings

REPO_ROOT = Path(__file__).parents[1]


def test_demo_mode_is_off_by_default() -> None:
    assert Settings(project_id="ai26").demo_mode is False


def test_demo_mode_comes_from_the_environment(monkeypatch) -> None:
    monkeypatch.setenv("LACLAUGPT_VIS_DEMO_MODE", "true")
    settings = Settings(project_id="ai26")
    assert settings.demo_mode is True
    # The label is rendered verbatim in the banner and is never invented by the code.
    assert settings.demo_data_label == ""


def test_a_research_deployment_keeps_every_tab() -> None:
    assert visible_tabs(False) == RESEARCH_TABS
    assert "Records" in visible_tabs(False)
    assert "Configuration" in visible_tabs(False)


def test_a_demo_copy_cannot_reach_raw_records_configuration_or_agent_ops() -> None:
    served = visible_tabs(True)
    assert served == ("Monitor", "Explore", "Networks", "Reports")
    for excluded in ("Records", "RAG Chat", "Configuration", "Hermes", "Diagnostics"):
        assert excluded not in served


def test_the_demo_tabs_are_a_subset_of_the_research_tabs() -> None:
    assert set(PUBLIC_DEMO_TABS) <= set(RESEARCH_TABS)


def test_the_copy_unit_uses_the_supported_entrypoint_and_not_a_hardcoded_address() -> None:
    unit = (REPO_ROOT / "deploy" / "laclaugpt-visualization-public-demo.service.example").read_text(
        encoding="utf-8"
    )
    assert "laclaugpt-visualize serve" in unit
    assert "--server.address" not in unit, "the copy must take its bind address from the env file"
    assert "EnvironmentFile=" in unit
    assert "ReadOnlyPaths=" in unit


def test_the_env_template_names_the_surface_without_values_or_secrets() -> None:
    template = (REPO_ROOT / "deploy" / "public-demo.env.example").read_text(encoding="utf-8")
    required = (
        "LACLAUGPT_VIS_MONGODB_URI",
        "LACLAUGPT_VIS_MONGODB_DATABASE",
        "LACLAUGPT_VIS_SERVER_HOST",
        "LACLAUGPT_VIS_SERVER_PORT",
        "LACLAUGPT_VIS_DEMO_MODE",
        "LACLAUGPT_VIS_DEMO_DATA_LABEL",
    )
    for name in required:
        assert f"{name}=" in template
    assert "LACLAUGPT_VIS_SERVER_HOST=127.0.0.1" in template
    assert "LACLAUGPT_VIS_DEMO_MODE=true" in template
    # No real credentials, no real host: every unset value stays a placeholder.
    for line in template.splitlines():
        if line.startswith("LACLAUGPT_VIS_MONGODB_URI="):
            assert "<" in line, "the template must not carry a usable connection string"


def test_the_copy_runbook_exists_and_names_the_gated_surfaces() -> None:
    doc = (REPO_ROOT / "docs" / "AI26_PUBLIC_DEMO_COPY.md").read_text(encoding="utf-8")
    assert "LACLAUGPT_VIS_DEMO_MODE=true" in doc
    for surface in ("Records", "RAG Chat", "Configuration", "Hermes", "Diagnostics"):
        assert surface in doc

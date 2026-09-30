"""Regression coverage for issue #162 canonical AI26 deployment contract."""

from __future__ import annotations

from pathlib import Path

from laclaugpt_visualization.config import Settings
from laclaugpt_visualization.service import readiness

REPO_ROOT = Path(__file__).parents[1]
CONTRACT_ENV = "LACLAUGPT_VIS_BROWSER_DATA_CONTRACT=canonical"


def test_ai26_deployment_artifacts_provision_canonical_browser_contract() -> None:
    preflight = (REPO_ROOT / "deploy" / "preflight-laskin-ai26.sh").read_text(encoding="utf-8")
    service = (
        REPO_ROOT / "deploy" / "laclaugpt-visualization-laskin-ai26.service.example"
    ).read_text(encoding="utf-8")
    env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")

    assert 'LACLAUGPT_VIS_BROWSER_DATA_CONTRACT:-}" == "canonical"' in preflight
    assert f"Environment={CONTRACT_ENV}" in service
    assert CONTRACT_ENV in env_example


def test_profile_and_health_expose_effective_browser_contract(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        project_id="ai26",
        browser_data_contract="canonical",
        data_dir=tmp_path,
        output_dir=tmp_path / "exports",
        sqlite_path=tmp_path / "database" / "visualization.sqlite3",
    )

    assert settings.safe_summary()["browser_data_contract"] == "canonical"
    assert readiness(settings)["config"]["browser_data_contract"] == "canonical"


def test_phase0_compatibility_contract_remains_explicitly_selectable(tmp_path: Path) -> None:
    """#172 made canonical the default but deliberately kept phase0 reachable.

    This is the compatibility half of the contract: removing phase0 from the
    Settings Literal must fail this test rather than silently leaving the suite green.
    """
    settings = Settings(
        _env_file=None,
        project_id="ai26",
        browser_data_contract="phase0",
        data_dir=tmp_path,
        output_dir=tmp_path / "exports",
        sqlite_path=tmp_path / "database" / "visualization.sqlite3",
    )

    assert settings.browser_data_contract == "phase0"
    assert settings.safe_summary()["browser_data_contract"] == "phase0"
    assert readiness(settings)["config"]["browser_data_contract"] == "phase0"


def test_canonical_is_code_level_ai26_phase2_default() -> None:
    settings = Settings(_env_file=None)
    assert settings.browser_data_contract == "canonical"

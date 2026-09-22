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


def test_phase0_remains_code_level_compatibility_default() -> None:
    settings = Settings(_env_file=None)
    assert settings.browser_data_contract == "phase0"

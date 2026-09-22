import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_server_launcher_defaults_to_loopback_and_requires_private_analysis_dir() -> None:
    text = (ROOT / "scripts" / "run_private_dashboard.sh").read_text(encoding="utf-8")
    assert "LACLAUGPT_VIS_ANALYSIS_DATA_DIR:?" in text
    assert "STREAMLIT_SERVER_ADDRESS=${STREAMLIT_SERVER_ADDRESS:-127.0.0.1}" in text
    assert "LACLAUGPT_VIS_ALLOW_NONLOOPBACK" in text


def test_public_deployment_doc_contains_no_concrete_private_infrastructure() -> None:
    text = (ROOT / "docs" / "STUDY_DEPLOYMENTS.md").read_text(encoding="utf-8")
    assert "CSC Pouta" in text
    assert "AI26" in text
    assert re.search(r"project_\\d{5,}", text, flags=re.IGNORECASE) is None
    assert re.search(r"\\b(?:10|192\\.168|172\\.(?:1[6-9]|2\\d|3[01])|100\\.(?:6[4-9]|[7-9]\\d|1[01]\\d|12[0-7]))\\.", text) is None
    assert "/scratch/" not in text

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_server_launcher_defaults_to_loopback_and_requires_private_analysis_dir():
    text = (ROOT / "scripts" / "run_private_dashboard.sh").read_text(encoding="utf-8")
    assert "LACLAUGPT_VIS_ANALYSIS_DATA_DIR:?" in text
    assert "STREAMLIT_SERVER_ADDRESS=${STREAMLIT_SERVER_ADDRESS:-127.0.0.1}" in text
    assert "LACLAUGPT_VIS_ALLOW_NONLOOPBACK" in text


def test_public_deployment_doc_contains_no_concrete_private_infrastructure():
    text = (ROOT / "docs" / "STUDY_DEPLOYMENTS.md").read_text(encoding="utf-8")
    assert "CSC Pouta" in text
    assert "AI26" in text
    assert "project_2009497" not in text
    assert "100.115." not in text
    assert "/scratch/" not in text

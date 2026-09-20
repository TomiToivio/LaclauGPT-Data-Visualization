"""Regression coverage for Phase 1 AI26-on-Laskin deployment (issue #134)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from laclaugpt_visualization.config import Settings
from laclaugpt_visualization.service import AI26_DASHBOARD_MODULE, dashboard_module
from laclaugpt_visualization.transforms import explore, monitor

REPO_ROOT = Path(__file__).parents[1]


def test_ai26_phase1_configuration_selects_canonical_dashboard() -> None:
    settings = Settings(
        _env_file=None,
        project_id="ai26",
        browser_data_contract="canonical",
        profile="server",
        machine="linux-server",
        execution="web-service",
    )
    assert settings.project_id == "ai26"
    assert settings.browser_data_contract == "canonical"
    assert dashboard_module(settings).name == AI26_DASHBOARD_MODULE


def test_ai26_project_config_contains_phase1_filters_and_safeguards() -> None:
    config = yaml.safe_load(
        (REPO_ROOT / "configs" / "projects" / "ai26.yaml").read_text(encoding="utf-8")
    )
    assert config["project_id"] == "ai26"
    assert {"time", "source", "platform", "language", "formation", "signifier", "topic"} <= set(
        config["filters"]
    )
    assert {"Monitor", "Explore", "Records"} <= set(config["tabs"])
    safeguards = " ".join(config["semantic_safeguards"]).casefold()
    assert "frequency is not hegemony" in safeguards
    assert "centrality is not a nodal point" in safeguards


def test_mixed_ai26_corpus_renders_monitor_and_explore_without_inference() -> None:
    frame = pd.DataFrame(
        [
            {
                "source_url": "synthetic://ai26/analyzed",
                "source_timestamp": "2026-09-20T10:00:00Z",
                "analysis_timestamp": "2026-09-20T10:05:00Z",
                "analysis_status": "complete",
                "review_status": "PROVISIONAL",
                "source_author": "Synthetic Researcher",
                "formations": ["Synthetic Formation"],
                "signifiers": ["future"],
                "topics": ["Synthetic Topic"],
                "entities": ["Synthetic Entity"],
                "relations": [],
            },
            {
                "source_url": "synthetic://ai26/awaiting",
                "source_timestamp": "2026-09-20T10:10:00Z",
                "analysis_timestamp": "",
                "analysis_status": "collection-only",
                "review_status": "PROVISIONAL",
                "source_author": "Synthetic Researcher",
                "formations": [],
                "signifiers": [],
                "topics": [],
                "entities": [],
                "relations": [],
            },
        ]
    )

    metrics = monitor(frame)
    views = explore(frame)

    assert metrics["documents"] == 2
    assert metrics["analyzed"] == 1
    assert metrics["awaiting_analysis"] == 1
    assert "descriptive occurrence counts only" in metrics["frequency_note"]
    assert list(views["formations"]["formations"]) == ["Synthetic Formation"]


def test_study_namespaces_keep_ai26_isolated_from_brazil26() -> None:
    ai26 = Settings(_env_file=None, project_id="ai26")
    brazil26 = Settings(_env_file=None, project_id="brazil26")

    assert ai26.resolved_mongodb_collection != brazil26.resolved_mongodb_collection
    assert ai26.distributed_namespace.redis_key("monitor") != brazil26.distributed_namespace.redis_key(
        "monitor"
    )


def test_laskin_deployment_artifacts_are_path_configurable() -> None:
    script = (REPO_ROOT / "deploy" / "preflight-laskin-ai26.sh").read_text(encoding="utf-8")
    service = (
        REPO_ROOT / "deploy" / "laclaugpt-visualization-laskin-ai26.service.example"
    ).read_text(encoding="utf-8")

    assert "/mnt/workspace/" not in script
    assert "/mnt/workspace/" not in service
    assert "LACLAUGPT_VIS_REPO_ROOT" in script
    assert "LACLAUGPT_VIS_ENV_FILE" in script
    assert "<visualization-root>" in service
    assert "<private-env-file>" in service
    assert "<private-runtime-root>" in service
    assert "LACLAUGPT_VIS_BROWSER_DATA_CONTRACT" in script

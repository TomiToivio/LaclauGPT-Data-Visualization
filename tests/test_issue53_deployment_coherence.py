"""Regression coverage for issue #53 deployment coherence."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parents[1]


def test_laskin_preflight_rejects_active_legacy_units() -> None:
    script = (REPO_ROOT / "deploy" / "preflight-laskin-ai26.sh").read_text(encoding="utf-8")
    assert "ai26-dashboard.service" in script
    assert "ai26-export.service" in script
    assert "ai26-export.timer" in script
    assert "legacy AI26 user units are still active" in script


def test_runbook_retires_legacy_jsonl_export() -> None:
    guide = (REPO_ROOT / "docs" / "AI26_LASKIN_DASHBOARD.md").read_text(encoding="utf-8")
    assert "legacy JSONL dashboard/export path" in guide
    assert "disable --now ai26-dashboard.service ai26-export.service ai26-export.timer" in guide
    assert "atomic rename" in guide


def test_ai26_dashboard_surfaces_analysis_freshness() -> None:
    source = (REPO_ROOT / "src" / "laclaugpt_visualization" / "ai26_dashboard.py").read_text(
        encoding="utf-8"
    )
    assert "newest_analyzed_at" in source
    assert "analyzed_age_hours" in source
    assert "Analysis is stale" in source
    assert "Analysis freshness unavailable: no durable analysis result" in source

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
    """Freshness must be surfaced with all three states handled.

    Asserted on structure rather than one exact sentence: issue #165 rewrote the
    wording (freshness now comes from the durable results store, and the
    duplicate Monitor banner was removed), and a test pinned to a phrase from
    the previous wording turned that into a red `main` rather than a caught
    regression.
    """
    source = (REPO_ROOT / "src" / "laclaugpt_visualization" / "ai26_dashboard.py").read_text(
        encoding="utf-8"
    )
    assert "newest_analyzed_at" in source
    assert "analyzed_age_hours" in source
    # Stale state.
    assert "Analysis is stale" in source
    # Unknown/unavailable state: the capability must remain, whatever it is called.
    assert "Analysis freshness unavailable" in source
    # Fresh state.
    assert "Analysis freshness:" in source
    # The threshold must still exist, so the warning was not silenced.
    assert "FRESHNESS_WARNING_HOURS" in source

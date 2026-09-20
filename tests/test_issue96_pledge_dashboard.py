from __future__ import annotations

import pandas as pd

from laclaugpt_visualization.config import Settings
from laclaugpt_visualization.plugins import default_registry
from laclaugpt_visualization.pledge_dashboard import build_pledge_snapshot


def test_pledge_dashboard_is_opt_in_and_independently_disableable(monkeypatch):
    assert Settings(_env_file=None).specialized_pledge_dashboard_enabled is False
    monkeypatch.setenv("LACLAUGPT_VIS_SPECIALIZED_PLEDGE_DASHBOARD_ENABLED", "true")
    assert Settings(_env_file=None).specialized_pledge_dashboard_enabled is True


def test_pledge_plugin_is_restored_not_placeholder():
    plugin = default_registry().get("pledge_dashboard").spec
    assert plugin.placeholder is False
    assert plugin.source == "pledge_dashboard.py"
    assert "source_url" in plugin.required_fields


def test_pledge_snapshot_is_deterministic_and_preserves_source_identity():
    frame = pd.DataFrame(
        [
            {
                "source_url": "https://example.test/b",
                "source_timestamp": "2026-09-02T10:00:00Z",
                "source_country": "Poland",
                "source_platform": "Instagram",
                "grievance": "Jobs and wages",
                "legacy_derived_alignment": "Centre",
                "topics": ["AI", "Labour"],
            },
            {
                "source_url": "https://example.test/a",
                "source_timestamp": "2026-09-01T10:00:00Z",
                "source_country": "Finland",
                "source_platform": "TikTok",
                "grievance": "Public services first",
                "political_alignment": "Left",
                "topics": ["AI", "Welfare"],
            },
        ]
    )
    snapshot = build_pledge_snapshot(frame).as_dict()
    assert snapshot == {
        "state": "ready",
        "records": [
            {
                "source_url": "https://example.test/a",
                "date": "2026-09-01",
                "country": "Finland",
                "platform": "TikTok",
                "grievance": "Public services first",
                "political_alignment": "Left",
                "alignment_observation_status": "observed",
                "topics": ["AI", "Welfare"],
            },
            {
                "source_url": "https://example.test/b",
                "date": "2026-09-02",
                "country": "Poland",
                "platform": "Instagram",
                "grievance": "Jobs and wages",
                "political_alignment": "Centre",
                "alignment_observation_status": "legacy_derived",
                "topics": ["AI", "Labour"],
            },
        ],
        "alignment_counts": {"legacy_derived": 1, "observed": 1},
        "country_counts": {"Finland": 1, "Poland": 1},
        "topic_counts": {"AI": 2, "Labour": 1, "Welfare": 1},
        "error": "",
    }


def test_pledge_snapshot_has_loading_empty_and_error_states():
    assert build_pledge_snapshot(None).state == "loading"
    assert build_pledge_snapshot(pd.DataFrame()).state == "empty"
    broken = build_pledge_snapshot(pd.DataFrame([{"summary": "missing identity"}]))
    assert broken.state == "error"
    assert "source_url" in broken.error

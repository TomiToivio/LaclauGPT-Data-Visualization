import pytest

from laclaugpt_visualization.config import Settings
from laclaugpt_visualization.data import frame_from_records
from laclaugpt_visualization.transforms import explore, monitor


def _analysis_result():
    return {
        "schema_version": "1.1.0",
        "project_id": "ai26",
        "source_url": "synthetic://issue-144/1",
        "source": {
            "platform": "synthetic",
            "author": "fixture",
            "country": "FI",
            "language": "en",
            "created_at": "2026-09-21T10:00:00Z",
        },
        "content": {"text": "Synthetic Phase 1 handoff record."},
        "analysis": {
            "status": "complete",
            "summary": "Synthetic analyzed result",
            "formations": [{"object_id": "f1", "label": "Synthetic Formation", "kind": "formation"}],
            "signifiers": [{"object_id": "s1", "label": "future", "kind": "signifier"}],
            "relations": [
                {
                    "relation_id": "r1",
                    "relation_type": "equivalence",
                    "source_ref": "future",
                    "target_ref": "Synthetic Formation",
                }
            ],
        },
        "evidence": [],
        "review": {"status": "PROVISIONAL"},
    }


def test_default_source_is_analysis_output_collection():
    settings = Settings(_env_file=None, project_id="ai26")

    assert settings.expected_mongodb_collection == "ai26__analysis_results"
    assert settings.resolved_mongodb_collection == "ai26__analysis_results"


def test_preflight_rejects_canonical_collection_drift():
    settings = Settings(
        _env_file=None,
        project_id="ai26",
        data_backend="mongodb",
        mongodb_uri="mongodb://example.invalid",
        mongodb_collection="ai26__annotations",
    )

    with pytest.raises(ValueError, match="canonical MongoDB source must match Analysis output"):
        settings.validate_remote_requirements()


def test_analysis_handoff_shape_reaches_monitor_and_explore_without_conversion():
    frame = frame_from_records([_analysis_result()])

    assert frame.iloc[0]["source_url"] == "synthetic://issue-144/1"
    assert monitor(frame)["analyzed"] == 1

    views = explore(frame)
    assert views["formations"].iloc[0]["formations"] == "Synthetic Formation"
    assert views["relations"].iloc[0]["type"] == "equivalence"

from pathlib import Path

import pytest
import yaml

from laclaugpt_visualization.project_config import compose_ai26_profile, sanitize_mapping

PUBLIC = Path("configs/projects/ai26.yaml")


def test_public_ai26_profile_uses_canonical_ids_and_multilabel_semantics():
    profile = compose_ai26_profile(PUBLIC)
    assert profile.project_id == "ai26"
    assert profile.storage == "distributed"
    assert profile.data_backend == "mongodb"
    assert set(profile.formations) == {
        "accelerationism",
        "doomerism",
        "left-wing accelerationism",
        "ai safety",
        "ai critical",
        "anti-ai",
    }
    assert all(item.provisional and item.multi_label for item in profile.formations.values())
    assert "frequency is not hegemony" in profile.semantic_safeguards


def test_private_overlay_can_change_display_settings_but_not_project_identity(tmp_path):
    overlay = tmp_path / "private.yaml"
    overlay.write_text(
        yaml.safe_dump({"limits": {"refresh_seconds": 15}, "project_id": "ai26"}),
        encoding="utf-8",
    )
    profile = compose_ai26_profile(PUBLIC, private_overlay_path=overlay)
    assert profile.limits.refresh_seconds == 15

    overlay.write_text(yaml.safe_dump({"project_id": "other"}), encoding="utf-8")
    with pytest.raises(ValueError, match="project_id"):
        compose_ai26_profile(PUBLIC, private_overlay_path=overlay)


def test_required_private_overlay_fails_closed(tmp_path):
    missing = tmp_path / "missing.yaml"
    with pytest.raises(FileNotFoundError):
        compose_ai26_profile(PUBLIC, private_overlay_path=missing, require_private=True)


def test_secret_keys_are_redacted_from_diagnostics():
    safe = sanitize_mapping(
        {
            "mongodb_uri": "mongodb://user:password@example.invalid/db",
            "redis_url": "redis://secret@example.invalid/0",
            "nested": {"s3_secret_access_key": "secret", "display": "ok"},
        }
    )
    assert safe["mongodb_uri"] == "<redacted>"
    assert safe["redis_url"] == "<redacted>"
    assert safe["nested"]["s3_secret_access_key"] == "<redacted>"
    assert safe["nested"]["display"] == "ok"

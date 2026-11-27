"""The copyable public demo: allowlist, bundle contract and view surface (issue #342)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from laclaugpt_visualization.ai26_dashboard import DEMO_TABS
from laclaugpt_visualization.config import Settings


def _stored() -> dict:
    """One stored AI26 record with exactly the fields a demo must not leak."""
    return {
        "_id": "mongo-only",
        "result": {
            "schema_version": "1.0.0",
            "project_id": "ai26",
            "source_url": "https://example.test/post/1",
            "source_native_ids": {"platform_post_id": "1"},
            "source": {
                "platform": "x",
                "author": "synthetic",
                "created_at": "2026-11-01T10:00:00+00:00",
                "arena": "elites",
                "language": "en",
                "raw_metadata": {"engagement": {"like_count": 3}},
            },
            "content": {
                "title": "Synthetic title",
                "text": "Synthetic text about pacing.",
                "media_references": [{"kind": "image", "url": "https://example.test/i.jpg"}],
            },
            "analysis": {
                "summary": "Synthetic summary.",
                "formations": ["ai safety"],
                "plugin_results": {"dna_statement_coding": {"proposal": {"statements": []}}},
                "model_runs": [{"model": "synthetic", "endpoint": "http://private.test"}],
            },
            "raw_capture": {"payload": {"cookies": "not public"}},
            "provenance": [{"collector": "synthetic", "git_commit": "abc"}],
            "review": {"reviewer": "private"},
        },
    }


def test_the_bundle_keeps_only_allowlisted_fields() -> None:
    from scripts.export_ai26_demo_bundle import public_record

    row = public_record(_stored())
    assert row is not None
    text = json.dumps(row, sort_keys=True)
    assert row["source_url"] == "https://example.test/post/1"
    assert row["source"]["arena"] == "elites"
    assert row["content"]["text"] == "Synthetic text about pacing."
    assert row["analysis"]["summary"] == "Synthetic summary."
    for leaked in (
        "cookies",
        "not public",
        "private.test",
        "reviewer",
        "platform_post_id",
        "media_references",
        "raw_capture",
        "provenance",
        "mongo-only",
        "plugin_results",
    ):
        assert leaked not in text, leaked


def test_a_record_without_identity_or_text_is_dropped() -> None:
    from scripts.export_ai26_demo_bundle import public_record

    anonymous = _stored()
    anonymous["result"].pop("source_url")
    assert public_record(anonymous) is None

    empty = _stored()
    empty["result"]["content"] = {"title": "", "text": ""}
    assert public_record(empty) is None


def test_writing_a_bundle_records_a_checksum_and_an_as_of_stamp(tmp_path: Path) -> None:
    from scripts.export_ai26_demo_bundle import _sha256, write_bundle

    manifest = write_bundle([_stored()], tmp_path, as_of="2026-11-26T00:00:00+00:00")
    assert manifest["records"] == 1
    assert manifest["data_as_of"] == "2026-11-26T00:00:00+00:00"
    assert manifest["files"]["records.jsonl"] == _sha256(tmp_path / "records.jsonl")
    assert (tmp_path / "README.md").read_text().count("LACLAUGPT_VIS_DEMO_MODE") == 1
    assert json.loads((tmp_path / "manifest.json").read_text())["bundle_version"] == 1


def test_an_empty_public_bundle_is_refused(tmp_path: Path) -> None:
    from scripts.export_ai26_demo_bundle import write_bundle

    with pytest.raises(ValueError, match="allowlist"):
        write_bundle([], tmp_path)


def test_the_demo_renders_only_read_only_views() -> None:
    assert DEMO_TABS == ("Explore", "Networks", "Records")
    for private_view in ("Reports", "RAG Chat", "Configuration", "Hermes", "Diagnostics"):
        assert private_view not in DEMO_TABS


def test_demo_mode_is_off_unless_asked_for() -> None:
    assert Settings(_env_file=None).demo_mode is False
    demo = Settings(_env_file=None, demo_mode=True, demo_bundle=Path("/tmp/bundle/records.jsonl"))
    assert demo.demo_mode is True
    assert demo.demo_bundle == Path("/tmp/bundle/records.jsonl")


def test_the_live_dataset_source_is_opt_in_and_explicit() -> None:
    """A copy reads a bundle unless the operator names the live source (issue #342)."""
    default = Settings(_env_file=None)
    assert default.demo_source == "bundle"
    live = Settings(_env_file=None, demo_mode=True, demo_source="live")
    assert live.demo_source == "live"
    # Demo mode is still off by default, so the research deployment is untouched.
    assert default.demo_mode is False

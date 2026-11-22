"""#263 §4 option (b): a review decision is an append-only event, not a UI state.

The risk this file guards against is a workbench that *looks* like it recorded a judgement and did not, or
one that silently rewrites a researcher's earlier decision.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from laclaugpt_visualization.ep24_review_log import (
    REVIEW_DIR_ENV,
    SCHEMA,
    ReviewError,
    ReviewStore,
    clean_values,
)


def _store(tmp_path: Path, **kwargs) -> ReviewStore:
    # A review directory outside the code checkout is the normal deployment; the guard is tested separately.
    kwargs.setdefault("application_root", tmp_path / "code-checkout")
    return ReviewStore(tmp_path / "reviews", **kwargs)


def test_a_decision_is_one_immutable_line(tmp_path):
    store = _store(tmp_path)
    event = store.append("ep24:finland:x", "finland", {"video_checked": True, "researcher_note": "frame 3"},
                         reviewer="tomi")
    shard = store.shards()[0]
    lines = shard.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["schema"] == SCHEMA
    assert payload["event_id"] == event.event_id
    assert payload["record_key"] == "ep24:finland:x"
    assert payload["values"] == {"video_checked": True, "researcher_note": "frame 3"}


def test_correcting_a_decision_appends_and_never_rewrites(tmp_path):
    store = _store(tmp_path)
    store.append("k1", "finland", {"dubious_video": True})
    store.append("k1", "finland", {"dubious_video": False, "researcher_note": "checked again"})
    lines = store.shards()[0].read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2  # both decisions are still there
    folded = store.fold("k1")
    assert folded.events == 2
    # An explicit False is a decision: the reviewer cleared the flag, and the history still holds the first.
    assert folded.values["dubious_video"] is False
    assert folded.values["researcher_note"] == "checked again"


def test_an_unconfigured_deployment_refuses_to_save(tmp_path):
    store = ReviewStore.from_environment({}, application_root=tmp_path / "code-checkout")
    assert store.enabled is False
    assert "no review directory" in store.unsafe_reason()
    with pytest.raises(ReviewError):
        store.append("k1", "finland", {"video_checked": True})


def test_a_directory_inside_the_code_checkout_is_refused(tmp_path):
    repository = tmp_path / "LaclauGPT-Data-Visualization"
    (repository / "src").mkdir(parents=True)
    store = ReviewStore(repository / "reviews", application_root=repository)
    assert store.enabled is True
    assert "inside the code checkout" in store.unsafe_reason()
    with pytest.raises(ReviewError):
        store.append("k1", "finland", {"video_checked": True})


def test_the_checkout_root_itself_is_not_a_review_destination(tmp_path):
    repository = tmp_path / "LaclauGPT-Data-Visualization"
    repository.mkdir()
    store = ReviewStore(repository, application_root=repository)
    assert "inside the code checkout" in store.unsafe_reason()
    with pytest.raises(ReviewError, match="inside the code checkout"):
        store.append("k1", "finland", {"video_checked": True})
    assert not list(repository.glob("events-*.jsonl"))


def test_an_unknown_field_is_refused_rather_than_stored(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ReviewError, match="unknown review field"):
        store.append("k1", "finland", {"video_cheked": True})  # typo must not become a field


def test_an_empty_decision_is_refused(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ReviewError, match="at least one decision"):
        store.append("k1", "finland", {"researcher_note": "   "})


def test_a_decision_without_a_record_is_refused(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ReviewError, match="record"):
        store.append("", "finland", {"video_checked": True})


def test_lists_accumulate_and_scalars_take_the_newest_value(tmp_path):
    store = _store(tmp_path)
    store.append("k1", "finland", {"new_persons": ["Alice"], "cut_at": "12"})
    store.append("k1", "finland", {"new_persons": ["Bob", "Alice"], "cut_at": "15"})
    folded = store.fold("k1")
    assert folded.values["new_persons"] == ["Alice", "Bob"]
    assert folded.values["cut_at"] == "15"


def test_a_corrupt_line_is_skipped_and_reported_without_losing_the_rest(tmp_path):
    store = _store(tmp_path)
    store.append("k1", "finland", {"video_checked": True})
    shard = store.shards()[0]
    with shard.open("a", encoding="utf-8") as handle:
        handle.write("{not json\n")
    store.append("k2", "poland", {"video_checked": True})
    events, warnings = store.read()
    assert len(events) == 2
    assert len(warnings) == 1 and "not valid JSON" in warnings[0]
    assert store.summary()["records"] == 2


def test_events_are_sharded_by_month(tmp_path):
    store = _store(tmp_path)
    store.append("k1", "finland", {"video_checked": True}, when=datetime(2026, 5, 3, tzinfo=UTC))
    store.append("k2", "poland", {"video_checked": True}, when=datetime(2026, 6, 1, tzinfo=UTC))
    assert [path.name for path in store.shards()] == ["events-2026-05.jsonl", "events-2026-06.jsonl"]


def test_summary_names_records_reviewers_and_warnings(tmp_path):
    store = _store(tmp_path)
    store.append("k1", "finland", {"video_checked": True}, reviewer="tomi")
    store.append("k2", "poland", {"video_checked": True}, reviewer="tomi")
    summary = store.summary()
    assert summary["events"] == 2 and summary["records"] == 2
    assert summary["reviewers"] == ["tomi"] and summary["warnings"] == []


def test_form_values_are_normalised_before_they_enter_the_log():
    assert clean_values({"new_persons": "Alice, Bob;  , Carol"}) == {"new_persons": ["Alice", "Bob", "Carol"]}
    assert clean_values({"researcher_note": "  spaced  ", "video_checked": False}) == {
        "researcher_note": "spaced", "video_checked": False}


def test_the_store_reads_the_configured_directory_from_the_environment(tmp_path):
    store = ReviewStore.from_environment({REVIEW_DIR_ENV: str(tmp_path / "r")},
                                         application_root=tmp_path / "code-checkout")
    assert store.enabled is True
    store.append("k1", "finland", {"video_checked": True})
    assert store.fold("k1").values == {"video_checked": True}


def _synthetic_export(root: Path) -> Path:
    """A one-record export in the delivered shape, so the workbench renders without private data."""
    root.mkdir(parents=True, exist_ok=True)
    columns = ["source_key", "country", "source_type", "video_id", "asr_transcript",
               "political_preference", "video_duration_seconds", "researcher_note"]
    row = {"source_key": "ep24:finland:review-1", "country": "finland", "source_type": "instagram",
           "video_id": "v1", "asr_transcript": "spoken words", "political_preference": "right",
           "video_duration_seconds": "42", "researcher_note": ""}
    (root / "combined.csv").write_text(
        ",".join(columns) + "\n" + ",".join(f'"{row[c]}"' for c in columns) + "\n", encoding="utf-8")
    return root


def _workbench_app(monkeypatch, export: Path, review_dir: Path | None):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("LACLAUGPT_VIS_ANALYSIS_DATA_DIR", str(export))
    monkeypatch.delenv("LACLAUGPT_VIS_DEMO_PASSWORD", raising=False)
    if review_dir is None:
        monkeypatch.delenv(REVIEW_DIR_ENV, raising=False)
    else:
        monkeypatch.setenv(REVIEW_DIR_ENV, str(review_dir))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1]
                                / "src" / "laclaugpt_visualization" / "ep24_reprocessed_app.py"),
                            default_timeout=120)
    app.session_state["demo_authenticated"] = True
    app.run(timeout=120)
    next(radio for radio in app.sidebar.radio if radio.label == "Research view").set_value(
        "Legacy parity · workbench").run(timeout=120)
    return app


def test_the_workbench_records_a_decision_through_the_ui(tmp_path, monkeypatch):
    export = _synthetic_export(tmp_path / "export")
    reviews = tmp_path / "reviews"
    app = _workbench_app(monkeypatch, export, reviews)
    assert not app.exception, app.exception

    app.text_area[0].set_value("checked frame 3")
    next(button for button in app.button if "Record decision" in button.label).click().run(timeout=120)
    assert not app.exception, app.exception

    shards = list(reviews.glob("events-*.jsonl"))
    assert len(shards) == 1
    payload = json.loads(shards[0].read_text(encoding="utf-8").splitlines()[0])
    assert payload["record_key"] == "ep24:finland:review-1"
    assert payload["values"]["researcher_note"] == "checked frame 3"
    assert payload["schema"] == SCHEMA


def test_an_unconfigured_deployment_offers_no_form_to_fill(tmp_path, monkeypatch):
    export = _synthetic_export(tmp_path / "export")
    app = _workbench_app(monkeypatch, export, None)
    assert not app.exception, app.exception
    assert not any("Record decision" in button.label for button in app.button)
    assert any("not configured" in str(info.value) for info in app.info)

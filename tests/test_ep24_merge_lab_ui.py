"""The review UI is only as good as what it refuses (#300, deliverable 2).

The browser is not trusted: it can send any JSON, replay an action, or be open twice. These tests
pin the properties that keep a review session honest — validation, autosave, undo, resume,
conflict detection and a deck without duplicate labels — without starting Streamlit.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboards"))

from ep24_merge_lab import session as sessions

APP = ROOT / "dashboards" / "ep24_merge_lab" / "ui" / "app.py"
COMPONENT = ROOT / "dashboards" / "ep24_merge_lab" / "ui" / "merge_lab_component"


def _load_app():
    spec = importlib.util.spec_from_file_location("ep24_merge_lab_app", APP)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


app = _load_app()


# ------------------------------------------------------------------ sessions


def test_a_session_round_trips_with_autosave(tmp_path: Path):
    review = sessions.new_session("s1", "run-1", "tomi")
    sessions.save(tmp_path, review)
    review.add(sessions.Action(action="merge", category="person", canonical="A", members=("A", "B"), uid="u1"))
    sessions.save(tmp_path, review)

    loaded = sessions.load(tmp_path, "s1")
    assert loaded.reviewer == "tomi"
    assert [action.uid for action in loaded.effective] == ["u1"]
    assert loaded.revision == review.revision


def test_undo_and_redo_move_a_cursor_rather_than_deleting(tmp_path: Path):
    review = sessions.new_session("s2", "run-1")
    for index in range(3):
        review.add(sessions.Action(action="merge", category="person", members=("A", "B"), uid=f"u{index}"))
    assert review.can_undo and not review.can_redo
    review.undo()
    assert len(review.effective) == 2 and review.can_redo
    review.redo()
    assert len(review.effective) == 3
    # A new action after undoing replaces the branch that was undone, not the whole history.
    review.undo()
    review.add(sessions.Action(action="merge", category="person", members=("C", "D"), uid="u9"))
    assert [action.uid for action in review.effective] == ["u0", "u1", "u9"]


def test_a_session_edited_elsewhere_is_not_overwritten(tmp_path: Path):
    review = sessions.new_session("s3", "run-1")
    sessions.save(tmp_path, review)
    stale_digest = review.digest
    other = sessions.load(tmp_path, "s3")
    other.add(sessions.Action(action="merge", category="person", members=("A", "B"), uid="u1"))
    sessions.save(tmp_path, other)
    with pytest.raises(sessions.SessionConflict):
        sessions.load(tmp_path, "s3", expect_digest=stale_digest)


def test_a_corrupt_session_is_refused(tmp_path: Path):
    path = sessions.session_path(tmp_path, "s4")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"schema_version": 1, "session_id": "s4", "digest": "nope"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="corrupt"):
        sessions.load(tmp_path, "s4")


# ------------------------------------------------------------------ validation


CARDS = [{"id": "A", "label": "A"}, {"id": "B", "label": "B"}]


def test_the_browser_cannot_merge_a_label_with_itself():
    with pytest.raises(ValueError, match="itself"):
        app.validate({"action": "merge", "source": "A", "target": "A"}, "person", CARDS)


def test_the_browser_cannot_act_on_a_label_that_is_not_on_the_deck():
    with pytest.raises(ValueError, match="must exist"):
        app.validate({"action": "merge", "source": "A", "target": "ZZ"}, "person", CARDS)


def test_the_browser_cannot_invent_an_action():
    with pytest.raises(ValueError, match="unknown action"):
        app.validate({"action": "delete_everything", "source": "A"}, "person", CARDS)


def test_a_merge_defaults_its_canonical_to_the_target():
    action = app.validate({"action": "merge", "source": "A", "target": "B"}, "person", CARDS)
    assert action.canonical == "B" and action.members == ("A", "B") and action.uid


# ------------------------------------------------------------------ deck and replay


def _run(tmp_path: Path) -> Path:
    run = tmp_path / "runs" / "20260101T000000Z"
    run.mkdir(parents=True)
    (run / "canonical_person.csv").write_text(
        "canonical,members,member_count,occurrences,confidence,method\n"
        'Petteri Orpo,"Orpo | Petteri Orpo",2,241,0.930,surname\n',
        encoding="utf-8",
    )
    (run / "review_person.csv").write_text(
        "label,occurrences,alternatives,reason\n"
        "Orpo,4,\"Petteri Orpo (0.930)\",bare surname\n"
        "Matti Orpo,2,\"Petteri Orpo (0.760)\",near miss\n",
        encoding="utf-8",
    )
    return run


def test_a_label_inside_a_cluster_is_not_offered_again(tmp_path: Path):
    """Otherwise the same spelling gets two contradictory decisions."""
    deck = app.deck_for(_run(tmp_path), "person")
    labels = [card["label"] for card in deck]
    assert labels.count("Petteri Orpo") == 1
    assert labels.count("Orpo") == 0, "Orpo is already a member of the cluster above"
    assert "Matti Orpo" in labels
    assert len(labels) == len(set(labels))


def test_a_merge_collapses_two_cards_and_undo_restores_them(tmp_path: Path):
    deck = app.deck_for(_run(tmp_path), "person")
    merge = sessions.Action(action="merge", category="person", canonical="Petteri Orpo",
                            members=("Petteri Orpo", "Matti Orpo"), uid="u1")
    merged = app.apply_actions(deck, [merge])
    assert len(merged) == len(deck) - 1
    assert any(card["label"] == "Petteri Orpo" for card in merged)
    assert not any(card["label"] == "Matti Orpo" for card in merged)
    restored = app.apply_actions(deck, [])
    assert any(card["label"] == "Matti Orpo" for card in restored)


def test_a_keep_separate_decision_clears_both_cards(tmp_path: Path):
    deck = app.deck_for(_run(tmp_path), "person")
    action = sessions.Action(action="keep_separate", category="person",
                             members=("Petteri Orpo", "Matti Orpo"), uid="u2")
    cards = app.apply_actions(deck, [action])
    assert not any(card["label"] in {"Petteri Orpo", "Matti Orpo"} for card in cards)


# ------------------------------------------------------------------ the component itself


def test_the_component_speaks_the_streamlit_protocol():
    html = (COMPONENT / "index.html").read_text(encoding="utf-8")
    for marker in ("streamlit:componentReady", "streamlit:setComponentValue", "streamlit:render"):
        assert marker in html
    assert 'draggable' in html and "dragstart" in html and "drop" in html
    assert "ArrowRight" in html, "keyboard access is not optional"


def test_the_page_reads_no_private_path_from_the_repository():
    source = APP.read_text(encoding="utf-8")
    assert "LACLAUGPT_EP24_CURATION" in source
    assert "/mnt/" not in source and "/home/" not in source


def test_a_committed_decision_is_not_written_twice(tmp_path: Path):
    review = sessions.new_session("s9", "run-1", "tomi")
    action = sessions.Action(action="merge", category="person", canonical="X",
                             members=("A", "B"), uid="u1")
    review.add(action)
    first = app.commit(tmp_path, review, review.effective)
    second = app.commit(tmp_path, review, review.effective)
    assert (first, second) == (1, 0)
    lines = (tmp_path / "decisions.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["source_ref"] == "s9:u1"

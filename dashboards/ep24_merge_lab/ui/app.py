"""Streamlit review surface for the legacy EP24 merge lab (#300, deliverable 2).

The page is deliberately thin: it loads one curation run, turns each category into a deck of
cards, and hands the deck to a JavaScript component that does the dragging. Every action the
component sends is validated here before it touches a file — the browser proposes, Python decides.

Nothing in this module analyses anything. It reads the run the CLI wrote, records decisions, and
writes them back through the same `decisions.jsonl` the CLI already honours, so a review done in
the browser and a review done with `merge_labels.py decide` are the same act.
"""
from __future__ import annotations

import csv
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

try:  # the package is importable when this file is run from the repository root
    from ep24_merge_lab import curation
    from ep24_merge_lab import session as sessions
    from ep24_merge_lab.model import CATEGORIES
except ImportError:  # pragma: no cover - streamlit run adds the script's directory to sys.path
    import sys

    # ui/app.py -> dashboards is two levels up; the package lives there.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from ep24_merge_lab import curation
    from ep24_merge_lab import session as sessions
    from ep24_merge_lab.model import CATEGORIES

_COMPONENT = None


def component():
    """The drag-and-drop component, declared on first use.

    Declaring it at import time would make this module unimportable outside a Streamlit run —
    which is exactly what the tests do to exercise the pure parts.
    """
    global _COMPONENT
    if _COMPONENT is None:
        _COMPONENT = components.declare_component(
            "ep24_merge_lab", path=str(Path(__file__).parent / "merge_lab_component")
        )
    return _COMPONENT

TITLES = {
    "entity": "Entities",
    "person": "Persons",
    "theme": "Themes",
    "topic": "Topics",
    "sentiment": "Sentiments",
}
PAGE_SIZE = 24
SORTS = {
    "confidence (lowest first)": lambda card: (card["confidence"], -card["count"]),
    "occurrences (highest first)": lambda card: (-card["count"], card["confidence"]),
    "label (A→Z)": lambda card: (card["label"].casefold(), 0),
}


# ------------------------------------------------------------------ reading a run


def curation_root() -> Path:
    """The private curation directory; the page refuses to guess one."""
    root = os.environ.get("LACLAUGPT_EP24_CURATION", "").strip()
    if not root:
        raise RuntimeError(
            "LACLAUGPT_EP24_CURATION is not set; point it at the private curation directory"
        )
    return Path(root).expanduser()


def latest_run(root: Path) -> Path:
    marker = root / "LATEST"
    if not marker.exists():
        raise RuntimeError(f"no completed run in {root}: run merge_labels.py run first")
    run = root / "runs" / marker.read_text(encoding="utf-8").strip()
    if not run.is_dir():
        raise RuntimeError(f"LATEST names {run}, which does not exist")
    return run


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def deck_for(run: Path, category: str) -> list[dict[str, Any]]:
    """Cards for one category: merged clusters first, then the labels the CLI could not settle."""
    cards: list[dict[str, Any]] = []
    decided: set[str] = set()
    for row in _rows(run / f"canonical_{category}.csv"):
        members = [item for item in row["members"].split(" | ") if item]
        decided.update(members)
        cards.append(
            {
                "id": row["canonical"],
                "label": row["canonical"],
                "aliases": [member for member in members if member != row["canonical"]],
                "count": int(row["occurrences"] or 0),
                "confidence": float(row["confidence"] or 0),
                "method": row["method"],
                "kind": "cluster",
            }
        )
    for row in _rows(run / f"review_{category}.csv"):
        if row["label"] in decided:
            # The label is already inside a cluster: showing it again would invite a second,
            # contradictory decision about the same spelling.
            continue
        alternatives = [
            part.strip().rsplit(" (", 1)[0]
            for part in row.get("alternatives", "").split("|")
            if part.strip()
        ]
        confidence = 0.0
        if row.get("alternatives", "").strip().endswith(")"):
            try:
                confidence = float(row["alternatives"].rsplit("(", 1)[1].rstrip(")"))
            except ValueError:
                confidence = 0.0
        cards.append(
            {
                "id": row["label"],
                "label": row["label"],
                "aliases": alternatives,
                "count": int(row.get("occurrences") or 0),
                "confidence": confidence,
                "method": "candidate",
                "kind": "review",
                "reason": row.get("reason", ""),
            }
        )
    return cards


# ------------------------------------------------------------------ applying decisions


def _find(cards: list[dict[str, Any]], label: str) -> dict[str, Any] | None:
    for card in cards:
        if card["label"] == label:
            return card
    return None


def apply_actions(deck: list[dict[str, Any]], actions: list[sessions.Action]) -> list[dict[str, Any]]:
    """Replay a session over a fresh deck. Deterministic, so undo is just a shorter prefix."""
    cards = [dict(card) for card in deck]
    for action in actions:
        if action.action == "merge":
            source, target = _find(cards, action.members[0] if action.members else ""), _find(
                cards, action.members[1] if len(action.members) > 1 else ""
            )
            if not source or not target or source is target:
                continue
            canonical = (action.canonical or target["label"]).strip()
            merged = {
                "id": canonical,
                "label": canonical,
                "aliases": sorted(
                    set(source["aliases"])
                    | set(target["aliases"])
                    | {source["label"], target["label"]}
                    - {canonical}
                ),
                "count": source["count"] + target["count"],
                "confidence": 1.0,
                "method": "researcher",
                "kind": "cluster",
            }
            cards = [card for card in cards if card is not source and card is not target]
            cards.insert(0, merged)
        elif action.action == "keep_separate":
            keep = set(action.members)
            cards = [card for card in cards if card["label"] not in keep]
        elif action.action == "rename":
            card = _find(cards, action.members[0] if action.members else "")
            if card:
                card["aliases"] = sorted(set(card["aliases"]) | {card["label"]} - {action.canonical})
                card["label"] = action.canonical
                card["id"] = action.canonical
        elif action.action == "split":
            card = _find(cards, action.canonical)
            if card and action.target in card["aliases"]:
                card["aliases"] = [item for item in card["aliases"] if item != action.target]
                cards.append(
                    {
                        "id": action.target,
                        "label": action.target,
                        "aliases": [],
                        "count": 0,
                        "confidence": 0.0,
                        "method": "researcher",
                        "kind": "review",
                    }
                )
        elif action.action == "confirm":
            cards = [card for card in cards if card["label"] != action.canonical]
    return cards


def validate(payload: dict[str, Any], category: str, cards: list[dict[str, Any]]) -> sessions.Action:
    """Refuse anything the browser should not be able to say."""
    action = str(payload.get("action", ""))
    if action not in sessions.ACTIONS:
        raise ValueError(f"unknown action {action!r}")
    labels = {card["label"] for card in cards}
    source = str(payload.get("source", "")).strip()
    target = str(payload.get("target", "")).strip()
    canonical = str(payload.get("canonical", "")).strip()
    if action in {"merge", "keep_separate"}:
        if source not in labels or target not in labels:
            raise ValueError("both labels must exist in the current deck")
        if source == target:
            raise ValueError("a label cannot be merged with itself")
    if action == "merge":
        canonical = canonical or target
        if len(canonical) > 200:
            raise ValueError("canonical labels are capped at 200 characters")
    if action == "rename" and not canonical:
        raise ValueError("a rename needs a new name")
    return sessions.Action(
        action=action,
        category=category,
        canonical=canonical,
        members=tuple(item for item in (source, target) if item),
        target=target,
        at=datetime.now(UTC).isoformat(),
        uid=uuid.uuid4().hex[:12],
    )


# ------------------------------------------------------------------ committing


def commit(root: Path, review: sessions.Session, actions: list[sessions.Action]) -> int:
    """Append the session's decisions to the log the CLI reads; already-written ones are skipped."""
    log = root / "decisions.jsonl"
    existing = {decision.source_ref for decision in curation.load_decisions(log)}
    written = 0
    for action in actions:
        reference = f"{review.session_id}:{action.uid}"
        if reference in existing:
            continue
        if action.action == "keep_separate":
            decision = curation.Decision(
                category=action.category,
                action="keep_separate",
                canonical=action.canonical,
                members=action.members,
                reviewer=review.reviewer,
                at=datetime.now(UTC).isoformat(),
                note=f"session {review.session_id}",
                source_ref=reference,
            )
        elif action.action == "split":
            decision = curation.Decision(
                category=action.category,
                action="keep_separate",
                members=(action.canonical, action.target),
                reviewer=review.reviewer,
                at=datetime.now(UTC).isoformat(),
                note=f"split in session {review.session_id}",
                source_ref=reference,
            )
        else:
            decision = curation.Decision(
                category=action.category,
                action="merge" if action.action in {"merge", "confirm"} else action.action,
                canonical=action.canonical,
                members=action.members or (action.canonical,),
                reviewer=review.reviewer,
                at=datetime.now(UTC).isoformat(),
                note=f"session {review.session_id}",
                source_ref=reference,
            )
        curation.append_decision(log, decision)
        written += 1
    return written


# ------------------------------------------------------------------ page


def main() -> None:
    st.set_page_config(page_title="EP24 Merge Lab", layout="wide")
    st.title("EP24 Merge Lab")
    st.caption(
        "Legacy label curation · every action is validated here and written to the private "
        "decision log · nothing is published from this page"
    )

    root = curation_root()
    run = latest_run(root)
    review = _session(root)

    with st.sidebar:
        st.subheader("Session")
        st.caption(f"run **{run.name}**")
        st.caption(f"reviewer **{review.reviewer or 'anonymous'}**")
        st.caption(f"revision {review.revision} · {len(review.effective)} actions in effect")
        if st.button("Undo", disabled=not review.can_undo):
            review.undo()
            sessions.save(root, review)
            st.rerun()
        if st.button("Redo", disabled=not review.can_redo):
            review.redo()
            sessions.save(root, review)
            st.rerun()
        if st.button("Commit decisions", type="primary"):
            written = commit(root, review, review.effective)
            st.success(f"{written} new decisions written; the CLI will honour them on the next run.")

    with st.sidebar:
        st.subheader("Queue")
        ordering = st.selectbox("Order by", list(SORTS), index=0, key="queue-order")
        needle = st.text_input("Filter labels", key="queue-filter").strip().casefold()

    tabs = st.tabs([TITLES[category] for category in CATEGORIES])
    for tab, category in zip(tabs, CATEGORIES, strict=True):
        with tab:
            deck = deck_for(run, category)
            actions = [item for item in review.effective if item.category == category]
            cards = apply_actions(deck, actions)
            reviewed = max(0, len(deck) - len(cards))
            total = len(deck)
            if needle:
                cards = [
                    card for card in cards
                    if needle in card["label"].casefold()
                    or any(needle in alias.casefold() for alias in card["aliases"])
                ]
            cards = sorted(cards, key=SORTS[ordering])
            pages = max(1, (len(cards) + PAGE_SIZE - 1) // PAGE_SIZE)
            page = st.number_input(
                f"Page (of {pages})", min_value=1, max_value=pages, value=1, step=1,
                key=f"page-{category}",
            )
            window = cards[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]
            milestone = ""
            if total and reviewed >= total:
                milestone = "Category complete."
            elif total and reviewed and reviewed * 4 >= total * 3:
                milestone = "Three quarters — the long tail is what's left."
            elif total and reviewed * 2 >= total:
                milestone = "Halfway."
            elif total and reviewed * 4 >= total:
                milestone = "First quarter down."
            state = {
                "category": category,
                "cards": window,
                "progress": {"reviewed": reviewed, "total": total},
                "can_undo": review.can_undo,
                "can_redo": review.can_redo,
                "milestone": milestone,
                "message": "Nothing left to review in this category.",
            }
            value = component()(
                state=json.dumps(state),
                key=f"merge-lab-{run.name}-{category}",
                default=None,
                height=880,
            )
            if isinstance(value, dict) and value.get("action"):
                # Streamlit keeps the last component value across reruns, so the same action would
                # be applied again on every later render. One signature, one application.
                signature = f"{category}:{json.dumps(value, sort_keys=True)}"
                if st.session_state.get("last-action") != signature:
                    st.session_state["last-action"] = signature
                    _handle(root, review, category, cards, value)

            if cards:
                st.caption(
                    f"cards {len(window)} of {len(cards)} matching · "
                    f"{reviewed} of {total} labels decided in this category"
                )
            if cards and st.toggle("Show card details", key=f"details-{category}"):
                st.dataframe(
                    [{"label": card["label"], "aliases": ", ".join(card["aliases"]),
                      "occurrences": card["count"], "confidence": round(card["confidence"], 3),
                      "method": card["method"]} for card in cards[:200]],
                    width="stretch", hide_index=True,
                )


def _session(root: Path) -> sessions.Session:
    session_id = os.environ.get("LACLAUGPT_EP24_SESSION", "default")
    reviewer = os.environ.get("LACLAUGPT_EP24_REVIEWER", "")
    path = sessions.session_path(root, session_id)
    if "ep24_session" in st.session_state:
        return st.session_state["ep24_session"]
    run = latest_run(root).name
    if path.exists():
        review = sessions.load(root, session_id)
    else:
        review = sessions.new_session(session_id, run, reviewer)
        sessions.save(root, review)
    st.session_state["ep24_session"] = review
    return review


def _handle(
    root: Path,
    review: sessions.Session,
    category: str,
    cards: list[dict[str, Any]],
    payload: dict[str, Any],
) -> None:
    try:
        action = validate(payload, category, cards)
    except ValueError as exc:
        st.error(f"Refused: {exc}")
        return
    review.add(action)
    sessions.save(root, review)
    st.rerun()


if __name__ == "__main__":
    main()

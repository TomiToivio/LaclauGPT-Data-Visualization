"""Legacy EP24 Merge Lab — gamified researcher curation for label merging (issue #300).

Deliverable 2 of #300: a Streamlit page whose merge interaction is a real JavaScript drag-and-drop
component (``frontend/index.html``), not a graph or a dropdown. Every frontend merge is validated
here, and the researcher's decisions are persisted to the private working area with a revision log.

Run from a checkout that has the private working area beside it:

    LACLAUGPT_LEGACY_DIR=../LaclauGPT-Private/analysis/ep24_legacy_curation \
    streamlit run dashboards/legacy_curation/app.py

The app never writes into a source export and never stores credentials in the browser.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml

# Load the curation module by path, not through the package. Importing the package runs its
# __init__, which pulls in the whole settings/config stack (pydantic-settings and friends) — none of
# which this page needs, and which is not installed on every host that serves a dashboard. Loading
# the one module keeps the lab runnable wherever Streamlit and pandas exist.
_MODULE_PATH = Path(__file__).resolve().parents[2] / "src" / "laclaugpt_visualization" / "legacy_curation.py"
_spec = importlib.util.spec_from_file_location("legacy_curation", _MODULE_PATH)
if _spec is None or _spec.loader is None:  # pragma: no cover - a broken checkout, not a code path
    raise ImportError(f"cannot load the curation module from {_MODULE_PATH}")
_legacy = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _legacy  # dataclasses resolves cls.__module__ through sys.modules
_spec.loader.exec_module(_legacy)

CATEGORIES = _legacy.CATEGORIES
build_cards = _legacy.cards
curate = _legacy.curate
read_labels = _legacy.read_labels

WORK_DIR = Path(os.environ.get("LACLAUGPT_LEGACY_DIR", "analysis/ep24_legacy_curation"))
DECISIONS = WORK_DIR / "decisions.json"
HISTORY = WORK_DIR / "decisions_history.jsonl"
COMPONENT_DIR = Path(__file__).resolve().parent / "frontend"

CATEGORY_LABELS = {
    "persons": ("Persons", "One person, one card: titles and bare surnames fold only when unambiguous."),
    "entities": ("Entities", "Institutions, countries, organisations."),
    "themes": ("Themes", "Equivalent wording only — relatedness is not sameness."),
    "topics": ("Topics", "Equivalent wording only."),
    "sentiments": ("Sentiments", "One polarity per card; opposites are never merged."),
}


def _login_gate() -> bool:
    """Opt-in authentication: set LACLAUGPT_AUTH_YAML to a streamlit-authenticator config.

    The lab reads research records, so serving it on a public port without a gate would publish
    them. Auth is opt-in because the same app is run locally with no auth at all.
    """
    auth_yaml = os.environ.get("LACLAUGPT_AUTH_YAML")
    if not auth_yaml:
        return True

    config_path = Path(auth_yaml)
    if not config_path.exists():
        st.error(f"LACLAUGPT_AUTH_YAML points at a missing file: {config_path}")
        return False

    import streamlit_authenticator as stauth

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    authenticator = stauth.Authenticate(
        config["credentials"],
        config["cookie"]["name"],
        config["cookie"]["key"],
        config["cookie"]["expiry_days"],
    )
    try:
        authenticator.login()
    except Exception as exc:  # noqa: BLE001 — the authenticator raises its own types on bad config;
        # surfacing the message beats a stack trace in the browser.
        st.error(exc)

    status = st.session_state.get("authentication_status")
    if status:
        authenticator.logout("Logout", "sidebar")
        return True
    if status is False:
        st.error("Username/password is incorrect")
    else:
        st.warning("Please enter your username and password")
    return False


def _component():
    return st.components.v1.declare_component("legacy_merge_board", path=str(COMPONENT_DIR))


def _load_decisions() -> dict:
    if DECISIONS.exists():
        return json.loads(DECISIONS.read_text(encoding="utf-8"))
    return {"merge": {}, "keep_separate": []}


def _save_decisions(decisions: dict, action: dict) -> None:
    """Persist decisions and append a revision record, so concurrent sessions can be reconciled."""
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    DECISIONS.write_text(json.dumps(decisions, indent=2, sort_keys=True), encoding="utf-8")
    record = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "action": action}
    with HISTORY.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _validate(action: dict, cards: list[dict]) -> tuple[bool, str]:
    """Backend validation: never trust the browser's ids."""
    known = {card["id"] for card in cards}
    ids = [item for item in (action.get("ids") or []) if item in known]
    if action.get("action") in {"confirm", "keep_separate", "propose"} and len(ids) < 1:
        return False, "no known card selected"
    if len(ids) > 40:
        return False, "too many cards in one decision"
    return True, ""


def main() -> None:
    st.set_page_config(page_title="Legacy EP24 Merge Lab", page_icon=":jigsaw:", layout="wide")
    if not _login_gate():
        return
    st.title("Legacy EP24 Merge Lab")
    st.caption(
        "Automatically proposed merges, reviewed by drag and drop. Decisions are saved to the private "
        f"working area: `{WORK_DIR}`. The source export is never modified."
    )

    source = st.sidebar.text_input("Source export (CSV/JSON, read-only)", value=str(WORK_DIR / "source.csv"))
    if not Path(source).exists():
        st.info(
            "Point the sidebar at the legacy export, or run the automatic pass first:\n\n"
            "`python tools/legacy_curate.py --source export.csv --out analysis/ep24_legacy_curation`"
        )
        return

    labelled = {category: read_labels(Path(source), category) for category in CATEGORIES}
    labelled = {category: counts for category, counts in labelled.items() if counts}
    decisions = _load_decisions()
    result = curate(labelled, decisions=decisions)

    stats = result["stats"]
    c1, c2, c3 = st.columns(3)
    c1.metric("Labels reviewed by rule", sum(item["labels"] for item in stats.values()))
    c2.metric("Merges applied", sum(item["auto_merges"] for item in stats.values()))
    c3.metric(
        "Still to review",
        sum(item["review_candidates"] for item in stats.values()) + len(decisions.get("keep_separate", [])),
    )

    component = _component()
    tabs = st.tabs([CATEGORY_LABELS[category][0] for category in CATEGORIES])
    for tab, category in zip(tabs, CATEGORIES):
        with tab:
            st.caption(CATEGORY_LABELS[category][1])
            counts = labelled.get(category, {})
            if not counts:
                st.info("No labels for this category in the source.")
                continue
            cards = build_cards(category, counts, result)
            loose = sum(1 for card in cards if card["status"] == "unresolved")
            if loose:
                st.caption(
                    f"Showing {loose} unmerged labels of {len(counts)} by frequency, plus every "
                    "proposed and confirmed cluster. Merged labels are no longer listed individually."
                )
            action = component(
                cards=cards,
                category=category,
                reviewed=len(decisions.get("keep_separate", [])) + len(decisions.get("merge", {})),
                total=max(1, len(cards)),
                key=f"board-{category}",
                default=None,
            )
            if not action:
                continue

            ok, error = _validate(action, cards)
            if not ok:
                st.error(f"Rejected: {error}")
                continue

            labels = [next(card["label"] for card in cards if card["id"] == card_id) for card_id in action["ids"]]
            if action["action"] == "confirm":
                canonical = labels[0]
                for alias in labels[1:]:
                    decisions.setdefault("merge", {})[alias] = canonical
                _save_decisions(decisions, {"confirm": labels, "category": category})
                st.success(f"Merged into **{canonical}** — saved.")
            elif action["action"] == "keep_separate":
                decisions.setdefault("keep_separate", []).extend(
                    label for label in labels if label not in decisions["keep_separate"]
                )
                _save_decisions(decisions, {"keep_separate": labels, "category": category})
                st.info("Kept separate — saved.")
            elif action["action"] == "propose":
                st.session_state["pending_preview"] = labels
                st.warning(f"Proposed merge: {' + '.join(labels)} — press Confirm merge in the board to apply.")
            else:
                st.toast("Undone in the board; nothing was saved.")

            preview = st.session_state.get("pending_preview")
            if preview:
                affected = sum(counts.get(label, 0) for label in preview)
                st.markdown(
                    f"**Preview:** {len(preview)} labels, {affected} occurrences would count as "
                    f"`{preview[0]}`. The export changes only when you act."
                )

            with st.expander("Affected labels"):
                st.dataframe(
                    pd.DataFrame(
                        [{"label": label, "mentions": counts.get(label, 0)} for label in preview or []]
                    ),
                    hide_index=True,
                    use_container_width=True,
                )

    st.sidebar.markdown("---")
    st.sidebar.json(decisions, expanded=False)


main()

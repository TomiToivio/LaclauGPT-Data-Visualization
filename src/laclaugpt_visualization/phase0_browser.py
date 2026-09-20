"""Opt-in read-only Phase 0 browser list and one-document inspection view.

This module deliberately sits at the Visualization boundary. It does not reinterpret
analysis, mutate records, or connect to MongoDB at import time.
"""
from __future__ import annotations

import os
from copy import deepcopy
from typing import Any

import streamlit as st

from .config import get_settings
from .phase0_adapter import adapt_phase0

_FLAG = "LACLAUGPT_VIS_PHASE0_BROWSER_ENABLED"
_STAGE_ORDER = ("preprocess", "summary", "postprocess", "discourse")


def browser_enabled(environ: dict[str, str] | None = None) -> bool:
    """Return whether the isolated Phase 0 browser is explicitly enabled."""
    values = os.environ if environ is None else environ
    return values.get(_FLAG, "").strip().casefold() in {"1", "true", "yes", "on"}


def phase0_collection_name(project_id: str) -> str:
    """Return the preserved Phase 0 collection name without Phase 1 migration."""
    return f"laclaugpt2_{project_id}_scraper_collection"


def _collection():
    settings = get_settings()
    if not settings.mongodb_uri:
        raise RuntimeError(
            "Phase 0 browser requires LACLAUGPT_VIS_MONGODB_URI; "
            "the feature is read-only and does not fall back to another schema."
        )
    try:
        from pymongo import MongoClient
    except ImportError as exc:
        raise RuntimeError(
            "Install laclaugpt-data-visualization[remote] for the Phase 0 browser."
        ) from exc
    client = MongoClient(
        settings.mongodb_uri,
        serverSelectionTimeoutMS=settings.mongodb_connect_timeout_ms,
        connectTimeoutMS=settings.mongodb_connect_timeout_ms,
        appname="laclaugpt-phase0-browser",
    )
    return client, client[settings.mongodb_database][phase0_collection_name(settings.project_id)]


def list_phase0_documents(limit: int = 50) -> list[dict[str, Any]]:
    """Read a bounded newest-first Phase 0 list without mutating source documents."""
    if limit < 1 or limit > 500:
        raise ValueError("limit must be between 1 and 500")
    client, collection = _collection()
    try:
        return list(
            collection.find({}, {"_id": False})
            .sort("source_date", -1)
            .limit(limit)
        )
    finally:
        client.close()


def find_phase0_document(source_url: str) -> dict[str, Any] | None:
    """Resolve exactly one Phase 0 document by canonical source_url identity."""
    client, collection = _collection()
    try:
        return collection.find_one({"source_url": source_url}, {"_id": False})
    finally:
        client.close()


def inspection_payload(document: dict[str, Any] | None) -> dict[str, Any] | None:
    """Build a read-only inspection payload aligned with Phase 0 inspect semantics."""
    if document is None:
        return None
    source = deepcopy(document)
    adapted = adapt_phase0(source)
    raw = adapted["phase0_compatibility"]["raw_phase0"]
    discourse = raw.get("phase0_discourse")
    discourse = discourse if isinstance(discourse, dict) else {}

    candidates = {
        key: deepcopy(discourse.get(key, []))
        for key in (
            "signifiers",
            "articulations",
            "demands",
            "chains_equivalence",
            "chains_difference",
            "collective_subjects",
            "frontiers",
            "affects",
            "nodal_point_candidates",
            "floating_signifier_candidates",
            "empty_signifier_candidates",
            "future_vision_candidates",
            "formation_evidence",
            "counter_evidence",
            "uncertainty_notes",
        )
        if key in discourse
    }
    errors: dict[str, Any] = {}
    for stage in _STAGE_ORDER:
        snapshot = adapted["phase0_stage_status"][stage]
        if str(snapshot.get("status", "")).casefold() == "error":
            errors[stage] = deepcopy(snapshot.get("error"))
    if raw.get("phase0_summary_validation_error"):
        errors["summary_validation"] = raw["phase0_summary_validation_error"]
    discourse_meta = raw.get("phase0_discourse_error_metadata")
    if discourse_meta:
        errors["discourse_validation"] = deepcopy(discourse_meta)

    raw_debug = {
        key: deepcopy(raw[key])
        for key in (
            "phase0_summary_raw",
            "phase0_discourse_raw",
            "phase0_summary_error_metadata",
            "phase0_discourse_error_metadata",
        )
        if key in raw
    }
    return {
        "source_url": adapted["source_url"],
        "document_id": adapted["document_id"],
        "title": adapted["content_title"],
        "summary": adapted["summary"],
        "analysis_status": adapted["analysis_status"],
        "stage_status": deepcopy(adapted["phase0_stage_status"]),
        "candidate_semantics": "candidate / provisional",
        "discourse_candidates": candidates,
        "validation_errors": errors,
        "raw_debug": raw_debug,
    }


def _list_rows(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for document in documents:
        adapted = adapt_phase0(document)
        rows.append(
            {
                "source_url": adapted["source_url"],
                "title": adapted["content_title"],
                "author": adapted["source_author"],
                "source_date": adapted["source_timestamp"],
                "analysis_status": adapted["analysis_status"],
            }
        )
    return rows


def run() -> None:
    """Run the isolated, opt-in Phase 0 browser."""
    st.set_page_config(page_title="LaclauGPT Phase 0 Browser", layout="wide")
    st.title("LaclauGPT Phase 0 Browser")
    st.caption(
        "Read-only compatibility view. Candidate/provisional labels are not validated "
        "theoretical conclusions."
    )
    if not browser_enabled():
        st.info(
            f"Phase 0 browser is disabled by default. Set {_FLAG}=true to enable this route."
        )
        return

    limit = int(st.sidebar.number_input("Maximum records", min_value=1, max_value=500, value=50))
    try:
        documents = list_phase0_documents(limit=limit)
    except (RuntimeError, ValueError, OSError) as exc:
        st.error(str(exc))
        return
    if not documents:
        st.info("No Phase 0 records found.")
        return

    rows = _list_rows(documents)
    st.dataframe(rows, use_container_width=True, hide_index=True)
    options = [row["source_url"] for row in rows if row["source_url"]]
    if not options:
        st.warning("Records were returned but no canonical source_url identity is available.")
        return

    selected = st.selectbox("Inspect source_url", options)
    document = next((item for item in documents if item.get("source_url") == selected), None)
    if document is None:
        document = find_phase0_document(selected)
    payload = inspection_payload(document)
    if payload is None:
        st.error("Document not found for the selected source_url.")
        return

    st.markdown("### Summary")
    st.write(payload["summary"] or "No validated/fallback summary is present.")

    st.markdown("### Stage status")
    st.json(payload["stage_status"])

    st.markdown("### Discourse candidates")
    st.caption("All labels in this section are candidate / provisional.")
    if payload["discourse_candidates"]:
        st.json(payload["discourse_candidates"])
    else:
        st.caption("No discourse candidates are present yet.")

    if payload["validation_errors"]:
        st.markdown("### Validation errors")
        st.json(payload["validation_errors"])

    if payload["raw_debug"]:
        with st.expander("Raw debugging responses"):
            st.json(payload["raw_debug"])


if __name__ == "__main__":
    run()

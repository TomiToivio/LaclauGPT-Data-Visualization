"""Opt-in, read-only browser for bounded Phase 0 record lists and inspection.

This module deliberately keeps the Phase 0 MongoDB contract separate from the
canonical Phase 1 storage path. Importing it never imports or connects to
MongoDB; the optional driver is loaded only when the guarded browser route is
actually used.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Literal

from .config import Settings
from .phase0_adapter import adapt_phase0, looks_like_phase0

PHASE0_BROWSER_MAX_LIMIT = 200
BrowserStatus = Literal["loading", "ready", "empty", "error", "config-error"]
_STAGE_ORDER = ("preprocess", "summary", "postprocess", "discourse")


class Phase0BrowserConfigurationError(ValueError):
    """Raised when the opt-in browser is enabled without its explicit contract."""


@dataclass(frozen=True)
class Phase0BrowserState:
    """Small UI-neutral state model for deterministic browser rendering/tests."""

    status: BrowserStatus
    rows: tuple[dict[str, Any], ...] = ()
    message: str = ""


def phase0_collection_name(project_id: str) -> str:
    """Return the collection name owned by the Phase 0 Analysis/Collection contract."""
    clean = project_id.strip()
    if not clean:
        raise Phase0BrowserConfigurationError("Phase 0 browser requires a project id.")
    return f"laclaugpt2_{clean}_scraper_collection"


def validate_phase0_browser_settings(settings: Settings) -> None:
    """Validate only the opt-in route without changing global Phase 0/Phase 1 startup."""
    if not settings.phase0_browser_enabled:
        return
    if not settings.phase0_mongodb_uri:
        raise Phase0BrowserConfigurationError(
            "Phase 0 browser requires LACLAUGPT_MONGODB_URI "
            "(or LACLAUGPT_VIS_PHASE0_MONGODB_URI)."
        )
    phase0_collection_name(settings.resolved_phase0_project_id)
    if not 1 <= settings.phase0_browser_limit <= PHASE0_BROWSER_MAX_LIMIT:
        raise Phase0BrowserConfigurationError(
            f"Phase 0 browser limit must be between 1 and {PHASE0_BROWSER_MAX_LIMIT}."
        )


def _browser_rows(records: list[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    """Project adapted records to the bounded list surface only."""
    rows: list[dict[str, Any]] = []
    for record in records:
        summary = str(record.get("summary") or "")
        rows.append(
            {
                "source_url": str(record.get("source_url") or ""),
                "source_date": record.get("source_timestamp") or "",
                "actor": str(record.get("source_author") or ""),
                "language": str(record.get("source_language") or ""),
                "title": str(record.get("content_title") or ""),
                "analysis_status": str(record.get("analysis_status") or ""),
                "summary": summary[:240],
            }
        )
    return tuple(rows)


def _client_factory_or_default(client_factory: Callable[..., Any] | None) -> Callable[..., Any]:
    if client_factory is not None:
        return client_factory
    try:
        from pymongo import MongoClient
    except ImportError as exc:
        raise RuntimeError(
            "Phase 0 browser requires the optional MongoDB dependency; "
            "install laclaugpt-data-visualization[remote]."
        ) from exc
    return MongoClient


def load_phase0_browser_records(
    settings: Settings,
    *,
    client_factory: Callable[..., Any] | None = None,
) -> list[dict[str, Any]]:
    """Read a bounded Phase 0 list and adapt it without mutating source documents."""
    validate_phase0_browser_settings(settings)
    factory = _client_factory_or_default(client_factory)
    client = factory(
        settings.phase0_mongodb_uri,
        serverSelectionTimeoutMS=settings.mongodb_connect_timeout_ms,
        connectTimeoutMS=settings.mongodb_connect_timeout_ms,
        appname="laclaugpt-phase0-browser",
        connect=False,
    )
    try:
        collection = client[settings.phase0_mongodb_database][
            phase0_collection_name(settings.resolved_phase0_project_id)
        ]
        cursor = (
            collection.find({}, {"_id": False})
            .sort([("source_date", -1), ("source_url", 1)])
            .limit(settings.phase0_browser_limit)
        )
        return [adapt_phase0(record) for record in cursor if looks_like_phase0(record)]
    except (ConnectionError, OSError, TimeoutError) as exc:
        raise RuntimeError("Configured Phase 0 MongoDB is unavailable.") from exc
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()


def find_phase0_document(
    settings: Settings,
    source_url: str,
    *,
    client_factory: Callable[..., Any] | None = None,
) -> dict[str, Any] | None:
    """Resolve one raw Phase 0 record by immutable source_url identity."""
    validate_phase0_browser_settings(settings)
    if not source_url:
        return None
    factory = _client_factory_or_default(client_factory)
    client = factory(
        settings.phase0_mongodb_uri,
        serverSelectionTimeoutMS=settings.mongodb_connect_timeout_ms,
        connectTimeoutMS=settings.mongodb_connect_timeout_ms,
        appname="laclaugpt-phase0-browser",
        connect=False,
    )
    try:
        collection = client[settings.phase0_mongodb_database][
            phase0_collection_name(settings.resolved_phase0_project_id)
        ]
        document = collection.find_one({"source_url": source_url}, {"_id": False})
        return document if isinstance(document, dict) and looks_like_phase0(document) else None
    except (ConnectionError, OSError, TimeoutError) as exc:
        raise RuntimeError("Configured Phase 0 MongoDB is unavailable.") from exc
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()


def inspection_payload(document: dict[str, Any] | None) -> dict[str, Any] | None:
    """Build a read-only inspection payload without reinterpreting analysis."""
    if document is None:
        return None
    if "phase0_compatibility" in document:
        adapted = deepcopy(document)
    else:
        adapted = adapt_phase0(deepcopy(document))
    compatibility = adapted.get("phase0_compatibility")
    compatibility = compatibility if isinstance(compatibility, dict) else {}
    raw = compatibility.get("raw_phase0")
    raw = raw if isinstance(raw, dict) else {}
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
    stage_status = adapted.get("phase0_stage_status")
    stage_status = stage_status if isinstance(stage_status, dict) else {}
    errors: dict[str, Any] = {}
    for stage in _STAGE_ORDER:
        snapshot = stage_status.get(stage)
        snapshot = snapshot if isinstance(snapshot, dict) else {}
        if str(snapshot.get("status", "")).casefold() == "error":
            errors[stage] = deepcopy(snapshot.get("error"))
    if raw.get("phase0_summary_validation_error"):
        errors["summary_validation"] = deepcopy(raw["phase0_summary_validation_error"])
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
        "source_url": str(adapted.get("source_url") or ""),
        "document_id": str(adapted.get("document_id") or ""),
        "title": str(adapted.get("content_title") or ""),
        "summary": str(adapted.get("summary") or ""),
        "analysis_status": str(adapted.get("analysis_status") or ""),
        "stage_status": deepcopy(stage_status),
        "candidate_semantics": "candidate / provisional",
        "discourse_candidates": candidates,
        "validation_errors": errors,
        "raw_debug": raw_debug,
    }


def phase0_browser_state(
    settings: Settings,
    *,
    loader: Callable[[Settings], list[dict[str, Any]]] = load_phase0_browser_records,
) -> Phase0BrowserState:
    """Resolve explicit configuration, empty, ready and runtime error states."""
    try:
        validate_phase0_browser_settings(settings)
    except Phase0BrowserConfigurationError as exc:
        return Phase0BrowserState("config-error", message=str(exc))
    try:
        records = loader(settings)
    except Exception as exc:  # UI boundary: turn backend failure into an explicit state.
        return Phase0BrowserState("error", message=str(exc))
    if not records:
        return Phase0BrowserState(
            "empty",
            message="No Phase 0 records are available in the configured project collection.",
        )
    return Phase0BrowserState("ready", rows=_browser_rows(records))


def render_phase0_browser(ui: Any, settings: Settings) -> None:
    """Render the guarded list plus source_url-keyed read-only inspection."""
    ui.markdown("### Phase 0 browser")
    ui.caption(
        "Read-only bounded list through the Phase 0 compatibility adapter. "
        "source_url remains the record identity; discourse labels remain candidate / provisional."
    )
    with ui.spinner("Loading bounded Phase 0 record list…"):
        state = phase0_browser_state(settings)

    if state.status == "config-error":
        ui.error(state.message)
        return
    if state.status == "error":
        ui.error(f"Phase 0 browser could not load records: {state.message}")
        return
    if state.status == "empty":
        ui.info(state.message)
        return

    rows = list(state.rows)
    ui.caption(
        f"Showing at most {settings.phase0_browser_limit} records from "
        f"{phase0_collection_name(settings.resolved_phase0_project_id)}."
    )
    ui.dataframe(rows, use_container_width=True, hide_index=True)

    options = [str(row.get("source_url") or "") for row in rows if row.get("source_url")]
    if not options or not hasattr(ui, "selectbox"):
        return
    selected = ui.selectbox("Inspect source_url", options)
    if not selected:
        return
    try:
        document = find_phase0_document(settings, str(selected))
    except Exception as exc:
        ui.error(f"Phase 0 document could not be loaded: {exc}")
        return
    payload = inspection_payload(document)
    if payload is None:
        ui.error("Document not found for the selected source_url.")
        return

    ui.markdown("#### Summary")
    if hasattr(ui, "write"):
        ui.write(payload["summary"] or "No validated/fallback summary is present.")
    ui.markdown("#### Stage status")
    if hasattr(ui, "json"):
        ui.json(payload["stage_status"])
    ui.markdown("#### Discourse candidates")
    ui.caption("All labels in this section are candidate / provisional.")
    if hasattr(ui, "json"):
        if payload["discourse_candidates"]:
            ui.json(payload["discourse_candidates"])
        elif hasattr(ui, "caption"):
            ui.caption("No discourse candidates are present yet.")
        if payload["validation_errors"]:
            ui.markdown("#### Validation errors")
            ui.json(payload["validation_errors"])
        if payload["raw_debug"]:
            ui.markdown("#### Raw debugging responses")
            ui.json(payload["raw_debug"])

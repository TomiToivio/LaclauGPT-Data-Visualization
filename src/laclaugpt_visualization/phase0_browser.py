"""Opt-in, read-only browser for bounded Phase 0 record lists.

This module deliberately keeps the Phase 0 MongoDB contract separate from the
canonical Phase 1 storage path. Importing it never imports or connects to
MongoDB; the optional driver is loaded only when the guarded browser route is
actually used.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

from .config import Settings
from .phase0_adapter import adapt_phase0, looks_like_phase0

PHASE0_BROWSER_MAX_LIMIT = 200
BrowserStatus = Literal["loading", "ready", "empty", "error", "config-error"]


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


def load_phase0_browser_records(
    settings: Settings,
    *,
    client_factory: Callable[..., Any] | None = None,
) -> list[dict[str, Any]]:
    """Read a bounded Phase 0 list and adapt it without mutating source documents."""
    validate_phase0_browser_settings(settings)

    if client_factory is None:
        try:
            from pymongo import MongoClient
        except ImportError as exc:
            raise RuntimeError(
                "Phase 0 browser requires the optional MongoDB dependency; "
                "install laclaugpt-data-visualization[remote]."
            ) from exc
        client_factory = MongoClient

    client = client_factory(
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
    """Render the single guarded list route. No inspect/review/monitor behavior lives here."""
    ui.markdown("### Phase 0 browser")
    ui.caption(
        "Read-only bounded list through the Phase 0 compatibility adapter. "
        "source_url remains the record identity."
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

    ui.caption(
        f"Showing at most {settings.phase0_browser_limit} records from "
        f"{phase0_collection_name(settings.resolved_phase0_project_id)}."
    )
    ui.dataframe(list(state.rows), use_container_width=True, hide_index=True)

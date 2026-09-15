"""Auditable Hermes operations built on the normal Visualization code paths."""
from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..config import Settings
from ..data import load_frame
from ..service import readiness, streamlit_command

CALLER = "hermes-agent"


def inspect_effective_config(settings: Settings) -> dict[str, object]:
    """Return non-secret effective configuration."""
    return settings.safe_summary()


def validate_analysis_input(source: str | Path, settings: Settings) -> dict[str, Any]:
    """Load through the canonical loader and report schema/identity health."""
    frame = load_frame(source, settings=settings)
    missing_identity = int(frame["source_url"].eq("").sum())
    versions = sorted({str(value) for value in frame["schema_version"] if str(value)})
    return {
        "records": len(frame),
        "missing_source_url": missing_identity,
        "schema_versions": versions,
        "valid": missing_identity == 0,
    }


def inspect_dataset(source: str | Path, settings: Settings) -> dict[str, Any]:
    """Return bounded metadata useful to an agent without exposing full rows."""
    frame = load_frame(source, settings=settings)
    return {
        "records": len(frame),
        "platforms": sorted(frame["source_platform"].dropna().astype(str).unique().tolist())[:50],
        "countries": sorted(frame["source_country"].dropna().astype(str).unique().tolist())[:50],
        "languages": sorted(frame["source_language"].dropna().astype(str).unique().tolist())[:50],
        "analysis_status": sorted(frame["analysis_status"].dropna().astype(str).unique().tolist())[:50],
    }


def validate_service(settings: Settings) -> dict[str, Any]:
    """Run offline readiness validation; no remote connections are made."""
    result = readiness(settings)
    result["command"] = streamlit_command(settings)
    return result


def export_summary(
    source: str | Path,
    settings: Settings,
    *,
    filename: str = "hermes-summary.json",
    caller: str = CALLER,
) -> Path:
    """Export dataset metadata through the same canonical loader used by humans."""
    settings.ensure_local_directories()
    target = (settings.output_dir / filename).resolve()
    output_root = settings.output_dir.resolve()
    try:
        target.relative_to(output_root)
    except ValueError as exc:
        raise ValueError("export must stay below configured output_dir") from exc
    payload = inspect_dataset(source, settings)
    payload.update(
        {
            "caller": caller,
            "execution": "agent",
            "project_id": settings.project_id,
            "created_at": datetime.now(UTC).isoformat(),
        }
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def request_human_review(
    source_url: str,
    settings: Settings,
    *,
    action: str = "review-requested",
    caller: str = CALLER,
) -> Path:
    """Append an auditable human-review request using canonical source identity."""
    if not source_url.strip():
        raise ValueError("source_url is required for review actions")
    settings.ensure_local_directories()
    log = settings.data_path("runs", "agent-review-actions.jsonl")
    record = {
        "source_url": source_url,
        "action": action,
        "caller": caller,
        "execution": "agent",
        "project_id": settings.project_id,
        "created_at": datetime.now(UTC).isoformat(),
    }
    with log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return log


def clear_derived_cache(settings: Settings) -> dict[str, Any]:
    """Clear only the local derived cache tree; never flush shared Redis implicitly."""
    if settings.cache_backend == "redis":
        return {
            "cleared": False,
            "reason": "shared Redis cache requires an explicit project-scoped maintenance operation",
        }
    cache_dir = settings.data_path("cache")
    removed = 0
    if cache_dir.exists():
        for path in cache_dir.iterdir():
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            removed += 1
    return {"cleared": True, "entries_removed": removed}

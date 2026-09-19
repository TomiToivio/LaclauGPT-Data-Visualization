"""Improved EP24 local bundle loader and storage-neutral research projections.

This module is strictly downstream of Analysis issue #245. It reads the private
CSV/SQLite handoff and produces descriptive view-layer tables only.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .data import explode_labels, normalize_frame

_RECORD_CSV_PRIORITY = ("combined.csv", "finland.csv", "poland.csv")
_SQLITE_TABLE_PRIORITY = ("combined", "records", "annotations")
_COMPANIONS = {
    "legacy_comparison": "legacy_comparison.csv",
    "failures": "failures.csv",
}


@dataclass(frozen=True)
class EP24Bundle:
    """Private EP24 handoff resolved from one local root."""

    root: Path
    records: pd.DataFrame
    legacy_comparison: pd.DataFrame
    failures: pd.DataFrame
    source_path: Path | None
    storage_kind: str


def _candidate_data_dirs(root: Path) -> list[Path]:
    candidates = [root, root / "data"]
    return [path for index, path in enumerate(candidates) if path not in candidates[:index]]


def normalize_ep24_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize nested canonical or improved flat #245 exports losslessly.

    Generic canonical reconstruction interprets a populated schema_version as a signal
    that nested source/content/analysis sections are present. Improved EP24 CSV exports
    may instead be intentionally flat, so suppress that signal only at this boundary and
    restore the exported schema version afterwards.
    """
    if frame.empty:
        return normalize_frame(frame)
    nested_sections = {"source", "content", "analysis"}.intersection(frame.columns)
    if nested_sections:
        return normalize_frame(frame)
    staged = frame.copy()
    schema = staged["schema_version"].copy() if "schema_version" in staged else None
    if schema is not None:
        staged["schema_version"] = ""
    normalized = normalize_frame(staged)
    if schema is not None:
        normalized["schema_version"] = schema.fillna("").astype(str).to_numpy()
    return normalized


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def _load_sqlite_records(path: Path) -> pd.DataFrame:
    with sqlite3.connect(path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        table = next((name for name in _SQLITE_TABLE_PRIORITY if name in tables), None)
        if table is None:
            return pd.DataFrame()
        frame = pd.read_sql_query(f'SELECT * FROM "{table}"', connection)
    return normalize_ep24_frame(frame)


def load_ep24_bundle(root: str | Path | None) -> EP24Bundle:
    """Load #245 outputs without MongoDB/Redis or import-time I/O."""
    resolved = Path(root) if root is not None else Path("data")
    source_path: Path | None = None
    storage_kind = "empty"
    records = pd.DataFrame()

    for data_dir in _candidate_data_dirs(resolved):
        for name in _RECORD_CSV_PRIORITY:
            path = data_dir / name
            if path.exists():
                records = normalize_ep24_frame(pd.read_csv(path))
                source_path = path
                storage_kind = "csv"
                break
        if source_path is not None:
            break

    if source_path is None:
        for data_dir in _candidate_data_dirs(resolved):
            for name in ("ep24.sqlite3", "visualization.sqlite3"):
                path = data_dir / name
                if not path.exists():
                    continue
                records = _load_sqlite_records(path)
                if not records.empty:
                    source_path = path
                    storage_kind = "sqlite"
                    break
            if source_path is not None:
                break

    companions: dict[str, pd.DataFrame] = {}
    for key, filename in _COMPANIONS.items():
        frame = pd.DataFrame()
        for data_dir in _candidate_data_dirs(resolved):
            path = data_dir / filename
            if path.exists():
                frame = _read_csv(path)
                break
        companions[key] = frame

    return EP24Bundle(
        root=resolved,
        records=records,
        legacy_comparison=companions["legacy_comparison"],
        failures=companions["failures"],
        source_path=source_path,
        storage_kind=storage_kind,
    )


def country_counts(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["country", "documents"])
    source = frame.copy()
    country = source.get("source_country", pd.Series("", index=source.index)).fillna("").astype(str)
    legacy_country = source.get("country", pd.Series("", index=source.index)).fillna("").astype(str)
    source["country"] = country.where(country.str.strip().ne(""), legacy_country)
    source["country"] = source["country"].replace("", "unknown")
    return (
        source.groupby("country", dropna=False)["source_url"]
        .nunique()
        .reset_index(name="documents")
        .sort_values(["documents", "country"], ascending=[False, True])
    )


def dimension_counts(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    """Count list/scalar dimensions per country without collapsing country identity."""
    if frame.empty or column not in frame.columns:
        return pd.DataFrame(columns=["country", column, "count"])
    rows: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        country = str(row.get("source_country") or row.get("country") or "unknown")
        value = row.get(column)
        values = value if isinstance(value, list) else [value]
        for item in values:
            if isinstance(item, dict):
                label = str(
                    item.get("label")
                    or item.get("name")
                    or item.get("canonical_id")
                    or item.get("id")
                    or ""
                ).strip()
            else:
                label = str(item or "").strip()
            if label:
                rows.append({"country": country, column: label})
    if not rows:
        return pd.DataFrame(columns=["country", column, "count"])
    return (
        pd.DataFrame(rows)
        .groupby(["country", column], dropna=False)
        .size()
        .reset_index(name="count")
        .sort_values(["country", "count", column], ascending=[True, False, True])
    )


def overview(frame: pd.DataFrame, failures: pd.DataFrame | None = None) -> dict[str, Any]:
    countries = country_counts(frame)
    return {
        "documents": int(frame["source_url"].nunique()) if "source_url" in frame else len(frame),
        "finland": int(
            countries.loc[countries["country"].str.casefold().eq("finland"), "documents"].sum()
        )
        if not countries.empty
        else 0,
        "poland": int(
            countries.loc[countries["country"].str.casefold().eq("poland"), "documents"].sum()
        )
        if not countries.empty
        else 0,
        "analyzed": int(frame["analysis_status"].astype(str).str.casefold().eq("analyzed").sum())
        if "analysis_status" in frame
        else 0,
        "failures": 0 if failures is None else len(failures),
        "codebook_refs": int(explode_labels(frame, "codebook_refs")["count"].sum())
        if "codebook_refs" in frame and not frame.empty
        else 0,
    }


def legacy_change_summary(comparison: pd.DataFrame) -> pd.DataFrame:
    """Return a descriptive summary of exported legacy-vs-new comparisons."""
    if comparison.empty:
        return pd.DataFrame(columns=["change", "count"])
    for column in ("change", "change_type", "status", "difference_type"):
        if column in comparison.columns:
            values = comparison[column].fillna("unknown").astype(str)
            return values.value_counts().rename_axis("change").reset_index(name="count")
    return pd.DataFrame([{"change": "rows_for_researcher_inspection", "count": len(comparison)}])


def qa_summary(frame: pd.DataFrame, failures: pd.DataFrame | None = None) -> pd.DataFrame:
    """Small inspectable QA table. Missing data is reported, never inferred."""
    rows: list[dict[str, Any]] = []
    rows.append({"metric": "records", "value": len(frame)})
    if "source_url" in frame:
        rows.append({"metric": "missing_source_url", "value": int(frame["source_url"].eq("").sum())})
        rows.append(
            {
                "metric": "duplicate_source_url_rows",
                "value": int(frame["source_url"].duplicated(keep=False).sum()),
            }
        )
    if "analysis_status" in frame:
        analyzed = frame["analysis_status"].astype(str).str.casefold().eq("analyzed")
        rows.append({"metric": "not_analyzed", "value": int((~analyzed).sum())})
    if "uncertainties" in frame:
        rows.append(
            {
                "metric": "records_with_uncertainty",
                "value": int(frame["uncertainties"].map(bool).sum()),
            }
        )
    rows.append({"metric": "failure_rows", "value": 0 if failures is None else len(failures)})
    return pd.DataFrame(rows)

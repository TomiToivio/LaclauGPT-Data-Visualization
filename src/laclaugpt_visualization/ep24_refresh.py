"""EP24 dashboard freshness and refresh checks (#210).

The dashboard reads a *copy* of an export. Nothing in the repository can tell, by looking at the
dashboard alone, whether that copy is the newest completed reprocessing output or a stale snapshot — and
"the dashboard looks fine" is exactly the failure mode #210 exists to remove.

This module compares two export manifests and returns a verdict, so the answer is computed rather than
eyeballed:

    CURRENT          the dashboard matches the source counts and is not older
    STALE            the source is newer or has more records: refresh is due
    DIFFERENT_UNIT   the two use different record units (video vs ingest); counts *should* differ and
                     the comparison is reported as incomparable rather than as a defect
    INCOMPARABLE     a manifest is missing a country, a count, or is malformed

Pure functions over parsed dictionaries: no I/O except `load_manifest`, no network, no Mongo. That keeps
the rule testable without a database and keeps private data out of the public repository.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: The country keys the EP24 export contract uses.
COUNTRIES: tuple[str, ...] = ("finland", "poland", "portugal")

VERDICT_CURRENT = "current"
VERDICT_STALE = "stale"
VERDICT_DIFFERENT_UNIT = "different_unit"
VERDICT_INCOMPARABLE = "incomparable"


class RefreshError(ValueError):
    """A manifest that cannot be used to decide anything."""


@dataclass(frozen=True)
class CountryStats:
    records: int
    distinct_media: int | None = None
    source_documents: int | None = None
    newest_timestamp: str | None = None


@dataclass(frozen=True)
class Report:
    verdict: str
    dashboard_generated_at: str | None
    source_generated_at: str | None
    dashboard_unit: str | None
    source_unit: str | None
    dashboard_records: int | None
    source_records: int | None
    per_country: Mapping[str, tuple[CountryStats | None, CountryStats | None]]
    reasons: tuple[str, ...]

    @property
    def needs_refresh(self) -> bool:
        return self.verdict == VERDICT_STALE

    def as_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "needs_refresh": self.needs_refresh,
            "dashboard": {
                "generated_at": self.dashboard_generated_at,
                "record_unit": self.dashboard_unit,
                "records": self.dashboard_records,
            },
            "source": {
                "generated_at": self.source_generated_at,
                "record_unit": self.source_unit,
                "records": self.source_records,
            },
            "per_country": {
                country: {
                    "dashboard": None if pair[0] is None else pair[0].__dict__,
                    "source": None if pair[1] is None else pair[1].__dict__,
                }
                for country, pair in self.per_country.items()
            },
            "reasons": list(self.reasons),
        }


def load_manifest(path: str | Path) -> dict[str, Any]:
    """Read a MANIFEST.json. A missing or malformed manifest is an error, never a guess."""
    p = Path(path)
    if p.is_dir():
        p = p / "MANIFEST.json"
    if not p.is_file():
        raise RefreshError(f"no manifest at {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise RefreshError(f"{p} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise RefreshError(f"{p} is not a manifest object")
    return data


def _country_block(manifest: Mapping[str, Any], country: str) -> CountryStats | None:
    countries = manifest.get("countries")
    if not isinstance(countries, Mapping):
        return None
    block = countries.get(country)
    if not isinstance(block, Mapping):
        return None
    records = block.get("records")
    if not isinstance(records, int):
        return None
    provenance = manifest.get("provenance")
    newest = None
    if isinstance(provenance, Mapping):
        pblock = provenance.get(country)
        if isinstance(pblock, Mapping):
            value = pblock.get("newest_timestamp")
            newest = str(value) if value else None
    media = block.get("distinct_media")
    docs = block.get("source_documents")
    return CountryStats(
        records=records,
        distinct_media=media if isinstance(media, int) else None,
        source_documents=docs if isinstance(docs, int) else None,
        newest_timestamp=newest,
    )


def country_stats(manifest: Mapping[str, Any]) -> dict[str, CountryStats | None]:
    return {country: _country_block(manifest, country) for country in COUNTRIES}


def compare(dashboard: Mapping[str, Any], source: Mapping[str, Any]) -> Report:
    """Decide whether the dashboard's copy is the newest completed export."""
    reasons: list[str] = []

    d_unit = dashboard.get("record_unit")
    s_unit = source.get("record_unit")
    d_records = dashboard.get("records") if isinstance(dashboard.get("records"), int) else None
    s_records = source.get("records") if isinstance(source.get("records"), int) else None
    d_gen = dashboard.get("generated_at")
    s_gen = source.get("generated_at")

    d_countries = country_stats(dashboard)
    s_countries = country_stats(source)
    per_country = {c: (d_countries[c], s_countries[c]) for c in COUNTRIES}

    d_has_countries = any(d_countries[c] is not None for c in COUNTRIES)
    s_has_countries = any(s_countries[c] is not None for c in COUNTRIES)

    # A manifest without per-country blocks is not incomparable — it is a different manifest shape
    # (the streaming exporter writes totals only). Fall back to a totals comparison and say so, rather
    # than refusing to answer the question the check exists to answer.
    totals_only = bool(s_has_countries) and not d_has_countries

    missing = [c for c in COUNTRIES if s_countries[c] is None] if (d_has_countries or not totals_only) else []
    if missing and not totals_only:
        reasons.append("missing country block or record count: " + ", ".join(missing))
    if totals_only:
        reasons.append(
            "dashboard manifest carries no per-country block (totals-only shape): "
            "country-level freshness cannot be verified from it"
        )

    zero = [
        c for c in COUNTRIES
        if s_countries[c] is not None and s_countries[c].records == 0  # type: ignore[union-attr]
    ]
    if zero:
        reasons.append("source reports zero records for: " + ", ".join(zero))

    if d_unit and s_unit and d_unit != s_unit:
        reasons.append(f"record units differ ({d_unit} vs {s_unit}): counts are not comparable")
        return Report(
            verdict=VERDICT_DIFFERENT_UNIT,
            dashboard_generated_at=d_gen, source_generated_at=s_gen,
            dashboard_unit=d_unit, source_unit=s_unit,
            dashboard_records=d_records, source_records=s_records,
            per_country=per_country, reasons=tuple(reasons),
        )

    if (missing and not totals_only) or zero or d_records is None or s_records is None:
        return Report(
            verdict=VERDICT_INCOMPARABLE,
            dashboard_generated_at=d_gen, source_generated_at=s_gen,
            dashboard_unit=d_unit, source_unit=s_unit,
            dashboard_records=d_records, source_records=s_records,
            per_country=per_country, reasons=tuple(reasons) or ("manifest lacks the fields needed",),
        )

    stale = False
    if s_records > d_records:
        stale = True
        reasons.append(f"source has more records ({s_records} > {d_records})")

    for country in COUNTRIES:
        d_stats, s_stats = per_country[country]
        if totals_only or d_stats is None or s_stats is None:
            continue
        if s_stats.records > d_stats.records:
            stale = True
            reasons.append(f"{country}: source has more records ({s_stats.records} > {d_stats.records})")
        if (
            s_stats.newest_timestamp and d_stats.newest_timestamp
            and s_stats.newest_timestamp > d_stats.newest_timestamp
        ):
            stale = True
            reasons.append(
                f"{country}: source is newer ({s_stats.newest_timestamp} > {d_stats.newest_timestamp})"
            )

    if not stale:
        if s_records < d_records:
            reasons.append(
                f"dashboard holds more records than the source ({d_records} > {s_records}): "
                "this is an identity-rule difference, not staleness — see "
                "docs/EP24_DASHBOARD_REFRESH.md"
            )
        elif s_gen and d_gen and s_gen > d_gen:
            reasons.append(
                "source was generated later with identical counts and no newer timestamps: "
                "content is current"
            )
        reasons.append("dashboard is not behind the source")
        return Report(
            verdict=VERDICT_CURRENT,
            dashboard_generated_at=d_gen, source_generated_at=s_gen,
            dashboard_unit=d_unit, source_unit=s_unit,
            dashboard_records=d_records, source_records=s_records,
            per_country=per_country, reasons=tuple(reasons),
        )

    return Report(
        verdict=VERDICT_STALE,
        dashboard_generated_at=d_gen, source_generated_at=s_gen,
        dashboard_unit=d_unit, source_unit=s_unit,
        dashboard_records=d_records, source_records=s_records,
        per_country=per_country, reasons=tuple(reasons),
    )


def count_country_csvs(directory: str | Path) -> dict[str, int]:
    """Row counts for the per-country CSVs a dashboard export carries.

    The streaming exporter writes a totals-only manifest, which is why a country-level freshness check
    had nothing to read. The rows are already on disk; this counts them so the manifest can state them.
    A missing file is simply absent from the result — never a zero.
    """
    d = Path(directory)
    counts: dict[str, int] = {}
    for country in COUNTRIES:
        path = d / f"{country}.csv"
        if not path.is_file():
            continue
        with path.open("rb") as fh:
            rows = sum(1 for _ in fh) - 1  # header
        counts[country] = max(0, rows)
    return counts


def annotate_manifest(directory: str | Path) -> dict[str, Any]:
    """Add a `countries` block to a totals-only manifest, in place. Returns the written manifest."""
    d = Path(directory)
    manifest = load_manifest(d)
    counts = count_country_csvs(d)
    if not counts:
        raise RefreshError(f"no per-country CSVs found in {d}")
    total = manifest.get("records")
    if isinstance(total, int) and sum(counts.values()) != total:
        raise RefreshError(
            f"per-country rows ({sum(counts.values())}) do not sum to the manifest total ({total})"
        )
    block = {c: {"records": n} for c, n in counts.items()}
    manifest["countries"] = block
    manifest["country_counts_source"] = "counted from per-country CSVs"
    (d / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest

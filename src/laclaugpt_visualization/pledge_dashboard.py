"""Opt-in Phase 1 Pledge dashboard over the shared canonical dataframe contract."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True, slots=True)
class PledgeSnapshot:
    state: str
    records: tuple[dict[str, Any], ...] = ()
    alignment_counts: tuple[tuple[str, int], ...] = ()
    country_counts: tuple[tuple[str, int], ...] = ()
    topic_counts: tuple[tuple[str, int], ...] = ()
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "records": list(self.records),
            "alignment_counts": dict(self.alignment_counts),
            "country_counts": dict(self.country_counts),
            "topic_counts": dict(self.topic_counts),
            "error": self.error,
        }


def _first(row: pd.Series, *names: str) -> Any:
    for name in names:
        if name not in row:
            continue
        value = row.get(name)
        if value is None:
            continue
        if isinstance(value, float) and pd.isna(value):
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return ""


def _topics(value: Any) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(sorted({str(item).strip() for item in value if str(item).strip()}))
    if isinstance(value, str):
        return tuple(sorted({part.strip() for part in value.replace(",", ";").split(";") if part.strip()}))
    return ()


def build_pledge_snapshot(frame: pd.DataFrame | None) -> PledgeSnapshot:
    """Build a deterministic read-only pledge view without mutating canonical rows."""
    if frame is None:
        return PledgeSnapshot(state="loading")
    if frame.empty:
        return PledgeSnapshot(state="empty")
    if "source_url" not in frame.columns:
        return PledgeSnapshot(state="error", error="canonical source_url field is required")

    records: list[dict[str, Any]] = []
    alignments: Counter[str] = Counter()
    countries: Counter[str] = Counter()
    topics: Counter[str] = Counter()

    for _, row in frame.iterrows():
        source_url = str(row.get("source_url") or "").strip()
        if not source_url:
            return PledgeSnapshot(state="error", error="source_url identity must not be empty")

        observed = _first(row, "political_alignment")
        derived = _first(row, "legacy_derived_alignment")
        if observed:
            alignment = str(observed)
            alignment_status = "observed"
        elif derived:
            alignment = str(derived)
            alignment_status = "legacy_derived"
        else:
            alignment = ""
            alignment_status = "missing"

        country = str(_first(row, "source_country", "country") or "")
        platform = str(_first(row, "source_platform", "source_type") or "")
        date_value = str(_first(row, "source_timestamp", "recording_date") or "")
        grievance = str(_first(row, "grievance", "human_readable_summary", "summary") or "")
        row_topics = _topics(_first(row, "topics", "topics_legacy", "new_theme"))

        record = {
            "source_url": source_url,
            "date": date_value[:10],
            "country": country,
            "platform": platform,
            "grievance": grievance,
            "political_alignment": alignment,
            "alignment_observation_status": alignment_status,
            "topics": list(row_topics),
        }
        records.append(record)
        alignments[alignment_status] += 1
        if country:
            countries[country] += 1
        topics.update(row_topics)

    records.sort(key=lambda item: (item["date"], item["source_url"]))
    return PledgeSnapshot(
        state="ready",
        records=tuple(records),
        alignment_counts=tuple(sorted(alignments.items())),
        country_counts=tuple(sorted(countries.items())),
        topic_counts=tuple(sorted(topics.items())),
    )


def render_pledge_dashboard(st: Any, frame: pd.DataFrame | None) -> None:
    """Render the restored dashboard using only the shared canonical dataframe projection."""
    snapshot = build_pledge_snapshot(frame)
    st.markdown("#### Pledge Dashboard")
    st.caption(
        "Opt-in Phase 1 specialized view. It preserves source_url identity and only displays "
        "observed or explicitly legacy-derived political metadata."
    )
    if snapshot.state == "loading":
        st.info("Pledge dashboard data is loading.")
        return
    if snapshot.state == "empty":
        st.info("No records are available for the Pledge dashboard.")
        return
    if snapshot.state == "error":
        st.error(snapshot.error)
        return

    counts = dict(snapshot.alignment_counts)
    metrics = st.columns(4)
    metrics[0].metric("Records", len(snapshot.records))
    metrics[1].metric("Observed alignment", counts.get("observed", 0))
    metrics[2].metric("Legacy-derived alignment", counts.get("legacy_derived", 0))
    metrics[3].metric("Missing alignment", counts.get("missing", 0))

    st.markdown("##### Research ledger")
    st.dataframe(list(snapshot.records), use_container_width=True, hide_index=True)

    left, right = st.columns(2)
    with left:
        st.markdown("##### Country coverage")
        st.dataframe(
            [{"country": key, "records": value} for key, value in snapshot.country_counts],
            use_container_width=True,
            hide_index=True,
        )
    with right:
        st.markdown("##### Topic counts")
        st.dataframe(
            [{"topic": key, "records": value} for key, value in snapshot.topic_counts],
            use_container_width=True,
            hide_index=True,
        )

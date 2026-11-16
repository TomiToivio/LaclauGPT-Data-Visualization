"""Safe researcher presentation layer for EP24. Explicit field allowlists only."""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

import pandas as pd

from laclaugpt_visualization.ep24_reprocessed import STAGES, status

# Display columns are deliberately enumerated. No pipeline columns can leak via exports.
DISPLAY = {
    "country": "Country",
    "source_type": "Platform",
    "created_at": "Published",
    "published_at": "Publication date",
    "source_language": "Language",
    "video_id": "Video",
    "source_url": "Source link",
    "source_caption": "Caption",
    "caption": "Caption",
    "asr_transcript": "Transcript",
    "asr_translation": "Translation",
    "ocr_1": "On-screen text",
    "frame_analysis_1": "Frame observations",
    "vllm_video_analysis": "Video observations",
    "summary_analysis": "Multimodal summary",
    "postprocess_summary_md": "Research summary",
    "postprocess_entities": "Entities",
    "postprocess_themes": "Themes",
    "laclau_summary_md": "Laclau analysis",
    "laclau_structured_json": "Discourse coding",
    "dna_statements_json": "DNA statements",
    "sna_analysis_markdown": "SNA interpretation",
}
TABLE_FIELDS = ("country", "source_type", "created_at", "published_at",
                "source_language", "video_id", "source_url", "source_caption",
                "caption", "summary_analysis", "postprocess_summary_md")
COUNTRIES = {"fi": "Finland", "finland": "Finland", "pl": "Poland",
             "poland": "Poland", "pt": "Portugal", "portugal": "Portugal"}
EXPECTED_DATASET = "ep24_monday500_20261031"


def friendly(value: Any) -> str:
    """Render structured evidence as a readable line, never Python/JSON repr."""
    from laclaugpt_visualization.ep24_presentation import readable
    return readable(value)


def view(frame: pd.DataFrame, *, full: bool = False) -> pd.DataFrame:
    """Only explicit research fields enter an on-screen table or CSV."""
    keys = tuple(DISPLAY) if full else TABLE_FIELDS
    columns = [key for key in keys if key in frame.columns]
    output = frame.loc[:, columns].copy()
    output.columns = [DISPLAY[key] for key in columns]
    for key in output.columns:
        if output[key].dtype == object:
            output[key] = output[key].map(friendly)
    return output



def declared_run(manifest: Mapping[str, Any]) -> str:
    """The cohort a manifest declares, in the spellings the real exporters use.

    The checkpoint exporter (#242) writes ``producer_revision: "monday500_20261031"`` and no
    ``dataset`` key at all, so a reader that only looks for ``dataset`` concludes "no verifiable
    dataset identifier" about a perfectly identified export. Normalise rather than require one
    spelling.
    """
    for key in ("dataset", "dataset_id", "run_id"):
        value = str(manifest.get(key) or "").strip()
        if value:
            return value
    revision = str(manifest.get("producer_revision") or "").strip()
    if revision:
        return revision if revision.startswith("ep24_") else f"ep24_{revision}"
    cohort = manifest.get("approved_cohort") or {}
    if isinstance(cohort, Mapping):
        value = str(cohort.get("dataset") or "").strip()
        if value:
            return value
    inputs = manifest.get("inputs") or {}
    declared = {str(v.get("dataset") or v.get("dataset_id") or "").strip()
                for v in inputs.values() if isinstance(v, dict)}
    declared.discard("")
    return next(iter(declared)) if len(declared) == 1 else ""


def cohort_notes(frame: pd.DataFrame, manifest: Mapping[str, Any]) -> list[str]:
    """Facts a researcher should see but that must not block the dashboard.

    The row-level ``dataset`` column carries the producer's *pipeline* label
    (``ep2024_reprocess``), not the cohort name. Treating the two as the same thing made the guard
    reject all 1 500 delivered videos. The label is reported here, as provenance.
    """
    notes: list[str] = []
    if not manifest:
        notes.append(
            "No export manifest: these counts have no producer run to point at, and no verifiable "
            "dataset identifier. Treat them as rows from a file, not as an exported cohort."
        )
    if "dataset" in frame.columns:
        labels = sorted({str(value) for value in frame["dataset"].dropna().unique() if str(value).strip()})
        if labels:
            notes.append(
                "Producer pipeline label in the rows: " + ", ".join(labels)
                + f"; the cohort is {EXPECTED_DATASET}, named by _storage_id and the export manifest."
            )
    cohort = manifest.get("approved_cohort") if isinstance(manifest, Mapping) else None
    if isinstance(cohort, Mapping) and cohort.get("sha256"):
        notes.append(f"Approved cohort roster sha256 {str(cohort['sha256'])[:16]}…")
    return notes


def processed_export_warnings(frame: pd.DataFrame, manifest: Mapping[str, Any]) -> list[str]:
    """Validate the actual 500 exported videos per country; no cohort roster required.

    Counts are over loaded records, not inferred from the larger source collection.
    Stage completion is always reported separately rather than assumed from membership.
    """
    warnings: list[str] = []
    if "country" not in frame:
        return ["Country field missing from the exported videos."]
    normalized = frame["country"].fillna("").astype(str).str.lower().map(COUNTRIES)
    if normalized.isna().any():
        warnings.append("Export contains unknown or unassigned countries.")
    for country in ("Finland", "Poland", "Portugal"):
        actual = int((normalized == country).sum())
        if actual != 500:
            warnings.append(f"{country}: expected 500 exported videos, found {actual}.")
    if len(frame) != 1500:
        warnings.append(f"Expected 1,500 exported videos; found {len(frame)}.")
    if "_storage_id" in frame:
        ids = frame["_storage_id"].fillna("").astype(str).str.strip()
        if ids.eq("").any() or ids.duplicated().any():
            warnings.append("Export contains empty or duplicate storage identities.")
    elif "video_id" in frame:
        ids = frame["video_id"].fillna("").astype(str).str.strip()
        composite = normalized.fillna("") + ":" + ids
        if ids.eq("").any() or composite.duplicated().any():
            warnings.append("Export contains missing or duplicate country-scoped video identities.")
    else:
        warnings.append("Neither storage identity nor video ID is available for deduplication.")
    countries = manifest.get("countries") if isinstance(manifest, Mapping) else None
    if isinstance(countries, Mapping):
        for code in ("finland", "poland", "portugal"):
            info = countries.get(code)
            if isinstance(info, Mapping):
                expected = info.get("exported_videos", info.get("exported"))
                if isinstance(expected, int) and expected != 500:
                    warnings.append(f"Manifest reports {expected} videos for {code}, not 500.")
    return warnings



def coverage(frame: pd.DataFrame) -> pd.DataFrame:
    """Explicit per-step denominator and observed status, no inferred validity."""
    records = frame.to_dict("records")
    result = []
    for number, (name, _) in STAGES.items():
        counts = Counter(status(record, number) for record in records)
        for state, count in sorted(counts.items()):
            result.append({"Step": number, "Stage": name,
                           "Status": state, "Videos": count,
                           "Denominator": len(records)})
    return pd.DataFrame(result)


def evidence_sections(row: Mapping[str, Any]) -> list[tuple[str, str]]:
    return [(title, friendly(row.get(key))) for key, title in DISPLAY.items()
            if key not in {"country", "video_id", "source_type", "source_url"}
            and friendly(row.get(key))]


def research_children(items: list[dict], columns: Mapping[str, str]) -> pd.DataFrame:
    """Normalize child statement display: exclude all unknown/raw fields."""
    return pd.DataFrame([{label: friendly(item.get(key)) for key, label in columns.items()}
                         for item in items], columns=list(columns.values()))


DNA_FIELDS = {
    "document": "Source video",
    "actor": "Actor", "actor_name": "Actor name", "actor_id": "Actor identifier",
    "concept": "Concept", "concept_name": "Concept name",
    "stance": "Position", "polarity": "Polarity",
    "evidence_quote": "Supporting quotation", "confidence": "Model confidence",
}
SNA_FIELDS = {
    "document": "Source video", "source_actor": "Source actor",
    "target_actor": "Target actor", "source_actor_id": "Source identifier",
    "target_actor_id": "Target identifier", "relation_type": "Relationship",
    "evidence_quote": "Supporting quotation",
}

"""Safe researcher presentation layer for EP24. Explicit field allowlists only."""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

import pandas as pd

from laclaugpt_visualization.ep24_reprocessed import STAGES, status, text, unpack

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
    value = unpack(value)
    if value is None:
        return ""
    if isinstance(value, dict):
        return "; ".join(f"{str(k).replace('_', ' ').capitalize()}: {friendly(v)}"
                         for k, v in value.items() if friendly(v))
    if isinstance(value, list):
        return " • ".join(friendly(item) for item in value if friendly(item))
    return text(value)


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


def cohort_warnings(frame: pd.DataFrame, manifest: Mapping[str, Any]) -> list[str]:
    warnings = []
    if not manifest:
        warnings.append("No export manifest: provenance unverified.")
    # Never turn a blank manifest into a claim that this is Monday500.
    run = str(manifest.get("dataset") or manifest.get("dataset_id")
              or manifest.get("run_id") or "").strip()
    if not run:
        inputs = manifest.get("inputs") or {}
        declared = {str(v.get("dataset") or v.get("dataset_id") or "").strip()
                    for v in inputs.values() if isinstance(v, dict)}
        declared.discard("")
        if len(declared) == 1:
            run = next(iter(declared))
    if run != EXPECTED_DATASET:
        warnings.append(f"Expected {EXPECTED_DATASET}; manifest declares "
                        f"{run or 'no verifiable dataset identifier'}. "
                        "Not verified as the requested 500-video cohort.")
    if "country" not in frame:
        warnings.append("Country field missing.")
    else:
        normalized = frame.country.fillna("").astype(str).str.lower().map(COUNTRIES)
        for country in ("Finland", "Poland", "Portugal"):
            actual = int((normalized == country).sum())
            if actual != 500:
                warnings.append(f"{country}: {actual} rows, target 500. "
                                "Do not interpret this as a complete cohort.")
        if normalized.isna().any():
            warnings.append("Unrecognized countries in export.")
    if "dataset" in frame:
        other = frame["dataset"].dropna().astype(str)
        if not other.empty and not other.eq(EXPECTED_DATASET).all():
            warnings.append("Some exported rows belong to another dataset.")
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

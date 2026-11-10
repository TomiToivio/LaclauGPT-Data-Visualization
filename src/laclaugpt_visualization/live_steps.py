"""Read-only analysis helpers for the FI/PL/PT live steps 1–7 export.

The dashboard is a view over artifacts built by ``tools/build_live_steps_artifacts.py``: one index
row per video (short scalars) plus a gzipped text bundle holding the long cells and the structured
children (DNA statements, SNA edges/nodes). Nothing here writes, guesses or re-derives a producer
field; the only derivations are the ones the manifest names (recording date from the media id,
duplicate collapse, step counters).
"""
from __future__ import annotations

import gzip
import json
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import pandas as pd

#: Steps in the export, with the bundle fields that carry their output and the index fields that
#: describe it. Step numbers match ``step_0N_status`` in the producer.
STEPS: dict[int, tuple[str, tuple[str, ...], tuple[str, ...]]] = {
    1: ("Preprocess · ASR", ("asr_transcript", "asr_translated"),
        ("asr_backend", "asr_language", "asr_model", "asr_runtime_ms", "preprocess_status")),
    2: ("Preprocess · OCR", ("ocr_1",), ("ocr_backend", "ocr_model", "ocr_runtime_ms")),
    3: ("Frame VLM", ("frame_analysis_1",),
        ("frame_analysis_status", "frame_analysis_model", "frame_timestamp_seconds")),
    4: ("Video VLM", ("vllm_video_analysis", "vllm_video_markdown_analysis"),
        ("vllm_video_status", "vllm_video_model", "vllm_video_inference_seconds")),
    5: ("Multimodal summary", ("summary_analysis", "summary_summary_md", "postprocess_summary_md"),
        ("summary_quality_status", "postprocess_entities", "postprocess_themes")),
    6: ("Laclau discourse", ("laclau_structured_json", "laclau_summary_md"),
        ("laclau_status", "laclau_formula_conditions_met", "formula_of_populism_us",
         "formula_of_populism_frontier")),
    7: ("Discourse network (DNA)", ("dna_analysis_markdown", "dna_statements_json"),
        ("dna_status", "dna_statement_count", "dna_binary_count", "dna_uncertain_count")),
    8: ("Social network (SNA)", ("sna_edges_json", "sna_report_markdown"),
        ("sna_status", "sna_schema_version", "has_sna")),
}

OK_TOKENS = {"ok", "complete", "completed", "success", "done", "cached", "analyzed"}
MISSING = {"", "nan", "none", "null", "<na>"}

_BUNDLE_MEMO: dict[tuple[str, int, int, tuple[str, ...]], dict[str, dict[str, Any]]] = {}


def clean(value: Any) -> str:
    if value is None:
        return ""
    value = str(value).strip()
    return "" if value.lower() in MISSING else value


def as_list(value: Any) -> list[str]:
    """A list out of a JSON list cell, a JSON string, or a bare string. Never raises."""
    if value is None:
        return []
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        if raw[0] in "[{":
            try:
                value = json.loads(raw)
            except ValueError:
                return [raw]
        else:
            return [raw]
    if isinstance(value, dict):
        value = list(value.values())
    try:
        return [str(item) for item in value if clean(item)]
    except TypeError:
        return []


def load(root: str | Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """The index rows and the manifest, from the artifact directory the server points at."""
    root = Path(root)
    frame = pd.DataFrame()
    for name in ("combined.csv", "finland.csv"):
        path = root / name
        if path.is_file():
            frame = pd.read_csv(path, dtype=str, keep_default_na=False)
            break
    manifest_path = root / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    return frame, manifest


def bundle_text(root: str | Path, fields: Iterable[str]) -> dict[str, dict[str, Any]]:
    """``record_id`` → the requested long fields, read once per bundle file identity.

    The inspector is the only consumer, and a researcher opens one record at a time, so the whole
    bundle is parsed once per process rather than seeking inside the gzip stream.
    """
    wanted = tuple(sorted(set(fields)))
    found: dict[str, dict[str, Any]] = {}
    for path in sorted(Path(root).resolve().glob("*_text.jsonl.gz")):
        stat = path.stat()
        key = (str(path), stat.st_mtime_ns, stat.st_size, wanted)
        if key not in _BUNDLE_MEMO:
            scanned: dict[str, dict[str, Any]] = {}
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        payload = json.loads(line)
                    except ValueError:
                        continue
                    record_id = clean(payload.get("record_id"))
                    if record_id:
                        scanned[record_id] = {name: payload[name] for name in wanted
                                              if payload.get(name) not in (None, "", [])}
            _BUNDLE_MEMO[key] = scanned
        found.update(_BUNDLE_MEMO[key])
    return found


def filter_records(frame: pd.DataFrame, *, countries: Iterable[str] = (), platforms: Iterable[str] = (),
                   political: Iterable[str] = (), months: Iterable[str] = (),
                   query: str = "", min_steps: int = 0) -> pd.DataFrame:
    """The one filter path every view uses, so a chart and a table cannot disagree."""
    result = frame
    for column, wanted in (("country", countries), ("source_type", platforms),
                           ("political_preference", political), ("month", months)):
        wanted = [value for value in wanted if value]
        if wanted and column in result.columns:
            result = result[result[column].isin(wanted)]
    if min_steps and "pipeline_steps_ok" in result.columns:
        steps = pd.to_numeric(result["pipeline_steps_ok"], errors="coerce").fillna(0)
        result = result[steps >= min_steps]
    if query and "video_id" in result.columns:
        result = result[result["video_id"].str.contains(query, case=False, regex=False)]
    return result


#: Step 8 has no ``step_08_status`` in the export; the producer reports it as ``sna_status``.
STATUS_COLUMN = {1: "step_01_status", 2: "step_02_status", 3: "step_03_status",
                 4: "step_04_status", 5: "step_05_status", 6: "step_06_status",
                 7: "step_07_status", 8: "sna_status"}


def step_table(frame: pd.DataFrame) -> pd.DataFrame:
    """one row per step: how many of these records carry its output, per country."""
    rows = []
    for step, (label, _, _) in STEPS.items():
        column = STATUS_COLUMN[step]
        statuses = frame[column].map(clean) if column in frame.columns else pd.Series(dtype=str)
        for country, group in frame.groupby("country"):
            group_statuses = statuses.loc[group.index]
            ok = group_statuses.str.lower().isin(OK_TOKENS).sum()
            rows.append({"step": step, "stage": label, "country": country,
                         "records": len(group), "complete": int(ok),
                         "pct": round(100 * ok / len(group), 1) if len(group) else 0.0})
    return pd.DataFrame(rows)


def status_counts(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    if column not in frame.columns:
        return pd.DataFrame(columns=["status", "country", "records"])
    grouped = (frame.assign(status=frame[column].map(clean).replace("", "not reported"))
               .groupby(["status", "country"]).size().reset_index(name="records"))
    return grouped.sort_values("records", ascending=False)


def value_counts(frame: pd.DataFrame, column: str, limit: int = 20) -> pd.DataFrame:
    """Counts of one column, or of one JSON-list column's members when the cell is a list."""
    if column not in frame.columns:
        return pd.DataFrame(columns=["value", "records"])
    counter: Counter = Counter()
    for value in frame[column]:
        items = as_list(value)
        counter.update(items or [clean(value)])
    counter.pop("", None)
    rows = [{"value": key, "records": count} for key, count in counter.most_common(limit)]
    return pd.DataFrame(rows)


def sentiment_totals(frame: pd.DataFrame) -> pd.DataFrame:
    """Mention counts per sentiment column. These are producer-coded targets, not a verdict."""
    rows = []
    for column in ("positive", "neutral", "negative"):
        counter: Counter = Counter()
        if column in frame.columns:
            for value in frame[column]:
                counter.update(as_list(value))
        counter.pop("", None)
        rows.append({"sentiment": column, "mentions": sum(counter.values()),
                     "distinct": len(counter), "top": ", ".join(list(counter)[:5])})
    return pd.DataFrame(rows)


def child_records(root: str | Path, frame: pd.DataFrame, field: str) -> list[dict[str, Any]]:
    """One row per child record (DNA statement, SNA edge) for the filtered videos, linked by record_id."""
    from laclaugpt_visualization.ep24_reprocessed import read_bundle_field

    countries = sorted({clean(value) for value in frame.get("country", [])} - {""})
    bundle = read_bundle_field(root, field, countries)
    output = []
    for _, row in frame.iterrows():
        record_id = clean(row.get("record_id"))
        for item in bundle.get(record_id, []):
            output.append({"record_id": record_id, "country": clean(row.get("country")),
                           "video_id": clean(row.get("video_id")), **item})
    return output


def node_degrees(edges: Iterable[Mapping[str, Any]], limit: int = 20) -> pd.DataFrame:
    counter: Counter = Counter()
    for edge in edges:
        source, target = clean(edge.get("source")), clean(edge.get("target"))
        if source:
            counter[source] += 1
        if target:
            counter[target] += 1
    return pd.DataFrame([{"node": node, "edges": count}
                         for node, count in counter.most_common(limit)])


def stage_availability(manifest: Mapping[str, Any]) -> pd.DataFrame:
    """Per country and stage: available, complete records, denominator — gaps rendered as gaps."""
    rows = []
    for country, stages in (manifest.get("stage_coverage") or {}).items():
        denominator = (manifest.get("record_counts", {}).get(country, {}) or {}).get("exported", 0)
        for stage, data in stages.items():
            rows.append({"country": country, "stage": stage,
                         "records": data.get("records", 0), "denominator": denominator,
                         "pct": round(100 * data.get("records", 0) / denominator, 1) if denominator else None,
                         "availability": "present" if data.get("available") else "unavailable in this source"})
    return pd.DataFrame(rows)

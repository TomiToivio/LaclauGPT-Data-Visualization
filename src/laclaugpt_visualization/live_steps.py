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


def node_degrees(edges: Iterable[Mapping[str, Any]], nodes: Iterable[Mapping[str, Any]] = (),
                 limit: int = 20) -> pd.DataFrame:
    """Most connected actors, by the producer's own labels.

    Edges carry ``source_label`` / ``target_label`` next to the ``actor:<hash>`` identifiers; a table of
    hashes is unreadable, so the labels win and the node table fills in anything the edges left bare.
    """
    labels = {clean(node.get("node_id")): clean(node.get("label")) for node in nodes}
    counter: Counter = Counter()
    for edge in edges:
        for identifier, label_key in (("source", "source_label"), ("target", "target_label")):
            name = clean(edge.get(label_key)) or labels.get(clean(edge.get(identifier)), "")
            if name:
                counter[name] += 1
    return pd.DataFrame([{"node": node, "edges": count}
                         for node, count in counter.most_common(limit)])


def parse_json_cell(value: Any) -> dict[str, Any]:
    """A producer JSON cell as a dict. Anything unparseable is an empty dict, never a guess."""
    if isinstance(value, dict):
        return value
    raw = clean(value)
    if not raw.startswith("{"):
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def laclau_summary(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate the step-6 structure: how often a Us, a frontier and an affect are actually articulated.

    The abstention reasons are counted, not hidden: a corpus where two thirds of the clips carry no
    articulated frontier is a finding about the corpus, not a gap in the dashboard.
    """
    affects: Counter = Counter()
    abstentions: Counter = Counter()
    totals = {"records": 0, "parsed": 0, "conditions_met": 0, "with_us": 0, "with_frontier": 0,
              "with_chains": 0, "with_affects": 0, "with_counter_evidence": 0, "affects": 0,
              "chains": 0, "uncertainty_notes": 0}
    for row in rows:
        totals["records"] += 1
        parsed = parse_json_cell(row.get("laclau_structured_json"))
        if not parsed:
            continue
        totals["parsed"] += 1
        if parsed.get("formula_minimum_conditions_met"):
            totals["conditions_met"] += 1
        totals["with_us"] += bool(as_list(parsed.get("us_constructs")))
        totals["with_frontier"] += bool(as_list(parsed.get("frontier_constructs")))
        totals["with_chains"] += bool(as_list(parsed.get("chains")))
        totals["with_counter_evidence"] += bool(as_list(parsed.get("counter_evidence")))
        totals["uncertainty_notes"] += len(as_list(parsed.get("uncertainty_notes")))
        values = as_list(parsed.get("affects"))
        totals["affects"] += len(values)
        totals["with_affects"] += bool(values)
        totals["chains"] += len(as_list(parsed.get("chains")))
        for item in values:
            label = clean(item.get("label") if isinstance(item, Mapping) else item)
            if label:
                affects[label] += 1
        reason = clean(parsed.get("formula_abstention_reason"))
        if reason:
            abstentions[reason[:220]] += 1
    totals["affect_labels"] = pd.DataFrame(
        [{"label": label, "records": count} for label, count in affects.most_common(20)])
    totals["abstentions"] = pd.DataFrame(
        [{"reason": reason, "records": count} for reason, count in abstentions.most_common(15)])
    return totals


def affect_rows(rows: Iterable[Mapping[str, Any]], limit: int = 200) -> list[dict[str, Any]]:
    """One row per articulated affect: the label, the span it was read from, and the confidence."""
    output = []
    for row in rows:
        for item in as_list(parse_json_cell(row.get("laclau_structured_json")).get("affects")):
            if not isinstance(item, Mapping):
                continue
            output.append({"record_id": clean(row.get("record_id")),
                           "country": clean(row.get("country")),
                           "label": clean(item.get("label")),
                           "confidence": clean(item.get("confidence")),
                           "text_span": clean(item.get("text_span"))[:240],
                           "provenance": clean(item.get("provenance"))})
    return output[:limit]


def statement_table(statements: Iterable[Mapping[str, Any]], limit: int = 400) -> pd.DataFrame:
    """Statements as the evidence they are: actor, concept, stance, proposition, quote."""
    columns = ("record_id", "country", "actor_name_raw", "actor_type", "organization",
               "concept_label_raw", "stance", "agreement", "network_layer", "confidence",
               "proposition", "evidence_quote")
    rows = [{column: clean(item.get(column))[:260] for column in columns}
            for item in statements][:limit]
    return pd.DataFrame(rows, columns=list(columns))


def search_bundle(bundle: Mapping[str, Mapping[str, Any]], query: str,
                  fields: Iterable[str] = (), limit: int = 60) -> list[dict[str, Any]]:
    """Substring search over the long cells, with a snippet.

    Casefolded substring matching, not a ranked index: 1,500 records of plain text are small enough that
    a researcher wants *every* hit and an honest snippet, not the top ten of an opaque ranking.
    """
    needle = clean(query).casefold()
    if not needle:
        return []
    fields = list(fields)
    hits = []
    for record_id, payload in bundle.items():
        for field in fields:
            value = payload.get(field)
            if not isinstance(value, str):
                continue
            haystack = value.casefold()
            position = haystack.find(needle)
            if position < 0:
                continue
            hits.append({"record_id": record_id, "field": field,
                         "hits": haystack.count(needle),
                         "snippet": value[max(0, position - 90):position + len(needle) + 110]
                                    .replace("\n", " ").strip()})
    return sorted(hits, key=lambda hit: -hit["hits"])[:limit]


def actor_concept_graph(statements: Iterable[Mapping[str, Any]],
                        max_actors: int = 40, max_concepts: int = 40) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The observed actor–concept network, straight from the statements.

    Two node kinds, one edge kind: an actor *said something about* a concept. Edge weight is the number
    of statements, colour is the dominant stance. Only what the producer extracted is drawn — an absent
    edge means no statement was extracted, not that no relation exists in the world.
    """
    actors: Counter = Counter()
    concepts: Counter = Counter()
    pairs: Counter = Counter()
    stance: dict[tuple[str, str], Counter] = {}
    for statement in statements:
        actor = clean(statement.get("actor_name_raw")) or clean(statement.get("actor_id"))
        concept = clean(statement.get("concept_label_raw")) or clean(statement.get("concept"))
        if not actor or not concept:
            continue
        actors[actor] += 1
        concepts[concept] += 1
        pairs[(actor, concept)] += 1
        stance.setdefault((actor, concept), Counter())[clean(statement.get("stance")) or "not stated"] += 1

    keep_actors = {name for name, _ in actors.most_common(max_actors)}
    keep_concepts = {name for name, _ in concepts.most_common(max_concepts)}
    nodes = ([{"id": f"actor:{name}", "label": name, "kind": "actor", "statements": count}
              for name, count in actors.most_common(max_actors)]
             + [{"id": f"concept:{name}", "label": name, "kind": "concept", "statements": count}
                for name, count in concepts.most_common(max_concepts)])
    edges = [{"source": f"actor:{actor}", "target": f"concept:{concept}", "statements": count,
              "stance": stance[(actor, concept)].most_common(1)[0][0]}
             for (actor, concept), count in pairs.items()
             if actor in keep_actors and concept in keep_concepts]
    return pd.DataFrame(nodes), pd.DataFrame(edges)


def problem_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Every record whose producer said something other than ok, with the reason next to it."""
    statuses = [f"step_0{step}_status" for step in range(1, 8)] + ["sna_status"]
    reasons = ("processing_status_reason", "frame_quality_reason", "summary_quality_reason",
               "laclau_abstention_reason", "sna_error", "dna_error", "preprocess_note")
    rows = []
    for _, row in frame.iterrows():
        bad = [status for status in statuses
               if status in frame.columns and clean(row.get(status)).lower() not in OK_TOKENS]
        if not bad:
            continue
        rows.append({"record_id": clean(row.get("record_id")), "country": clean(row.get("country")),
                     "video_id": clean(row.get("video_id")),
                     "not_complete": ", ".join(status.replace("_status", "").replace("step_0", "step ")
                                               for status in bad),
                     **{reason: clean(row.get(reason))[:200] for reason in reasons
                        if clean(row.get(reason))}})
    return pd.DataFrame(rows)


def monthly_by(frame: pd.DataFrame, by: str = "source_type") -> pd.DataFrame:
    """Records per recording month, split by one column — the stacked view the 8501 dashboard leads with."""
    if "month" not in frame.columns:
        return pd.DataFrame()
    split = frame[by].map(clean).replace("", "not reported") if by in frame.columns else "all"
    return (frame.assign(_split=split)
            .groupby(["month", "_split"]).size().reset_index(name="records"))


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

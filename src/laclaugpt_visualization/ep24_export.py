"""Read-only final-result projection of cumulative EP24 checkpoints.

This is a private export, NOT a public-data anonymizer. Producer field names and
nested values stay intact; relation tables are reproducible views of those fields.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

from .ep24_pipeline import EP24_STAGES, SOURCE_COLUMNS

VERSION = "ep24-final-export-v1"
PRODUCER_REVISION = "c3ffc569dea1b2c008000075f23bbea46ef8dfc8"
COUNTRIES = {"fi": "finland", "pl": "poland", "pt": "portugal",
             "finland": "finland", "poland": "poland", "portugal": "portugal"}
# Reuse the existing consumption contract, excluding intermediate/backend fields.
OMIT = {"ocr_runtime_ms", "asr_runtime_ms", "vllm_video_runtime_seconds", "metadata",
        "ep24_memory_entity_ids", "ep24_memory_topic_ids", "ep24_memory_theme_ids",
        "ep24_memory_sentiment_target_ids_json"}
FIELDS = {s.number: tuple(k for k in s.reported_columns() if k not in OMIT)
          for s in EP24_STAGES}
FIELDS[0] = tuple(SOURCE_COLUMNS) + (
    "dataset", "_storage_id", "source_url", "source_language", "created_at", "timestamp",
    "schema_version", "processing_status", "processing_status_reason",
)
FIELDS[1] += ("asr_translation", "asr_model", "asr_backend", "ocr_model", "ocr_backend",
              "preprocess_note", "preprocess_completed_at")
FIELDS[3] += ("vllm_video_error", "video_initial_skip_seconds", "vllm_video_prompt_sha256",
              "vllm_video_structured_output_error")
FIELDS[5] += ("ep24_entity_canonical_names", "ep24_entity_unresolved_json",
              "ep24_theme_resolution_json", "ep24_theme_canonical_names")
FIELDS[7] += ("dna_model_metadata_json", "dna_context_sha256")
FIELDS[8] += ("sna_nodes_json", "sna_metrics_json", "sna_schema_version", "sna_prompt_version",
              "sna_castells_prompt_version", "sna_generated_at", "sna_status", "sna_error",
              "sna_report_markdown", "sna_castells_interpretation_markdown")
FIELDS[9] += ("rdf_document_uri", "rdf_row_uri", "rdf_schema_version", "rdf_status")
ALLOWED = set().union(*FIELDS.values())
HUMAN = {"entities", "themes", "researcher_note", "political_preference"}
STRUCTURED = {k for k in ALLOWED if k.endswith("_json")} | {
    "entities", "themes", "postprocess_entities", "postprocess_themes", "ep24_entity_ids",
    "ep24_entity_canonical_names", "ep24_theme_canonical_names",
}
STATUS = {1: "preprocess_status", 2: "frame_analysis_status", 3: "vllm_video_status",
          4: "summary_quality_status", 6: "laclau_status", 7: "dna_status",
          8: "sna_status", 9: "rdf_status"}
CHILDREN = {
    "entities": ("postprocess_entities", None),
    "themes": ("postprocess_themes", None),
    "sentiment_targets": ("ep24_sentiment_targets_json", None),
    "dna_statements": ("dna_statements_json", "statements"),
    "sna_nodes": ("sna_nodes_json", "nodes"),
    "sna_edges": ("sna_edges_json", "edges"),
}
MISSING = {"", "none", "null", "nan", "<na>"}


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def digest(value):
    return hashlib.sha256(dumps(value).encode()).hexdigest()


def text(value):
    if value is None:
        return ""
    result = str(value).strip()
    return "" if result.casefold() in MISSING else result


def decode(value):
    """Decode up to three JSON envelopes; never interpret Python repr or plain text."""
    for _ in range(3):
        if not isinstance(value, str) or not value.strip().startswith(("[", "{", '"')):
            break
        try:
            value = json.loads(value)
        except ValueError:
            break
    return value


def read_source(path: Path, table="records"):
    """CSV IDs remain opaque strings; SQLite is opened read-only."""
    if path.suffix.lower() == ".csv":
        csv.field_size_limit(sys.maxsize)
        with path.open(encoding="utf-8-sig", newline="") as stream:
            return list(csv.DictReader(stream))
    if path.suffix.lower() in {".sqlite", ".sqlite3", ".db"}:
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
            db.row_factory = sqlite3.Row
            names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if table not in names:
                raise ValueError("Requested SQLite table does not exist")
            escaped = table.replace('"', '""')
            return [dict(r) for r in db.execute(f'SELECT * FROM "{escaped}"')]
    if path.suffix.lower() == ".jsonl":
        with path.open(encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]
    raise ValueError("Expected CSV, JSONL or SQLite cumulative checkpoint")


def stage_states(row):
    pipeline = decode(row.get("_pipeline", {}))
    pipeline = pipeline if isinstance(pipeline, dict) else {}
    result = {}
    for step in range(10):
        raw = text(row.get(STATUS.get(step, "")))
        state = decode(pipeline.get(f"step_{step:02d}", {}))
        state = state if isinstance(state, dict) else {}
        # Keep orchestration separate: process success is not interpretation validity.
        execution = {k: state[k] for k in ("status", "completed_at", "error_type") if k in state}
        has_output = any(text(row.get(k)) for k in FIELDS[step]
                         if k != STATUS.get(step) and not k.endswith(("_status", "_error")))
        result[str(step)] = {
            "reported_status": raw or None,
            "availability": "output_present" if has_output else "not_exported",
            "execution": execution,
        }
    return result


def project(sources):
    """Project (country, source_label, rows) inputs; quarantine conflicting duplicates."""
    groups = defaultdict(list)
    diagnostics = []
    omitted = set()
    input_counts = Counter()
    for country, label, rows in sources:
        country = COUNTRIES[country.casefold()]
        for number, row in enumerate(rows, 1):
            input_counts[country] += 1
            if not isinstance(row, dict):
                raise TypeError("Input records must be JSON objects")
            observed_country = COUNTRIES.get(text(row.get("country")).casefold())
            vid = row.get("video_id")
            reason = None
            if not isinstance(vid, str) or not text(vid):
                reason = "missing_or_nonstring_video_id"
            elif observed_country != country:
                reason = "missing_or_conflicting_country"
            elif not text(row.get("source_type")):
                reason = "missing_platform"
            if reason:
                diagnostics.append({"country": country, "source": label, "row": number,
                                    "reason": reason})
                continue
            dataset = text(row.get("dataset")) or "ep2024_reprocess"
            key = [country, dataset, text(row["source_type"]).casefold(), vid]
            source_key = "ep24:" + ":".join(quote(x, safe="") for x in key)
            fields = {k: decode(v) if k in STRUCTURED else v for k, v in row.items()
                      if k in ALLOWED}
            for field in STRUCTURED:
                if field.endswith("_json") and text(fields.get(field)) and not isinstance(
                    fields[field], (dict, list)
                ):
                    diagnostics.append({"country": country, "source": label, "row": number,
                                        "reason": "malformed_structured_field", "field": field})
            fields.update(country=country, dataset=dataset)
            states = stage_states(row)
            omitted.update(set(row) - ALLOWED - {"_pipeline"})
            # Compare final projection, not transient prompts/caches, to deduplicate.
            signature = digest({"fields": fields, "stages": states})
            groups[source_key].append((signature, fields, states,
                                       {"source": label, "row": number}))
    records = []
    for key, group in sorted(groups.items()):
        if len({item[0] for item in group}) > 1:
            diagnostics.append({"source_key": key, "reason": "conflicting_duplicate",
                                "count": len(group)})
            continue
        _, fields, states, _ = group[0]
        records.append({"source_key": key, "fields": fields, "stages": states,
                        "provenance": sorted([x[3] for x in group], key=dumps)})
        if len(group) > 1:
            diagnostics.append({"source_key": key, "reason": "identical_duplicate",
                                "count": len(group) - 1})
    return records, diagnostics, sorted(omitted), dict(input_counts)


def child_tables(records):
    tables = {name: [] for name in CHILDREN}
    tables["discourse_items"] = []
    for record in records:
        fields, key = record["fields"], record["source_key"]
        candidates = []
        for name, (field, container) in CHILDREN.items():
            value = fields.get(field)
            if container and isinstance(value, dict):
                value = value.get(container)
            if isinstance(value, list):
                candidates.append((name, field, value))
        discourse = fields.get("laclau_structured_json")
        if isinstance(discourse, dict):
            # Preserve producer's item categories, without inventing a unified "claim".
            for category, value in discourse.items():
                if isinstance(value, list):
                    candidates.append(("discourse_items", f"laclau_structured_json.{category}", value))
        for name, field, values in candidates:
            occurrences = Counter()
            for index, value in enumerate(values):
                fingerprint = digest(value)
                occurrences[fingerprint] += 1
                tables[name].append({
                    "child_id": digest([key, field, fingerprint, occurrences[fingerprint]]),
                    "source_key": key, "country": fields["country"],
                    "field": field, "index": index, "origin": "model_output",
                    "value": value,
                })
    return tables


def readable(value, depth=0):
    """Researcher-readable rendering without a JSON cell dump or invented analysis."""
    prefix = "  " * depth
    if isinstance(value, dict):
        return "\n".join(f"{prefix}- **{k.replace('_', ' ')}**: " +
                         ("\n" + readable(v, depth + 1) if isinstance(v, (dict, list))
                          else text(v) or "Not exported") for k, v in value.items())
    if isinstance(value, list):
        if not value:
            return prefix + "- Explicitly empty list in producer output"
        return "\n".join(prefix + "- " + readable(v, depth + 1) for v in value)
    return text(value) or "Not exported"


def read_mongo(uri, database, countries):
    """Optional source adapter: find only, never claims/updates orchestration state."""
    from pymongo import MongoClient

    sources = []
    with MongoClient(uri, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000) as client:
        for country in sorted(countries):
            collection = f"laclaugpt_ep2024_reprocess_{country}_dataframe"
            projection = {k: 1 for k in ALLOWED | {"_pipeline"}}
            projection["_id"] = 0
            rows = list(client[database][collection].find({}, projection))
            # Bind the actual read, not credentials or a mutable collection name.
            label = digest(sorted(rows, key=dumps))
            sources.append((country, label, rows))
    return sources


def csv_safe(value):
    """Protect researcher CSV downloads against spreadsheet formula execution."""
    if isinstance(value, (dict, list)):
        value = dumps(value)
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def write_csv(path, rows, columns):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows({k: csv_safe(v) for k, v in row.items()} for row in rows)


def write_bundle(output, sources, *, producer_revision=None, exported_at=None):
    """Require a new directory; failed/partial bundles never replace a working export."""
    output = Path(output)
    if output.exists():
        raise ValueError("Output must be a new directory; select a new versioned export path")
    records, diagnostics, omitted, counts = project(sources)
    output.mkdir(parents=True, mode=0o700)
    def write_json(name, value):
        (output / name).write_text(dumps(value) + "\n", encoding="utf-8")
    def write_jsonl(name, values):
        (output / name).write_text("".join(dumps(v) + "\n" for v in values), encoding="utf-8")
    scalar_columns = sorted(ALLOWED - STRUCTURED)
    for country in ("combined", "finland", "poland", "portugal"):
        selected = [r for r in records if country == "combined" or r["fields"]["country"] == country]
        write_jsonl(country + ".jsonl", selected)
        report = [f"# EP24 {country} final results", "",
                  "Private research export. Model results require researcher review.",
                  "Missing means unavailable, not absence of a phenomenon.", ""]
        for record in selected:
            report += [f"## {record['source_key']}", "", "### Researcher annotations", "",
                       readable({k: v for k, v in record["fields"].items() if k in HUMAN}), ""]
            for step in range(10):
                report += [f"### Step {step} — " +
                           ("source observations" if step == 0 else
                            "derived RDF projection" if step == 9 else "model output / processing"),
                           "", readable(record["stages"][str(step)]), "",
                           readable({k: record["fields"][k] for k in FIELDS[step]
                                     if k in record["fields"] and k not in HUMAN}), ""]
        (output / (country + ".md")).write_text("\n".join(report), encoding="utf-8")
        flat = [{"source_key": r["source_key"], **{k: v for k, v in r["fields"].items()
                 if not isinstance(v, (dict, list))}} for r in selected]
        write_csv(output / (country + ".csv"), flat, ["source_key", *scalar_columns])
    for name, values in child_tables(records).items():
        write_jsonl(name + ".jsonl", values)
        # Keep nested evidence lossless in JSONL; CSV includes scalar item properties only.
        flat = [{**{k: v for k, v in item.items() if k != "value"},
                 **{f"item.{k}": v for k, v in (item["value"] if isinstance(item["value"], dict)
                    else {"label": item["value"]}).items() if not isinstance(v, (dict, list))}}
                for item in values]
        columns = ["child_id", "source_key", "country", "field", "index", "origin"]
        columns += sorted(set().union(*(set(r) for r in flat)) - set(columns))
        write_csv(output / (name + ".csv"), flat, columns)
    write_json("qa.json", diagnostics)
    write_json("dictionary.json", {
        "version": VERSION, "fields_by_step": FIELDS,
        "researcher_fields": sorted(HUMAN), "structured_fields": sorted(STRUCTURED),
        "omitted_fields_seen": omitted,
        "omission_reason": "Not allowlisted final result, identity, quality or provenance field",
        "csv_policy": "Scalar fields only; formula-like strings prefixed with apostrophe; JSONL is lossless",
    })
    coverage = {}
    for country in ("finland", "poland", "portugal"):
        subset = [r for r in records if r["fields"]["country"] == country]
        coverage[country] = {"input_rows": counts.get(country, 0), "exported_videos": len(subset),
                             "stages": {str(step): dict(Counter(
                                 r["stages"][str(step)]["reported_status"] or
                                 r["stages"][str(step)]["availability"] for r in subset))
                                        for step in range(10)}}
    manifest = {
        "version": VERSION, "producer_revision": producer_revision,
        "mapping_producer_revision": PRODUCER_REVISION,
        "sources": [{"country": country, "snapshot_sha256": label, "rows": len(rows)}
                    for country, label, rows in sources],
        "exported_at": exported_at or datetime.now(UTC).isoformat(),
        "countries": coverage, "qa_counts": dict(Counter(d["reason"] for d in diagnostics)),
        "all_requested_countries_present": all(coverage[c]["exported_videos"] for c in coverage),
        "files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir())},
        "privacy": "Private research export; not approved for public publication",
    }
    # Manifest is written last; its presence is the completed-bundle marker.
    write_json("manifest.json", manifest)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", default=[], metavar="COUNTRY=CHECKPOINT")
    parser.add_argument("--countries", nargs="+", default=["finland", "poland", "portugal"])
    parser.add_argument("--sqlite-table", default="records")
    parser.add_argument("--mongo-database", help="Optional read-only Mongo source database")
    parser.add_argument("--mongo-uri-env", default="LACLAUGPT_MONGODB_URI")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--producer-revision", help="Actual producer run revision, if known")
    parser.add_argument("--exported-at", help="Fixed ISO timestamp for reproducible reruns")
    args = parser.parse_args(argv)
    requested = {COUNTRIES[c.casefold()] for c in args.countries}
    sources = []
    for entry in args.input:
        country, path = entry.split("=", 1)
        country = COUNTRIES[country.casefold()]
        if country not in requested:
            raise ValueError("Input country was not requested")
        source = Path(path)
        # The source hash binds the input without leaking private absolute paths.
        label = hashlib.sha256(source.read_bytes()).hexdigest()
        sources.append((country, label, read_source(source, args.sqlite_table)))
    if args.mongo_database:
        if sources:
            parser.error("Choose either Mongo or local checkpoints for one snapshot")
        uri = os.environ.get(args.mongo_uri_env)
        if not uri:
            parser.error("Mongo URI environment variable is unset")
        try:
            from pymongo.errors import PyMongoError
        except ImportError:
            parser.exit(1, "Install the remote extra to read MongoDB.\n")
        try:
            sources = read_mongo(uri, args.mongo_database, requested)
        except (PyMongoError, ValueError, TypeError):
            # Driver exceptions may embed a credential-bearing endpoint.
            parser.exit(1, "Mongo read failed; check private connectivity and credentials.\n")
    if not sources:
        parser.error("At least one --input COUNTRY=CHECKPOINT is required")
    os.umask(0o077)
    manifest = write_bundle(args.output, sources, producer_revision=args.producer_revision,
                            exported_at=args.exported_at)
    print(dumps({"countries": manifest["countries"], "qa_counts": manifest["qa_counts"]}))
    return 0 if all(manifest["countries"][c]["exported_videos"] for c in requested) else 2


if __name__ == "__main__":
    raise SystemExit(main())

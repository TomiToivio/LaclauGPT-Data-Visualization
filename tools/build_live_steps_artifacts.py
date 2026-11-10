"""Build human-readable dashboard artifacts from the live steps 1–7 CSV exports (#live-steps).

The source is three wide, mostly-text CSVs (finland/poland/portugal, ~180–190 columns, 1.8 GB).
The deliverable is the artifact contract this repository's reprocessed app already reads:

    <country>.csv              one row per record: short scalars, statuses, counts, dates
    <country>_text.jsonl.gz    long cells keyed by record_id (transcripts, analyses, statements)
    children/<country>_dna_statements.csv   normalized DNA statements, joined on _storage_id
    cleaned/<country>_clean.csv  the whole cleaned dataframe, every kept column, verbatim
    combined.csv               the three indexes stacked
    MANIFEST.json              per-column keep/drop decision + reason, stage coverage, audit

Nothing is invented: every kept column is copied verbatim, every dropped column names why, and the
builder refuses to finish while a source column is unaccounted for.

The stdlib reader is used on purpose. DuckDB's `read_csv` mis-detects quoting on the portugal export
(strict: `CSV Error on Line: 1`; `ignore_errors=true`: silently 3 rows for 500 videos;
`strict_mode=false`: one row per physical line). Python's `csv` module parses all three files correctly,
so the builder reads every row, asserts it parses to the header width, and never runs with
error-dropping on. Per-row duplicates are collapsed on (country, video_id) with a completeness-biased
winner.

Usage:
    python tools/build_live_steps_artifacts.py --source-dir "<OneDrive>" --out analysis/live_steps_1_7
"""
from __future__ import annotations

import argparse
import csv
import datetime
import gzip
import hashlib
import io
import json
import re
from pathlib import Path

csv.field_size_limit(300 * 1024 * 1024)

COUNTRIES = ("finland", "poland", "portugal")
BUILDER_VERSION = "live-steps-artifacts-1"
CONTRACT = "ep24-reprocessed-view/0.1"

#: Short scalar columns copied verbatim into the index.
INDEX_COLUMNS = (
    "_storage_id", "country", "video_id", "allas_filename", "source_type", "source_recording",
    "sequence_number", "author_username", "account_type", "political_preference",
    "video_duration", "video_duration_seconds", "video_filename", "video_initial_skip_seconds",
    "video_status", "video_quality_status", "video_quality_reason", "SCROLL", "SCROLL_SECONDS",
    "processing_status", "processing_status_reason", "preprocess_status", "preprocess_note",
    "preprocess_completed_at", "asr_backend", "asr_language", "asr_model", "asr_runtime_ms",
    "ocr_backend", "ocr_model", "ocr_runtime_ms", "frame_analysis_status", "frame_analysis_model",
    "frame_file", "frame_timestamp_seconds", "frame_analysis_timestamp_seconds",
    "frame_quality_status", "frame_quality_reason", "vllm_video_status", "vllm_video_model",
    "vllm_video_api", "vllm_video_runtime_seconds", "vllm_video_inference_seconds",
    "vllm_video_analysis_duration_seconds", "vllm_video_analyzed_duration_seconds",
    "vllm_video_source_duration_seconds", "vllm_video_bytes", "vllm_video_source_id",
    "vllm_video_selected_index", "vllm_video_persistence_status",
    "vllm_video_structured_output_status", "vllm_video_trim_exit_status", "vllm_version",
    "vllm_structured_status", "vllm_gpu_name", "vllm_peak_gpu_memory_mb", "summary_quality_status",
    "summary_quality_reason", "step4_summary_provenance", "postprocess_entities",
    "postprocess_themes", "entities", "themes", "laclau_status", "laclau_formula_conditions_met",
    "laclau_persistence_status", "laclau_generated_at", "laclau_runtime_seconds",
    "laclau_abstention_reason", "laclau_context_truncated", "formula_of_populism_analysis",
    "formula_of_populism_us", "formula_of_populism_frontier", "dna_status",
    "dna_statement_count", "dna_binary_count", "dna_uncertain_count", "dna_actor_unresolved_count",
    "dna_concept_novel_count", "dna_persistence_status", "dna_generated_at", "dna_runtime_seconds",
    "dna_context_truncated", "sna_status", "sna_schema_version", "sna_generated_at", "sna_error",
    "sna_context_truncated", "positive", "neutral", "negative", "researcher_note",
    "needs_resplit", "_monday500_reused_through",
    "step_01_status", "step_02_status", "step_03_status", "step_04_status", "step_05_status",
    "step_06_status", "step_07_status", "context_evidence_role", "dna_prompt_version",
    "laclau_prompt_version", "sna_prompt_version", "sna_castells_prompt_version",
    "vllm_video_prompt_version", "vllm_video_version", "vllm_cuda_version", "vllm_torch_version",
    "vllm_hostname", "vllm_video_allas_source", "vllm_video_source_row_index", "dna_error",
    "cleaning_rule_id", "cleaning_status", "include_in_reprocess", "needs_human_review",
    "entities_seed_provenance", "themes_seed_provenance",
)

#: Long human-readable cells moved to the text bundle, verbatim.
TEXT_COLUMNS = (
    "asr_transcript", "asr_translated", "ocr_1", "frame_analysis_1", "vllm_video_analysis",
    "vllm_video_markdown_analysis", "summary_analysis", "summary_summary_md",
    "postprocess_summary_md", "laclau_structured_json", "laclau_summary_md",
    "dna_analysis_markdown", "sna_analysis_markdown", "sna_castells_interpretation_markdown",
    "sna_report_markdown",
)

#: Structured children kept as parsed lists of dicts in the bundle (the app joins them by record_id).
CHILD_COLUMNS = ("dna_statements_json", "sna_edges_json", "sna_nodes_json", "sna_metrics_json")

#: Everything else is dropped with a reason. Ordered: first match wins.
DROP_RULES = (
    (r".*_rag_context_json$", "retrieval-context dump: prompt input, not a result"),
    (r".*_codebook_context_json$", "codebook context dump: prompt input, not a result"),
    (r".*_memory_context_json$", "memory-context dump: prompt input, not a result"),
    (r"^memory_context_json$", "memory-context dump: prompt input, not a result"),
    (r"^rag_context_json$", "retrieval-context dump: prompt input, not a result"),
    (r"^codebook_context_json$", "codebook context dump: prompt input, not a result"),
    (r"^metadata$", "raw capture metadata blob: intermediate"),
    (r".*_raw_response$", "model raw response: intermediate duplicate of the parsed output"),
    (r".*_model_metadata_json$", "model metadata JSON: provenance detail, not readable output"),
    (r".*_raw_output$", "model raw output: intermediate duplicate of the parsed output"),
    (r"^vllm_video_prompt$", "the prompt itself: intermediate"),
    (r".*_prompt_hash$|.*_prompt_sha256$", "prompt hash: provenance detail, not readable"),
    (r".*_context_sha256$|.*_sha256$|.*_fingerprint$", "content hash: not human-readable"),
    (r".*_local_path$|.*_remote_path.*$|.*_analysis_path$|^vllm_video_trim_command$",
     "server-local path or command: not portable"),
    (r"^_pipeline$|^_pipeline_step_7$|^_provenance$",
     "orchestrator blob: step statuses are carried in step_0N_status and pipeline_steps_ok"),
    (r"^ep24_.*$", "EP24 ingest intermediate: seed/resolution/memory bookkeeping"),
    (r".*_normalization_json$|.*_resolution_json$|.*_unresolved_json$",
     "normalisation intermediate: entity/theme merge bookkeeping"),
)

DERIVED_COLUMNS = ("record_id", "record_date", "month", "duration_minutes",
                   "pipeline_steps_ok", "has_sna")

STAGE_SPEC = {
    "0_ingest": ("processing_status", ("video_id", "allas_filename")),
    "1_preprocess": ("preprocess_status", ("asr_transcript", "ocr_1", "frame_file")),
    "2_frame": ("frame_analysis_status", ("frame_analysis_1",)),
    "3_video": ("vllm_video_status", ("vllm_video_analysis",)),
    "4_summary": ("summary_quality_status", ("summary_analysis", "summary_summary_md")),
    "5_postprocess": (None, ("postprocess_entities", "postprocess_themes", "postprocess_summary_md")),
    "6_laclau": ("laclau_status", ("laclau_structured_json", "laclau_summary_md")),
    "7_dna": ("dna_status", ("dna_statements_json",)),
    "8_sna": ("sna_status", ("sna_edges_json",)),
}

OK_TOKENS = {"ok", "complete", "completed", "success", "done", "cached", "analyzed"}


def classify(column: str) -> tuple[str, str]:
    """(class, reason) for one source column. Every column must land somewhere."""
    if column in INDEX_COLUMNS:
        return "index", "kept: scalar a researcher reads (status, count, model, date, identity)"
    if column in TEXT_COLUMNS:
        return "text", "kept: long human-readable output, moved to the text bundle"
    if column in CHILD_COLUMNS:
        return "child", "kept: structured child records, parsed into the text bundle"
    for pattern, reason in DROP_RULES:
        if re.fullmatch(pattern, column):
            return "dropped", reason
    return "unclassified", ""


def header_of(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as handle:
        return next(csv.reader(handle))


def records(path: Path):
    """Yield one dict per record. A row that does not parse to the header width fails the build."""
    header = header_of(path)
    width = len(header)
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        next(reader)
        for number, fields in enumerate(reader, start=2):
            if len(fields) != width:
                raise ValueError(f"{path.name}: line {number} has {len(fields)} fields, "
                                 f"header has {width}")
            yield dict(zip(header, fields))


def clean(value: str | None) -> str:
    return (value or "").strip()


def json_value(raw: str | None):
    """Parsed JSON for a child cell, or None. Unparseable cells are counted, never guessed at."""
    raw = clean(raw)
    if not raw or raw[0] not in "[{":
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def statement_rows(record: dict) -> list[dict]:
    """Flatten dna_statements_json into child rows that join on the parent's storage id."""
    statements = json_value(record.get("dna_statements_json", ""))
    if isinstance(statements, dict):
        statements = next((v for v in statements.values() if isinstance(v, list)), None)
    if not isinstance(statements, list):
        return []
    output = []
    for item in statements:
        if not isinstance(item, dict):
            continue
        output.append({"_storage_id": record.get("_storage_id", ""),
                       "video_id": record.get("video_id", ""),
                       "country": record.get("country", ""), **item})
    return output


def completeness(record: dict) -> tuple:
    """Dedupe ranking: the row carrying the most stage output wins, ties broken by content volume.

    A re-run row that completed the same stages but produced an empty statement list must not beat the
    row that produced twelve statements, so the second key is total characters, not non-empty cells.
    """
    statuses = sum(1 for key, value in record.items()
                   if key.endswith("_status") and clean(value).lower() in OK_TOKENS)
    volume = sum(len(value) for value in record.values() if value)
    return (statuses, volume)


def build_country(path: Path, out: Path) -> tuple[dict, list[str]]:
    """Write one country's index, text bundle and DNA children; return its audit block.

    Two streaming passes: the first only ranks duplicate keys, the second writes the winners. A
    record carries up to a megabyte of text, so holding a whole country in memory is how this build
    dies on a 15 GB machine.
    """
    country = path.name.split("_")[0]
    index_path = out / f"{country}.csv"
    bundle_path = out / f"{country}_text.jsonl.gz"
    children_path = out / "children" / f"{country}_dna_statements.csv"
    children_path.parent.mkdir(parents=True, exist_ok=True)
    clean_path = out / "cleaned" / f"{country}_clean.csv"
    clean_path.parent.mkdir(parents=True, exist_ok=True)

    header = header_of(path)
    best: dict[str, tuple] = {}
    read = invalid = 0
    parse_failures = {name: 0 for name in CHILD_COLUMNS}
    for record in records(path):
        read += 1
        for name in parse_failures:
            if clean(record.get(name)) and json_value(record.get(name)) is None:
                parse_failures[name] += 1
        key = clean(record.get("video_id"))
        if not key:
            invalid += 1
            continue
        score = completeness(record)[:2]
        if key not in best or score > best[key]:
            best[key] = score

    index_columns = (["record_id"] + [name for name in INDEX_COLUMNS if name in header]
                     + ["record_date", "month", "duration_minutes", "pipeline_steps_ok", "has_sna"])
    text_fields = [name for name in TEXT_COLUMNS if name in header]
    child_fields = [name for name in CHILD_COLUMNS if name in header]
    #: Every kept column in one frame: identity, metadata, step status, then the long cells. This is the
    #: cleaned dataframe a researcher opens in pandas; the index + bundle above exist so the app does not
    #: have to load it.
    clean_columns = ([name.replace("record_id", "record_id") for name in index_columns]
                     + [name for name in text_fields + list(child_fields) if name not in index_columns])

    exported = statements_total = 0
    covered = {stage: 0 for stage in STAGE_SPEC}
    # mtime=0: a gzip header carries the clock, which would make every rebuild differ byte-wise and
    # turn the manifest's hashes into noise. The bundle must be reproducible from the same source.
    with index_path.open("w", newline="", encoding="utf-8") as index_file, \
            gzip.GzipFile(str(bundle_path), "wb", mtime=0) as raw_bundle, \
            io.TextIOWrapper(raw_bundle, encoding="utf-8", newline="\n") as bundle_file, \
            children_path.open("w", newline="", encoding="utf-8") as child_file, \
            clean_path.open("w", newline="", encoding="utf-8") as clean_file:
        writer = csv.DictWriter(index_file, fieldnames=index_columns, extrasaction="ignore")
        writer.writeheader()
        clean_writer = csv.DictWriter(clean_file, fieldnames=clean_columns, extrasaction="ignore")
        clean_writer.writeheader()
        child_writer = None
        seen: set[str] = set()
        for record in records(path):
            key = clean(record.get("video_id"))
            if not key or key in seen or completeness(record)[:2] != best[key]:
                continue
            seen.add(key)
            exported += 1
            record_id = f"{country}/{key}"
            record["record_id"] = record_id
            record["record_date"] = recording_date(key)
            record["month"] = record["record_date"][:7] if record["record_date"] else ""
            try:
                seconds = float(clean(record.get("video_duration_seconds")) or 0)
            except ValueError:
                seconds = 0.0
            record["duration_minutes"] = round(seconds / 60, 2)
            record["pipeline_steps_ok"] = sum(
                1 for value in (record.get(f"step_0{n}_status") for n in range(1, 8))
                if clean(value).lower() in OK_TOKENS)
            record["has_sna"] = bool(clean(record.get("sna_edges_json")))
            writer.writerow({name: record.get(name, "") for name in index_columns})
            clean_writer.writerow({name: record.get(name, "") for name in clean_columns})

            payload: dict = {"record_id": record_id}
            for name in text_fields:
                value = clean(record.get(name))
                if value:
                    payload[name] = value
            for name in child_fields:
                parsed = json_value(record.get(name))
                if parsed is not None:
                    payload[name] = parsed
            bundle_file.write(json.dumps(payload, ensure_ascii=False) + "\n")
            for stage, (_, output_fields) in STAGE_SPEC.items():
                if any(clean(record.get(field)) for field in output_fields):
                    covered[stage] += 1

            rows = statement_rows(record)
            if rows:
                if child_writer is None:
                    child_writer = csv.DictWriter(
                        child_file, fieldnames=sorted({k for row in rows for k in row}),
                        extrasaction="ignore")
                    child_writer.writeheader()
                for item in rows:
                    child_writer.writerow({k: json.dumps(v, ensure_ascii=False)
                                           if isinstance(v, (dict, list)) else v
                                           for k, v in item.items()})
                statements_total += len(rows)

    return {
        "country": country,
        "source": path.name,
        "source_bytes": path.stat().st_size,
        "source_sha256": sha256(path),
        "read": read,
        "exported": exported,
        "duplicate_rows": read - exported - invalid,
        "invalid_ids": invalid,
        "dna_statement_rows": statements_total,
        "parse_failures": parse_failures,
        "index": index_path.name,
        "bundle": bundle_path.name,
        "cleaned": clean_path.name,
        "cleaned_bytes": clean_path.stat().st_size,
        "children": children_path.name if statements_total else "",
        "stage_coverage": {
            stage: {"available": any(field in header for field in output_fields),
                    "records": covered[stage],
                    "pct_of_exported": round(100 * covered[stage] / exported, 1) if exported else 0.0,
                    "status_field": status_field or "output presence"}
            for stage, (status_field, output_fields) in STAGE_SPEC.items()},
    }, header


def recording_date(video_id: str) -> str:
    """Recording date from the media id (``…-20240604-1048000``), or empty. Stated in the UI."""
    match = re.search(r"-(20\d{2})(\d{2})(\d{2})-", video_id)
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}" if match else ""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stack(target: Path, sources: list[Path]) -> None:
    """Concatenate CSVs with a union of their columns, in first-seen order."""
    columns: list[str] = []
    for source in sources:
        with source.open(encoding="utf-8") as handle:
            columns += [name for name in next(csv.reader(handle)) if name not in columns]
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for source in sources:
            with source.open(newline="", encoding="utf-8") as rows:
                writer.writerows(csv.DictReader(rows))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build live steps 1-7 dashboard artifacts.")
    parser.add_argument("--source-dir", required=True, type=Path,
                        help="directory holding <country>_live_steps_1_7.csv")
    parser.add_argument("--out", required=True, type=Path, help="artifact directory to write")
    arguments = parser.parse_args(argv)
    out: Path = arguments.out
    out.mkdir(parents=True, exist_ok=True)

    audits = {}
    decisions: dict[str, dict] = {}
    for country in COUNTRIES:
        path = arguments.source_dir / f"{country}_live_steps_1_7.csv"
        if not path.is_file():
            raise SystemExit(f"missing source: {path}")
        audit, header = build_country(path, out)
        decisions.update({name: classify(name) for name in header})
        unaccounted = sorted(name for name, (kind, _) in decisions.items() if kind == "unclassified")
        if unaccounted:
            raise SystemExit(f"unclassified source columns in {country}: {unaccounted}")
        audits[country] = audit
        print(f"{country}: {audit['read']} read -> {audit['exported']} exported, "
              f"{audit['duplicate_rows']} duplicates, {audit['dna_statement_rows']} statements",
              flush=True)

    clean_columns_seen: list[str] = []
    for country in COUNTRIES:
        with (out / "cleaned" / f"{country}_clean.csv").open(encoding="utf-8") as handle:
            clean_columns_seen += [name for name in next(csv.reader(handle))
                                   if name not in clean_columns_seen]
    stack(out / "combined.csv", [out / f"{country}.csv" for country in COUNTRIES])
    # No cleaned/combined_clean.csv: it is exactly pandas.concat of the three per-country frames, and a
    # 75 MB duplicate blob is not worth the convenience.

    manifest = {
        "contract": CONTRACT,
        "builder_version": BUILDER_VERSION,
        "generated_at": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        "read_only": True,
        "record_unit": "video",
        "records": sum(audit["exported"] for audit in audits.values()),
        "record_counts": {
            "exported_total": sum(audit["exported"] for audit in audits.values()),
            **{country: {key: audit[key] for key in
                         ("read", "exported", "duplicate_rows", "invalid_ids", "dna_statement_rows")}
               for country, audit in audits.items()},
        },
        "countries": {country: {"exported": audit["exported"],
                                "source_sha256": audit["source_sha256"],
                                "source_bytes": audit["source_bytes"]}
                      for country, audit in audits.items()},
        "stage_coverage": {country: audit["stage_coverage"] for country, audit in audits.items()},
        "inputs": {country: {"profile": "live-csv-steps-1-7",
                             "dropped_reasons": {name: reason for name, (kind, reason)
                                                 in decisions.items() if kind == "dropped"},
                             "stage_unavailable": [stage for stage, row
                                                   in audit["stage_coverage"].items()
                                                   if not row["available"]]}
                   for country, audit in audits.items()},
        "unaccounted_source_columns": {country: [] for country in COUNTRIES},
        "parse_failures": {country: audit["parse_failures"] for country, audit in audits.items()},
        "distinct_media": sum(audit["exported"] for audit in audits.values()),
        "reader": {
            "implementation": "python csv.reader",
            "field_width_assertion": True,
            "note": ("DuckDB read_csv mis-detects quoting on the portugal export (strict: CSV Error on "
                     "Line 1; ignore_errors=true: 3 rows; strict_mode=false: one row per physical line). "
                     "Python csv reads all three exports whole: 500 records x 182/185/190 fields."),
        },
        "provenance": {"source": "OneDrive live steps 1-7 exports",
                       "recording_dates_derived_from": "video_id token YYYYMMDD",
                       "note": "Counts describe the export, not the population it samples."},
        "outputs": [{"name": str(path.relative_to(out)), "bytes": path.stat().st_size,
                     "sha256": sha256(path)}
                    for path in sorted(out.glob("*.csv")) + sorted(out.glob("*.jsonl.gz"))
                    + sorted(out.glob("cleaned/*.csv"))],
    }
    manifest["cleaned_frames"] = {
        "what": "the cleaned dataframe per country, every kept column verbatim, one row per video",
        "files": [f"cleaned/{country}_clean.csv" for country in COUNTRIES],
        "columns": len(clean_columns_seen),
        "note": "index + text bundle exist so the dashboard need not load these; both come from one build",
    }
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n",
                                       encoding="utf-8")
    print(f"manifest: {manifest['records']} records, {len(manifest['inputs']['finland']['dropped_reasons'])}"
          f" dropped source columns classified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Read-only, evidence-preserving projections for reprocessed EP24 Steps 0–9.

Field names match LaclauGPT-Multimodal-Analysis/ep24_stage_contract.py
(2026-10-12). No inference or model execution occurs here.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

STAGES = {
    0: ("Ingestion", ("_storage_id", "video_id", "allas_filename")),
    1: ("Preprocess", ("preprocess_status", "asr_transcript", "ocr_1", "frame_file")),
    2: ("Frame VLM", ("frame_analysis_status", "frame_analysis_1")),
    3: ("Video VLM", ("vllm_video_status", "vllm_video_analysis")),
    4: ("Multimodal summary", ("summary_analysis", "summary_quality_status")),
    5: ("Postprocess", ("postprocess_entities", "postprocess_themes", "postprocess_summary_md")),
    6: ("Laclau discourse", ("laclau_status", "laclau_structured_json", "laclau_summary_md")),
    7: ("Discourse network", ("dna_status", "dna_statements_json")),
    8: ("Social network", ("sna_edges_json", "sna_analysis_markdown")),
    9: ("RDF export", ()),  # file-based artifact; never infer completion from Step 8
}
STATUS_FIELDS = {1: "preprocess_status", 2: "frame_analysis_status",
                 3: "vllm_video_status", 4: "summary_quality_status",
                 6: "laclau_status", 7: "dna_status"}
MISSING = {"", "none", "nan", "null", "<na>"}
SCHEMA_VERSION = "ep24-reprocessed-view/0.1"

# The exporter keys `record_counts` by full country name; dashboards and issues usually name the
# country by ISO code. A mismatch between the two shapes must never be read as "country absent".
COUNTRY_ALIASES = {
    "fi": ("fi", "finland"),
    "pl": ("pl", "poland"),
    "pt": ("pt", "portugal"),
}

#: The EP24 exporter moves any cell longer than its text threshold out of the row CSV into
#: ``<country>_text.jsonl.gz``, keyed by the same ``record_id`` the CSV row carries.
BUNDLE_SUFFIX = "_text.jsonl.gz"


def text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    value = str(value).strip()
    return "" if value.lower() in MISSING else value


def unpack(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    string = text(value)
    if not string:
        return None
    if string.startswith(("{", "[")):
        try:
            return json.loads(string)
        except (ValueError, TypeError):
            pass
    return string


def identity(row: Mapping[str, Any]) -> str:
    """Namespace the row so identical video IDs in different countries never join."""
    namespace = "|".join(text(row.get(k)).casefold() for k in
                         ("dataset", "country", "source_type"))
    native = next((text(row.get(k)) for k in
                   ("_storage_id", "video_id", "source_url", "allas_filename")
                   if text(row.get(k))), "")
    if not native:
        # Mark, but do not merge unrelated records with missing IDs.
        return ""
    return namespace + "|" + native


def status(row: Mapping[str, Any], stage: int, *, rdf_available: bool = False) -> str:
    if stage == 9:
        return "available" if rdf_available else "unavailable"
    if stage == 0:
        return "available" if text(row.get("video_id")) and text(row.get("allas_filename")) else "incomplete"
    key = STATUS_FIELDS.get(stage)
    if key and text(row.get(key)):
        val = text(row[key]).lower()
        if any(x in val for x in ("error", "fail")):
            return "error"
        if "retry" in val or "reprocess" in val:
            return "retry"
        if val in {"ok", "complete", "completed", "success", "analyzed", "done"}:
            return "complete"
        if val in {"skipped", "deleted", "delete"}:
            return "skipped"
        return val
    if any(text(row.get(k)) for k in STAGES[stage][1]):
        return "output present (status unknown)"
    return "unavailable"


def read_records(root: str | Path) -> pd.DataFrame:
    """Read CSV/JSONL/SQLite exports from a private directory, without network access."""
    root = Path(root)
    for folder in (root, root / "data"):
        for filename in ("combined.csv", "finland.csv", "poland.csv", "portugal.csv",
                         "records.jsonl", "records.csv"):
            path = folder / filename
            if path.is_file():
                if path.suffix == ".jsonl":
                    return pd.read_json(path, lines=True)
                return pd.read_csv(path, low_memory=False)
        for filename in ("ep24.sqlite3", "visualization.sqlite3"):
            path = folder / filename
            if path.is_file():
                import sqlite3
                with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as conn:
                    names = {x[0] for x in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'")}
                    for table in ("combined", "records", "annotations"):
                        if table in names:
                            return pd.read_sql_query(f'SELECT * FROM "{table}"', conn)
    return pd.DataFrame()



def read_dna_children(root: str | Path, parents: list[Mapping[str, Any]]
                      ) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Read producer DNA child CSVs without inventing parent identities."""
    root = Path(root)
    aliases = {"fi": "finland", "pl": "poland", "pt": "portugal"}
    def country(value: Any) -> str:
        raw = text(value).lower()
        return aliases.get(raw, raw)

    # Keyed by identifier value only: a child's ``source_record_id`` *is* the parent's
    # ``_storage_id`` on the real export, so including the field name would orphan every statement.
    index: dict[tuple[str, str], set[int]] = {}
    for number, row in enumerate(parents):
        for key in ("_storage_id", "source_record_id"):
            value = text(row.get(key))
            if value:
                index.setdefault((country(row.get("country")), value), set()).add(number)

    result: list[dict[str, Any]] = []
    counts = {"read": 0, "matched": 0, "orphan": 0, "ambiguous": 0, "duplicate": 0}
    seen: set[tuple[str, str, str]] = set()
    for name in ("finland", "poland", "portugal"):
        source = next((folder / "children" / f"{name}_dna_statements.csv"
                       for folder in (root, root / "data")
                       if (folder / "children" / f"{name}_dna_statements.csv").is_file()), None)
        if source is None:
            continue
        for item in pd.read_csv(source, dtype=str, keep_default_na=False).to_dict("records"):
            counts["read"] += 1
            matches: set[int] = set()
            for key in ("_storage_id", "source_record_id"):
                value = text(item.get(key))
                if value:
                    matches.update(index.get((name, value), set()))
            if not matches:
                counts["orphan"] += 1
                continue
            if len(matches) > 1:
                counts["ambiguous"] += 1
                continue
            parent = parents[next(iter(matches))]
            document = identity(parent)
            if not document:
                counts["orphan"] += 1
                continue
            statement = text(item.get("statement_id"))
            if statement:
                marker = (name, document, statement)
                if marker in seen:
                    counts["duplicate"] += 1
                    continue
                seen.add(marker)
            result.append({"document": document, "country": name, **item})
            counts["matched"] += 1
    return result, counts


def _dicts(value: Any) -> list[dict[str, Any]]:
    """A list of dicts out of a JSON cell, a list, or a dict that holds the list."""
    parsed = unpack(value)
    if isinstance(parsed, dict):
        parsed = next((part for part in parsed.values() if isinstance(part, list)), [])
    return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []


def record_key(row: Mapping[str, Any]) -> str:
    """The producer's own row key when the export carries one, else our namespaced identity.

    The EP24 exporter writes ``record_id`` into every index row and keys its text bundles by the same
    value, so the bundle can be read without guessing at identity rules.
    """
    return text(row.get("record_id")) or identity(row)


def _country_aliases(country: str) -> set[str]:
    folded = country.casefold()
    return set(next((aliases for aliases in COUNTRY_ALIASES.values() if folded in aliases), (folded,)))


#: ``{path: (mtime_ns, size, field): {record_id: parsed value}}``. A bundle is hundreds of megabytes
#: through gzip, so it is scanned once per process; the key carries the file's identity, which means a
#: swapped export invalidates the entry instead of serving the previous corpus.
_BUNDLE_MEMO: dict[tuple[str, int, int, str], dict[str, list[dict[str, Any]]]] = {}


def bundle_files(root: str | Path) -> list[Path]:
    """``<country>_text.jsonl.gz``: where the exporter puts cells too long for the row CSV."""
    root = Path(root).resolve()
    return sorted(path for folder in (root, root / "data") if folder.is_dir()
                  for path in folder.glob(f"*{BUNDLE_SUFFIX}") if path.is_file())


def read_bundle_field(root: str | Path, field: str,
                      countries: Iterable[str] | None = None) -> dict[str, list[dict[str, Any]]]:
    """``record_id`` → parsed ``field`` from the text bundles, limited to ``countries`` when given.

    The exporter moves every cell longer than its 1,000-character threshold out of ``combined.csv``
    into these bundles, so a reader that opens only the CSV cannot see a full statement list at all.
    """
    wanted = {alias for country in (countries or ()) for alias in _country_aliases(country)}
    found: dict[str, list[dict[str, Any]]] = {}
    for path in bundle_files(root):
        if wanted and path.name[: -len(BUNDLE_SUFFIX)].casefold() not in wanted:
            continue
        stat = path.stat()
        memo_key = (str(path), stat.st_mtime_ns, stat.st_size, field)
        if memo_key not in _BUNDLE_MEMO:
            scanned: dict[str, list[dict[str, Any]]] = {}
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        payload = json.loads(line)
                    except ValueError:
                        continue
                    key = text(payload.get("record_id"))
                    entries = _dicts(payload.get(field))
                    if key and entries:
                        scanned[key] = entries
            _BUNDLE_MEMO[memo_key] = scanned
        found.update(_BUNDLE_MEMO[memo_key])
    return found


@dataclass(frozen=True)
class DNAEvidence:
    """DNA statements for the current selection, and which export carrier supplied them."""

    items: tuple[dict[str, Any], ...] = ()
    source: str = "row cells"
    records: int = 0
    counts: Mapping[str, int] = field(default_factory=dict)

    @property
    def statements(self) -> int:
        return len(self.items)


def dna_evidence(records: Sequence[Mapping[str, Any]], root: str | Path) -> DNAEvidence:
    """Step 7 statements for these records, from the export's own carriers, best first.

    1. **text bundle** — same unit as the export (one entry per exported row) and exact: the producer
       moved the long cells there, so this is the only carrier that sees every statement;
    2. **child tables** — the normalized fallback, joined by :func:`read_dna_children`, which reports
       orphans and ambiguity instead of attributing them to a listed record;
    3. **row cells** — only what survived the producer's 1,000-character text threshold.
    """
    countries = {text(row.get("country")) for row in records} - {""}
    bundle = read_bundle_field(root, "dna_statements_json", countries)
    items = [{"document": identity(row), **statement}
             for row in records if record_key(row) in bundle
             for statement in bundle[record_key(row)] if identity(row)]
    if items:
        return DNAEvidence(tuple(items), "text bundle", len({item["document"] for item in items}))

    found, counts = read_dna_children(root, list(records))
    if counts.get("read"):
        return DNAEvidence(tuple(found), "children tables",
                           len({item["document"] for item in found}), counts)

    cells = [{"document": identity(row), **statement}
             for row in records for statement in _dicts(row.get("dna_statements_json"))
             if identity(row)]
    return DNAEvidence(tuple(cells), "row cells", len({item["document"] for item in cells}))


def rdf_files(root: str | Path) -> list[Path]:
    root = Path(root).resolve()
    if not root.exists():
        return []
    return sorted(p for p in root.rglob("*") if p.is_file() and
                  p.suffix.lower() in {".nt", ".ttl"} and
                  p.name in {"graph.nt", "graph.ttl"})


def rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    return [
        {
            key: (None if value is pd.NA or (isinstance(value, float) and pd.isna(value))
                  else value)
            for key, value in record.items()
        }
        for record in frame.to_dict("records")
    ]


@dataclass(frozen=True)
class Graph:
    nodes: tuple[dict[str, Any], ...]
    edges: tuple[dict[str, Any], ...]
    warnings: tuple[str, ...]


def multilayer(records: list[Mapping[str, Any]], max_records: int = 1000,
               max_edges: int = 2500) -> Graph:
    """Typed graph; all links trace to source rows; no inferred social relations."""
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    if len(records) > max_records:
        warnings.append(f"Limited to first {max_records} filtered records")
    def node(identifier: str, kind: str, label: str, source: str) -> None:
        nodes.setdefault(identifier, {"id": identifier, "type": kind,
                                       "label": label, "source": source})
    def link(source: str, target: str, kind: str, doc: str, evidence: str = "",
             field: str = "") -> None:
        if len(edges) >= max_edges:
            return
        digest = hashlib.sha256(json.dumps([source, target, kind, doc, evidence],
                                           ensure_ascii=False).encode()).hexdigest()[:20]
        edges.setdefault(digest, {"id": digest, "source": source, "target": target,
                                  "type": kind, "document": doc,
                                  "evidence": evidence, "field": field})
    for row in records[:max_records]:
        doc = identity(row)
        if not doc:
            warnings.append("Omitted record without stable source identifier")
            continue
        document = "video:" + doc
        node(document, "document", text(row.get("video_id")) or doc, doc)
        # Only explicitly exported postprocess labels, no topic -> political stance inference.
        for key, kind in (("postprocess_entities", "actor"),
                          ("postprocess_themes", "concept")):
            items = unpack(row.get(key))
            if isinstance(items, str):
                items = [items]
            for item in items if isinstance(items, list) else []:
                label = text(item.get("canonical_name") or item.get("name") or item.get("label")) if isinstance(item, dict) else text(item)
                if not label:
                    continue
                ident = kind + ":" + hashlib.sha256(label.casefold().encode()).hexdigest()[:20]
                node(ident, kind, label, doc)
                link(document, ident, "extracted_from", doc, field=key)
        statements = unpack(row.get("dna_statements_json"))
        if isinstance(statements, dict):
            statements = statements.get("statements", [])
        for index, st in enumerate(statements if isinstance(statements, list) else []):
            if not isinstance(st, dict):
                continue
            actor = text(st.get("actor_id") or st.get("organization") or st.get("actor"))
            concept = text(st.get("concept_id") or st.get("concept"))
            if not actor or not concept:
                continue
            sid = text(st.get("statement_id")) or f"{doc}:{index}"
            sid = "statement:" + sid
            actor_id = "actor:" + hashlib.sha256(actor.casefold().encode()).hexdigest()[:20]
            concept_id = "concept:" + hashlib.sha256(concept.casefold().encode()).hexdigest()[:20]
            node(sid, "dna_statement", sid, doc)
            node(actor_id, "actor", actor, doc)
            node(concept_id, "concept", concept, doc)
            quote = text(st.get("evidence_quote"))
            link(document, sid, "statement_evidence", doc, quote, "dna_statements_json")
            link(sid, actor_id, "statement_actor", doc, quote, "dna_statements_json")
            link(sid, concept_id, "statement_concept", doc, quote, "dna_statements_json")
        social = unpack(row.get("sna_edges_json"))
        if isinstance(social, dict):
            social = social.get("edges", [])
        for st in social if isinstance(social, list) else []:
            if not isinstance(st, dict):
                continue
            actor = text(st.get("source_actor_id") or st.get("source_actor"))
            target = text(st.get("target_actor_id") or st.get("target_actor"))
            quote = text(st.get("evidence_quote"))
            relation = text(st.get("relation_type"))
            if not all((actor, target, quote, relation)):
                continue
            a = "actor:" + hashlib.sha256(actor.casefold().encode()).hexdigest()[:20]
            b = "actor:" + hashlib.sha256(target.casefold().encode()).hexdigest()[:20]
            node(a, "actor", actor, doc)
            node(b, "actor", target, doc)
            link(a, b, "empirical_sna:" + relation, doc, quote, "sna_edges_json")
            link(document, a, "sna_source_evidence", doc, quote, "sna_edges_json")
    if len(edges) >= max_edges:
        warnings.append(f"Graph capped at {max_edges} edges")
    return Graph(tuple(nodes.values()), tuple(edges.values()), tuple(warnings))

def read_manifest(root: str | Path) -> dict[str, Any]:
    """The export's own manifest, if present. An absent manifest is reported, never invented."""
    root = Path(root)
    for folder in (root, root / "data"):
        path = folder / "MANIFEST.json"
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                return {}
    return {}


def exported_counts(manifest: Mapping[str, Any]) -> dict[str, int]:
    """Exported record count per ISO country code, tolerant of both manifest key styles.

    Returns an empty mapping when the manifest carries no ``record_counts`` at all: an absent
    count is not evidence that a country is missing from the export.
    """
    counts = manifest.get("record_counts") or {}
    if not isinstance(counts, Mapping) or not counts:
        return {}
    totals: dict[str, int] = {}
    for iso, aliases in COUNTRY_ALIASES.items():
        total = 0
        for key in aliases:
            entry = counts.get(key)
            if isinstance(entry, Mapping):
                total = int(entry.get("exported") or 0)
                break
            if isinstance(entry, int | float):
                total = int(entry)
                break
        totals[iso] = total
    return totals


def missing_countries(manifest: Mapping[str, Any]) -> list[str]:
    """ISO codes the manifest positively reports as having no exported records."""
    totals = exported_counts(manifest)
    return [iso for iso in COUNTRY_ALIASES if iso in totals and not totals[iso]]


def coverage_rows(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    """One row per country and stage: how many records carry it, and out of how many.

    A denominator of zero means the country has no exported records, not that the stage is empty.
    An ``unavailable`` stage is marked as such rather than rendered as 0 %.
    """
    rows_out: list[dict[str, Any]] = []
    counts = manifest.get("record_counts") or {}
    coverage = manifest.get("stage_coverage") or {}
    unavailable = {country: set(data.get("stage_unavailable") or ())
                   for country, data in (manifest.get("inputs") or {}).items()
                   if isinstance(data, Mapping)}
    for country, stages in coverage.items():
        denominator = 0
        if isinstance(counts.get(country), Mapping):
            denominator = int(counts[country].get("exported") or 0)
        profile = (manifest.get("inputs", {}).get(country) or {}).get("profile", "reprocessed")
        for stage, data in stages.items():
            records = int((data or {}).get("records") or 0)
            missing = stage in unavailable.get(country, set())
            rows_out.append({
                "country": country, "profile": profile, "stage": stage,
                "records": records, "denominator": denominator,
                "coverage_pct": None if missing or not denominator
                else round(100 * records / denominator, 1),
                "availability": "unavailable in this source" if missing else
                ("no records" if not records else "present"),
            })
    return rows_out

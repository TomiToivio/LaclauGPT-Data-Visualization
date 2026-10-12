"""Read-only, evidence-preserving projections for reprocessed EP24 Steps 0–9.

Field names match LaclauGPT-Multimodal-Analysis/ep24_stage_contract.py
(2026-10-12). No inference or model execution occurs here.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

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


def rdf_files(root: str | Path) -> list[Path]:
    root = Path(root).resolve()
    if not root.exists():
        return []
    return sorted(p for p in root.rglob("*") if p.is_file() and
                  p.suffix.lower() in {".nt", ".ttl"} and
                  p.name in {"graph.nt", "graph.ttl"})


def rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [{key: (None if value is pd.NA or (isinstance(value, float) and pd.isna(value)) else value)\n             for key, value in record.items()} for record in frame.to_dict("records")] if not frame.empty else []


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

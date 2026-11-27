"""Build the public demo bundle a copied AI26 dashboard runs from (issue #342).

The development dashboard reads the private database. A copy on a public server must not: it
cannot reach that database, must not hold credentials, and must not show row-level material the
study has not approved. This script produces the one artefact such a copy needs:

    records.jsonl   canonical-shaped records, reduced to an explicit allowlist of fields
    graph.json      optional AnalyticalGraph export (DNA/SNA layers), if one is published
    manifest.json   counts, source window, as-of timestamp, code revision and sha256 per file
    README.md       what the bundle is and what it deliberately does not contain

Two modes, and the safe one is the default:

- ``--synthetic`` (default) writes a small invented dataset. It proves the packaging and lets a
  copy be smoke-tested before any real data is approved.
- ``--from-mongo --approve-scope`` reads the private store. The second flag is not ceremony: it is
  the operator recording that Tomi approved this exact data scope for public release.

What never leaves the private side, regardless of flags: the raw capture payload, provenance
internals, review state, native ids, Mongo ids, credentials, endpoints and any media reference.
Every emitted record keeps ``source_url`` — the canonical identity — and its timestamps, because
without them nothing on the dashboard can be dated or traced.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

#: Record fields a public demo may show. Everything else is dropped, not blanked: a key that is
#: absent cannot be re-enabled by a later change in a UI layer.
ALLOWED_SOURCE = (
    "platform",
    "author",
    "author_fullname",
    "created_at",
    "language",
    "arena",
    "title",
)
ALLOWED_CONTENT = ("title", "text", "language")
ALLOWED_ANALYSIS = (
    "summary",
    "topics",
    "themes",
    "formations",
    "nodal_points",
    "empty_signifier_candidates",
    "floating_signifiers",
    "equivalence_chains",
    "difference_chains",
    "antagonisms",
    "frontiers",
    "entities",
    "entity_mentions",
    "signifiers",
    "relations",
    "collective_subjects",
    "imaginaries",
    "affects",
    "stances",
    "sentiments",
    "uncertainty",
    "abstentions",
    "status",
)


def _pick(source: Mapping[str, Any], keys: Sequence[str]) -> dict[str, Any]:
    """The allowlisted, non-empty subset of ``source``."""
    return {key: source[key] for key in keys if source.get(key) not in (None, "", [], {})}


def public_record(document: Mapping[str, Any]) -> dict[str, Any] | None:
    """Reduce one stored record to the public demo shape, or drop it.

    A record without ``source_url`` is not a record the dashboard can identify, so it is dropped
    rather than emitted with a made-up key.
    """
    nested = document.get("result")
    record: Mapping[str, Any] = nested if isinstance(nested, Mapping) else document
    source_url = str(record.get("source_url") or "").strip()
    if not source_url:
        return None
    source = record.get("source")
    content = record.get("content")
    analysis = record.get("analysis")
    source = source if isinstance(source, Mapping) else {}
    content = content if isinstance(content, Mapping) else {}
    analysis = analysis if isinstance(analysis, Mapping) else {}
    out: dict[str, Any] = {
        "schema_version": str(record.get("schema_version") or ""),
        "source_url": source_url,
        "project_id": str(record.get("project_id") or ""),
        "source": _pick(source, ALLOWED_SOURCE),
        "content": _pick(content, ALLOWED_CONTENT),
        "analysis": _pick(analysis, ALLOWED_ANALYSIS),
    }
    if not out["content"].get("text") and not out["content"].get("title"):
        # A demo exists to show documents; a row with neither a title nor text renders as an empty
        # card and invites the reader to conclude the corpus is empty.
        return None
    return out


def _synthetic() -> list[dict[str, Any]]:
    """Three invented records that exercise every view without describing anyone real."""
    rows = [
        {
            "source_url": "https://example.invalid/demo/elite-1",
            "source": {
                "platform": "web",
                "author": "Synthetic lab",
                "created_at": "2026-11-01T09:00:00+00:00",
                "language": "en",
                "arena": "elites",
                "title": "Synthetic frontier-lab statement",
            },
            "content": {
                "title": "Synthetic frontier-lab statement",
                "text": "A synthetic statement about pacing, evaluation and deployment.",
                "language": "en",
            },
            "analysis": {
                "summary": "Synthetic summary for the public demo.",
                "formations": ["ai safety"],
                "signifiers": [{"object_id": "safety", "label": "safety"}],
                "topics": [{"topic_id": "t1", "label": "evaluation"}],
                "entities": [{"entity_id": "e1", "label": "Synthetic lab"}],
                "status": "ok",
            },
        },
        {
            "source_url": "https://example.invalid/demo/grassroots-1",
            "source": {
                "platform": "mastodon",
                "author": "Synthetic organiser",
                "created_at": "2026-11-02T12:30:00+00:00",
                "language": "en",
                "arena": "grassroots",
                "title": "Synthetic labour statement",
            },
            "content": {
                "title": "Synthetic labour statement",
                "text": "A synthetic statement about automation, consent and bargaining.",
                "language": "en",
            },
            "analysis": {
                "summary": "Synthetic summary for the public demo.",
                "formations": ["ai critical"],
                "signifiers": [{"object_id": "labour", "label": "labour"}],
                "entities": [{"entity_id": "e2", "label": "Synthetic union"}],
                "status": "ok",
            },
        },
        {
            "source_url": "https://example.invalid/demo/parliament-1",
            "source": {
                "platform": "rss",
                "author": "Synthetic committee",
                "created_at": "2026-11-03T08:15:00+00:00",
                "language": "en",
                "arena": "parliamentary",
                "title": "Synthetic committee release",
            },
            "content": {
                "title": "Synthetic committee release",
                "text": "A synthetic release about oversight, liability and public procurement.",
                "language": "en",
            },
            "analysis": {
                "summary": "Synthetic summary for the public demo.",
                "formations": ["ai safety"],
                "relations": [
                    {
                        "relation_id": "r1",
                        "source_ref": "e3",
                        "target_ref": "liability",
                        "relation_type": "articulation",
                    }
                ],
                "entities": [{"entity_id": "e3", "label": "Synthetic committee"}],
                "status": "ok",
            },
        },
    ]
    for row in rows:
        row.update({"schema_version": "1.0.0", "project_id": "ai26"})
    return [row for row in rows if row["source_url"]]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _revision() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def write_bundle(
    records: Iterable[Mapping[str, Any]],
    output_dir: str | Path,
    *,
    as_of: str | None = None,
    graph: Mapping[str, Any] | None = None,
    source_label: str = "synthetic",
) -> dict[str, Any]:
    """Write ``records.jsonl``, optional ``graph.json``, ``manifest.json`` and ``README.md``."""
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    kept: list[dict[str, Any]] = []
    dropped = 0
    for document in records:
        row = public_record(document)
        if row is None:
            dropped += 1
            continue
        kept.append(row)
    if not kept:
        raise ValueError("no record survived the public allowlist; refusing to write an empty demo")

    records_path = target / "records.jsonl"
    records_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in kept),
        encoding="utf-8",
    )
    files = {"records.jsonl": _sha256(records_path)}
    if graph is not None:
        graph_path = target / "graph.json"
        graph_path.write_text(
            json.dumps(graph, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
        )
        files["graph.json"] = _sha256(graph_path)

    stamps = sorted(
        str(row["source"].get("created_at") or "")
        for row in kept
        if row["source"].get("created_at")
    )
    manifest = {
        "bundle_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "data_as_of": as_of or (stamps[-1] if stamps else ""),
        "source": source_label,
        "code_revision": _revision(),
        "records": len(kept),
        "dropped_records": dropped,
        "platforms": sorted({str(row["source"].get("platform") or "unknown") for row in kept}),
        "arenas": sorted({str(row["source"].get("arena") or "unknown") for row in kept}),
        "files": files,
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (target / "README.md").write_text(_readme(manifest), encoding="utf-8")
    return manifest


def _readme(manifest: Mapping[str, Any]) -> str:
    return (
        "# AI26 dashboard demo bundle\n\n"
        f"- source: {manifest['source']}\n"
        f"- records: {manifest['records']} (dropped {manifest['dropped_records']})\n"
        f"- data as of: {manifest['data_as_of'] or 'not recorded'}\n"
        f"- generated: {manifest['generated_at']} from code revision {manifest['code_revision']}\n"
        f"- platforms: {', '.join(manifest['platforms'])}\n"
        f"- arenas: {', '.join(manifest['arenas'])}\n\n"
        "Run a copy of the dashboard against this directory with:\n\n"
        "```bash\n"
        "export LACLAUGPT_VIS_DEMO_MODE=1\n"
        "export LACLAUGPT_VIS_DEMO_BUNDLE=/srv/ai26-demo/current/records.jsonl\n"
        "export LACLAUGPT_VIS_DEMO_GRAPH=/srv/ai26-demo/current/graph.json   # if present\n"
        "export LACLAUGPT_VIS_DEMO_AS_OF='<the data-as-of value above>'\n"
        "streamlit run src/laclaugpt_visualization/ai26_dashboard.py --server.port 8504\n"
        "```\n\n"
        "This bundle contains only the allowlisted fields the public views render. It holds no raw\n"
        "capture payloads, provenance internals, review state, native ids, credentials, endpoints or\n"
        "media references. Verify a copy against `manifest.json` (sha256 per file) before serving it.\n"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="directory to write the bundle into")
    parser.add_argument("--synthetic", action="store_true", help="write the invented demo dataset")
    parser.add_argument("--from-mongo", action="store_true", help="read the private AI26 store")
    parser.add_argument(
        "--approve-scope",
        action="store_true",
        help="the study owner approved this exact data scope for public release",
    )
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--graph", help="AnalyticalGraph JSON to include (optional)")
    parser.add_argument("--as-of", default="", help="data-as-of timestamp to record")
    args = parser.parse_args(argv)

    if args.from_mongo and not args.approve_scope:
        parser.error(
            "--from-mongo requires --approve-scope: public data scope is an owner decision"
        )
    if not args.from_mongo:
        manifest = write_bundle(_synthetic(), args.output, as_of=args.as_of or "synthetic")
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0

    uri = os.environ.get("LACLAUGPT_MONGODB_URI")
    database = os.environ.get("LACLAUGPT_MONGODB_DATABASE")
    if not uri or not database:
        parser.error("LACLAUGPT_MONGODB_URI and LACLAUGPT_MONGODB_DATABASE are required")
    from pymongo import MongoClient

    graph = None
    if args.graph:
        graph = json.loads(Path(args.graph).read_text(encoding="utf-8"))
    with MongoClient(uri, serverSelectionTimeoutMS=8000) as client:
        documents = list(
            client[database]["ai26__analysis_results"].find({}, {"_id": 0}).limit(args.limit)
        )
    manifest = write_bundle(
        documents, args.output, as_of=args.as_of, graph=graph, source_label="approved AI26 export"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

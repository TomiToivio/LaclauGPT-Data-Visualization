"""Small CLI for inspecting and exporting Phase 0 analysis output."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

from .mongo import analysis_status, find_document, list_documents

LIST_FIELDS = (
    "source_date",
    "source_name",
    "actor_name",
    "arena",
    "ai_formation",
    "source_title",
    "source_url",
    "phase0.discourse.status",
)


def _json_default(value: Any) -> str:
    return str(value)


def _nested(document: dict[str, Any], dotted: str) -> Any:
    value: Any = document
    for part in dotted.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _row(document: dict[str, Any]) -> dict[str, Any]:
    row = {
        field: _nested(document, field) if "." in field else document.get(field)
        for field in LIST_FIELDS
    }
    row["analysis_status"] = analysis_status(document)
    if row["analysis_status"] == "awaiting":
        row["phase0.discourse.status"] = "awaiting analysis"
    return row


def _filters(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "status": args.status,
        "since": args.since,
        "until": args.until,
        "actor": args.actor,
        "arena": args.arena,
        "formation": args.formation,
        "language": args.language,
    }


def _print_table(documents: list[dict[str, Any]]) -> None:
    fields = (*LIST_FIELDS, "analysis_status")
    print("\t".join(fields))
    for document in documents:
        row = _row(document)
        print("\t".join(str(row.get(field) or "").replace("\t", " ") for field in fields))


def _print_json(documents: list[dict[str, Any]]) -> None:
    print(
        json.dumps(
            [_row(document) for document in documents],
            indent=2,
            ensure_ascii=False,
            default=_json_default,
        )
    )


def _clean_document(document: dict[str, Any]) -> dict[str, Any]:
    clean = {key: value for key, value in document.items() if key != "_id"}
    clean["analysis_status"] = analysis_status(document)
    if clean["analysis_status"] == "awaiting":
        phase0 = clean.setdefault("phase0", {})
        discourse = phase0.setdefault("discourse", {})
        discourse.setdefault("status", "awaiting analysis")
    return clean


def _export(documents: list[dict[str, Any]], path: Path, fmt: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "jsonl":
        with path.open("w", encoding="utf-8") as handle:
            for document in documents:
                handle.write(
                    json.dumps(
                        _clean_document(document),
                        ensure_ascii=False,
                        default=_json_default,
                    )
                    + "\n"
                )
        return
    fields = (
        *LIST_FIELDS,
        "analysis_status",
        "phase0_summary",
        "phase0_discourse",
        "phase0_ontology",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for document in documents:
            row = _row(document)
            for field in ("phase0_summary", "phase0_discourse", "phase0_ontology"):
                row[field] = json.dumps(
                    document.get(field),
                    ensure_ascii=False,
                    sort_keys=True,
                    default=_json_default,
                )
            writer.writerow(row)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="python -m laclaugpt.cli")
    sub = root.add_subparsers(dest="command", required=True)
    for name in ("list", "export"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--status", choices=("analyzed", "awaiting", "error"))
        cmd.add_argument("--since")
        cmd.add_argument("--until")
        cmd.add_argument("--actor")
        cmd.add_argument("--arena")
        cmd.add_argument("--formation")
        cmd.add_argument("--language")
        cmd.add_argument("--limit", type=int, default=50)
    list_cmd = sub.choices["list"]
    list_cmd.add_argument("--json", action="store_true", dest="as_json")
    inspect_cmd = sub.add_parser("inspect")
    inspect_cmd.add_argument("identity")
    inspect_cmd.add_argument("--json", action="store_true", dest="as_json")
    export_cmd = sub.choices["export"]
    export_cmd.add_argument("--format", choices=("jsonl", "csv"), default="jsonl")
    export_cmd.add_argument("--output", type=Path)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "inspect":
            document = find_document(args.identity)
            if document is None:
                print("document not found", file=sys.stderr)
                return 1
            clean = _clean_document(document)
            print(json.dumps(clean, indent=2, ensure_ascii=False, default=_json_default))
            return 0

        documents = list_documents(limit=args.limit, **_filters(args))
        if args.command == "list":
            if args.as_json:
                _print_json(documents)
            else:
                _print_table(documents)
            return 0

        output = args.output or Path("data/exports") / f"phase0.{args.format}"
        _export(documents, output, args.format)
        print(output)
        return 0
    except (RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

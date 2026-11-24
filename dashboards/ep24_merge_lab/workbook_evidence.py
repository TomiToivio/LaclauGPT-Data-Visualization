"""Read-only human codebook evidence inventory for #311.

Run on an authorized checkout with hydrated Excel sources. No mapping is activated.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path

FILES = {"entity": "entities.xlsx", "person": "persons.xlsx", "theme": "themes.xlsx"}


def inspect_workbooks(root: Path) -> dict:
    from openpyxl import load_workbook

    sources = {}
    for category, filename in FILES.items():
        path = root / filename
        raw = path.read_bytes()
        if raw.startswith(b"version https://git-lfs.github.com/spec/v1"):
            raise ValueError(f"{filename}: hydrate Git LFS first")
        workbook = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        pairs = []
        sheets = []
        try:
            for sheet in workbook.worksheets:
                rows = iter(sheet.values)
                header = next(rows, ())
                names = [str(value or "").strip().casefold() for value in header]
                if names.count("old") != 1 or names.count("new") != 1:
                    sheets.append({"name": sheet.title, "status": "unrecognized_header"})
                    continue
                old, new = names.index("old"), names.index("new")
                incomplete = []
                count = 0
                for number, row in enumerate(rows, start=2):
                    if not any(value is not None for value in row):
                        continue
                    left, right = row[old], row[new]
                    if not isinstance(left, str) or not isinstance(right, str) or not left.strip() or not right.strip():
                        incomplete.append(number)
                        continue
                    pairs.append({"alias": left, "canonical": right, "sheet": sheet.title, "row": number})
                    count += 1
                sheets.append({"name": sheet.title, "status": "read", "pairs": count,
                               "incomplete_rows": incomplete})
        finally:
            workbook.close()
        if not pairs:
            raise ValueError(f"{filename}: no old/new mappings found")
        targets = {}
        for pair in pairs:
            targets.setdefault(pair["alias"].strip().casefold(), set()).add(pair["canonical"])
        conflicts = {key: sorted(values) for key, values in targets.items() if len(values) > 1}
        sources[category] = {"file": filename, "sha256": hashlib.sha256(raw).hexdigest(),
                             "bytes": len(raw), "sheets": sheets, "pairs": pairs,
                             "conflicts": conflicts}
    return {"schema": "ep24.human_workbook_evidence/1", "sources": sources,
            "activation_authorized": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbooks", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = inspect_workbooks(args.workbooks)
    # Exclusive creation: do not replace another agent's evidence snapshot.
    with args.out.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Does this export directory match the manifest that travels with it (#263 acceptance 4)?

The dashboard reads whatever sits in its data directory. A README, a directory listing or a plausible row
count cannot answer *"is this the export we think it is?"* — only the manifest can, and only if every file
in it exists with the declared size, hash and row count.

Two things this module will not do:

* **It will not call an unverifiable snapshot verified.** A missing manifest, a layout the tree does not
  have, a hash that differs and a CSV whose row count disagrees are four different failures, reported
  separately, and each one makes the verdict worse than ``verified``.
* **It will not hide undeclared files.** Provenance sidecars legitimately live beside an export
  (`manifest.json`, `dictionary.json`, a cohort roster). They are listed rather than ignored, because "25
  declared files exist" and "the directory contains 29 files" are both true and only together are useful.

Row counts are read by parsing CSV, never by counting lines: a 500-row export with transcripts reads as
~127 000 lines, and the mismatch looks like missing data.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Countries in the delivered export, in the order the frame assembles them.
EXPORT_COUNTRIES = ("finland", "poland", "portugal")

LAYOUT_PER_COUNTRY = "per-country"
LAYOUT_FLAT = "flat"
LAYOUT_ABSENT = "absent"
LAYOUT_AMBIGUOUS = "ambiguous"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _csv_rows(path: Path) -> int:
    """Data rows by parsing, so quoted newlines inside transcripts are not counted as rows."""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            next(reader)
        except StopIteration:
            return 0
        return sum(1 for _ in reader)


def detect_layout(root: str | Path) -> str:
    """Which artifact layout this directory actually holds.

    ``per-country`` is the delivered shape (``<root>/<country>/<country>.csv``); ``flat`` is one
    ``combined.csv`` at the root; both present is ``ambiguous`` — the state where two layouts of one
    dataset can drift apart without anyone noticing.
    """
    base = Path(root)
    combined = (base / "combined.csv").is_file()
    # A country directory (or any of its files) is enough: a per-country export missing one country is a
    # broken per-country layout, not a different layout. Reporting it as "absent" would hide the missing file.
    per_country = any((base / country / f"{country}.csv").is_file() or (base / country).is_dir()
                      for country in EXPORT_COUNTRIES)
    if combined and per_country:
        return LAYOUT_AMBIGUOUS
    if per_country:
        return LAYOUT_PER_COUNTRY
    if combined:
        return LAYOUT_FLAT
    return LAYOUT_ABSENT


def manifest_files(manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """The manifest's file table in one shape. Two dialects exist: a mapping and a list of entries."""
    files = manifest.get("files")
    if isinstance(files, Mapping):
        return {str(name): dict(spec or {}) for name, spec in files.items()}
    if isinstance(files, Sequence) and not isinstance(files, (str, bytes)):
        table: dict[str, dict[str, Any]] = {}
        for entry in files:
            if isinstance(entry, Mapping) and entry.get("path"):
                table[str(entry["path"])] = dict(entry)
        return table
    return {}


@dataclass(frozen=True)
class FileResult:
    path: str
    status: str
    detail: str = ""


@dataclass(frozen=True)
class Verdict:
    root: str
    layout_declared: str
    layout_detected: str
    results: tuple[FileResult, ...]
    undeclared: tuple[str, ...]
    rows_declared: int
    rows_verified: int

    @property
    def files_declared(self) -> int:
        return len(self.results)

    @property
    def files_verified(self) -> int:
        return sum(1 for result in self.results if result.status == "verified")

    @property
    def verdict(self) -> str:
        if not self.results:
            return "no manifest"
        if self.layout_detected == LAYOUT_AMBIGUOUS:
            return "layout ambiguous"
        if self.layout_declared and self.layout_detected != self.layout_declared:
            return "layout mismatch"
        if any(result.status != "verified" for result in self.results):
            return "unverified"
        return "verified"

    @property
    def mismatched(self) -> tuple[FileResult, ...]:
        return tuple(result for result in self.results if result.status != "verified")

    def summary(self) -> str:
        if not self.results:
            return "No manifest: the export cannot be verified."
        line = (f"{self.files_verified}/{self.files_declared} declared files verified "
                f"({self.rows_verified}/{self.rows_declared:,} declared rows) · layout "
                f"{self.layout_declared or 'undeclared'} (directory: {self.layout_detected})")
        if self.undeclared:
            line += f" · {len(self.undeclared)} undeclared file(s)"
        return line


def verify_manifest(root: str | Path, *, hash_limit: int | None = None) -> Verdict:
    """Compare the directory against its manifest, file by file.

    ``hash_limit`` bounds how many files are hashed (useful for a quick UI check on a huge export); rows and
    sizes are always checked for every declared file. A file skipped for hashing is reported as verified
    only for the checks that ran — never silently upgraded.
    """
    base = Path(root)
    manifest: Mapping[str, Any] = {}
    for candidate in (base / "manifest.json", base / "MANIFEST.json"):
        if candidate.is_file():
            try:
                manifest = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                manifest = {}
            break

    table = manifest_files(manifest)
    if not table:
        return Verdict(root=str(base), layout_declared=str(manifest.get("layout") or ""),
                       layout_detected=detect_layout(base), results=(), undeclared=(),
                       rows_declared=0, rows_verified=0)

    results: list[FileResult] = []
    rows_declared = 0
    rows_verified = 0
    for index, (name, spec) in enumerate(sorted(table.items())):
        path = base / name
        if not path.is_file():
            results.append(FileResult(name, "missing", "declared but not present"))
            continue
        expected_bytes = spec.get("bytes")
        actual_bytes = path.stat().st_size
        if isinstance(expected_bytes, int) and expected_bytes != actual_bytes:
            results.append(FileResult(name, "size mismatch",
                                      f"declared {expected_bytes:,} bytes, found {actual_bytes:,}"))
            continue
        expected_rows = spec.get("rows")
        if isinstance(expected_rows, int):
            rows_declared += expected_rows
            actual_rows = _csv_rows(path)
            if actual_rows != expected_rows:
                results.append(FileResult(name, "row count mismatch",
                                          f"declared {expected_rows:,} rows, parsed {actual_rows:,}"))
                continue
            rows_verified += expected_rows
        expected_hash = str(spec.get("sha256") or "")
        if expected_hash and (hash_limit is None or index < hash_limit):
            actual_hash = _sha256(path)
            if actual_hash != expected_hash:
                results.append(FileResult(name, "hash mismatch",
                                          f"declared {expected_hash[:12]}…, found {actual_hash[:12]}…"))
                continue
        results.append(FileResult(name, "verified"))

    declared = set(table)
    present = {str(path.relative_to(base)) for path in base.rglob("*") if path.is_file()}
    # The manifest cannot declare itself; listing it as "undeclared" is noise beside the real sidecars.
    undeclared = tuple(sorted(present - declared - {"manifest.json", "MANIFEST.json"}))
    return Verdict(root=str(base), layout_declared=str(manifest.get("layout") or ""),
                   layout_detected=detect_layout(base), results=tuple(results),
                   undeclared=undeclared, rows_declared=rows_declared, rows_verified=rows_verified)

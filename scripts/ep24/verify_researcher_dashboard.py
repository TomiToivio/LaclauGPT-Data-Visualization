#!/usr/bin/env python3
"""Verify the EP24 researcher dashboard deployment (issue #242).

The issue's definition of done asks for facts about the *running* service: the served commit, the data
manifest and version, the cohort counts, the stage coverage, and that a researcher can reach it. This
script answers those questions from the files and the process, not from the badge on a pull request.

    python scripts/ep24/verify_researcher_dashboard.py \
        --data-root /path/to/live_steps_1_7 \
        --served-dir /path/to/served/checkout \
        --url http://100.115.95.109:8502

Each check prints PASS/FAIL with the evidence it used; the exit status is the number of failures, so
it can gate a deployment. `--json` prints the same facts as a single object.

Read-only: it opens the CSV to read a header, never the rows, and it never writes to the artifact
directory.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from laclaugpt_visualization.researcher_export import (
    UnclassifiedColumnError,
    classify,
    served_commit,
)

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"


def check(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"check": name, "status": STATUS_PASS if ok else STATUS_FAIL, "detail": detail}


def _header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return next(csv.reader(handle))


#: Outcome keys that mean "this stage produced an output for this record".
_PRESENT_OUTCOMES = {"ok", "output_present", "cached", "success", "complete", "completed", "present"}


def normalise_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Add the totals and coverage keys the checks read, from either exporter's dialect.

    Two manifests exist in this project: the artifact builder's (``records``, ``record_counts``,
    ``stage_coverage``) and the checkpoint exporter's (``countries[].exported_videos``,
    ``countries[].stages`` with per-outcome counts). The verifier reads one shape; normalising here
    keeps that single shape without pretending the two files are identical.
    """
    normalised = dict(manifest)
    countries = manifest.get("countries") or {}
    if not isinstance(countries, dict):
        countries = {}
    counts = manifest.get("record_counts")
    if not isinstance(counts, dict) or not counts:
        per_country = {}
        for country, data in countries.items():
            if not isinstance(data, dict):
                continue
            exported = data.get("exported_videos", data.get("exported", data.get("input_rows")))
            if isinstance(exported, int):
                per_country[country] = {"exported": exported}
        if per_country:
            per_country["exported_total"] = sum(v["exported"] for v in per_country.values())
            normalised["record_counts"] = per_country
            normalised.setdefault("records", per_country["exported_total"])

    if not manifest.get("stage_coverage"):
        coverage = {}
        for country, data in countries.items():
            if not isinstance(data, dict):
                continue
            stages = data.get("stages") or data.get("coverage") or {}
            if not isinstance(stages, dict):
                continue
            entries = {}
            for step, outcome in stages.items():
                if isinstance(outcome, dict):
                    # A stage's dict counts *outcomes* (ok, cached, error, not_exported). Summing
                    # them reports 500 for a stage that produced nothing, which is precisely how a
                    # missing stage gets disguised as a complete one. Count what exists.
                    present = sum(
                        value for key, value in outcome.items()
                        if isinstance(value, int) and str(key).lower() in _PRESENT_OUTCOMES
                    )
                    if not any(str(key).lower() in _PRESENT_OUTCOMES for key in outcome):
                        # No outcome key names a produced output: a stage whose only outcome is
                        # "not_exported" produced nothing. A total-ish key still counts.
                        present = next((outcome[key] for key in ("records", "total", "count", "exported")
                                        if isinstance(outcome.get(key), int)), 0)
                    entries[str(step)] = {"records": present,
                                          "outcomes": {str(k): v for k, v in outcome.items()
                                                       if isinstance(v, int)}}
                else:
                    entries[str(step)] = {"records": outcome}
            if entries:
                coverage[country] = entries
        if coverage:
            normalised["stage_coverage"] = coverage
    return normalised


def check_manifest(data_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The manifest exists, parses, and its totals agree with its own per-country counts."""
    manifest_path = next((data_root / name for name in ("MANIFEST.json", "manifest.json")
                          if (data_root / name).is_file()), data_root / "MANIFEST.json")
    if not manifest_path.is_file():
        return {}, [check("manifest", False, f"missing {manifest_path}")]
    try:
        manifest = normalise_manifest(json.loads(manifest_path.read_text(encoding="utf-8")))
    except json.JSONDecodeError as error:
        return {}, [check("manifest", False, f"unreadable JSON: {error}")]

    provenance_block = manifest.get("provenance") if isinstance(manifest.get("provenance"), dict) else {}
    dataset = manifest.get("dataset") or provenance_block.get("dataset") or manifest.get("run") or "not named"
    results = [check("manifest", True, f"{manifest.get('contract')} · dataset {dataset}")]
    counts = manifest.get("record_counts") or {}
    per_country = {key: value.get("exported") for key, value in counts.items() if isinstance(value, dict)}
    total = counts.get("exported_total")
    summed = sum(value for value in per_country.values() if isinstance(value, int))
    results.append(
        check(
            "manifest totals agree",
            isinstance(total, int) and total == summed == manifest.get("records"),
            f"exported_total={total} sum(countries)={summed} records={manifest.get('records')}",
        )
    )
    countries = [key for key in per_country if per_country[key] is not None]
    results.append(
        check(
            "three countries exported",
            len(countries) == 3,
            ", ".join(f"{key}={per_country[key]}" for key in sorted(per_country)),
        )
    )
    return manifest, results


def _display_allowlist() -> tuple[str, ...]:
    """The researcher app's own display allowlist (#243/#245)."""
    from laclaugpt_visualization.ep24_researcher import (
        DISPLAY,
    )

    return tuple(DISPLAY)


def _classify_for(header: list[str], allowlist: str) -> tuple[list[str], list[dict[str, str]], str]:
    """Classify a header against one of the two allowlists this project actually uses.

    ``research`` is the live-steps index allowlist; ``display`` is the researcher app's DISPLAY map.
    ``auto`` prefers the former and falls back to the latter, reporting which one it used — the two
    apps serve different exports and a verifier that assumes one allowlist reports a false failure
    against the other.
    """
    if allowlist in {"auto", "research"}:
        try:
            keep, dropped = classify(header, strict=True)
            return keep, dropped, "research"
        except UnclassifiedColumnError:
            if allowlist == "research":
                raise
    display = _display_allowlist()
    keep = [column for column in display if column in header]
    dropped = [{"column": column, "reason": "not on the researcher display allowlist"}
               for column in header if column not in keep]
    return keep, dropped, "display"


#: The approved cohort's shape: the roster the export was built against (#248/#249).
ROSTER_FILE = "approved_cohort.txt"
ROSTER_COUNTS = {"finland": 500, "poland": 500, "portugal": 500}


def check_roster(data_root: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """The export's own approval record: a digest that matches, and 500 identities per country.

    A dashboard that cannot prove its rows are the approved cohort is displaying *some* cohort. The
    manifest carries the digest the export was built with; the roster beside the export must hash to
    it, or the two files describe different cohorts.
    """
    roster = Path(data_root) / ROSTER_FILE
    record = manifest.get("approved_cohort") or {}
    declared = str(record.get("sha256") or "")
    if not roster.is_file():
        return [check("approved cohort roster", False, f"missing {roster}")]
    digest = hashlib.sha256(roster.read_bytes()).hexdigest()
    results = [
        check("approved cohort roster", True, f"{roster.name} · {roster.stat().st_size} bytes"),
        check("approved cohort digest", bool(declared) and digest == declared,
              declared[:12] + (" · matches" if digest == declared else " · mismatch") if declared
              else "the manifest carries no approved_cohort.sha256"),
    ]
    counts: dict[str, int] = {}
    duplicates = 0
    seen: set[str] = set()
    for line in roster.read_text(encoding="utf-8").splitlines():
        identity = line.strip()
        if not identity:
            continue
        if identity in seen:
            duplicates += 1
        seen.add(identity)
        parts = identity.split(":")
        if len(parts) == 3:
            counts[parts[1]] = counts.get(parts[1], 0) + 1
    results.append(check("approved cohort size", len(seen) == sum(ROSTER_COUNTS.values()),
                         f"{len(seen)} identities, {duplicates} duplicates"))
    results.append(check("approved cohort by country", counts == ROSTER_COUNTS,
                         ", ".join(f"{name}={value}" for name, value in sorted(counts.items()))))
    return results


def check_artifacts(data_root: Path, manifest: dict[str, Any], *, allowlist: str = "auto"
                    ) -> list[dict[str, Any]]:
    """The CSVs the app reads exist, and their headers classify without drift."""
    results: list[dict[str, Any]] = []
    combined = data_root / "combined.csv"
    if not combined.is_file():
        return [check("combined.csv", False, f"missing {combined}")]

    header = _header(combined)
    results.append(check("combined.csv", True, f"{len(header)} columns"))

    try:
        keep, dropped, used = _classify_for(header, allowlist)
    except UnclassifiedColumnError as error:
        results.append(check("column allowlist", False, str(error)))
    else:
        results.append(
            check(
                "column allowlist",
                True,
                f"{len(keep)} researcher columns, {len(dropped)} dropped with a reason "
                f"({used} allowlist)",
            )
        )
        risky = [column for column in keep if _looks_like_backend_field(column)]
        results.append(
            check(
                "no storage or credential fields on the allowlist",
                not risky,
                ", ".join(risky) or "none",
            )
        )

    manifest_records = manifest.get("records")
    if isinstance(manifest_records, int):
        # Parse rather than count lines: transcripts contain embedded newlines inside quoted fields,
        # so a line count reports 4057 rows for a 1500-video corpus.
        with combined.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            next(reader, None)
            rows = sum(1 for row in reader if row)
        results.append(
            check("combined.csv row count", rows == manifest_records, f"{rows} rows vs manifest {manifest_records}")
        )

    # Long-form evidence ships as gzipped bundles in the artifact dialect and as per-country
    # CSV/JSONL in the checkpoint dialect; check whichever this export uses.
    if any(data_root.glob("*_text.jsonl.gz")):
        missing = [country for country in ("finland", "poland", "portugal")
                   if not (data_root / f"{country}_text.jsonl.gz").is_file()]
        results.append(check("text bundles present", not missing, ", ".join(missing) or "all three"))
    else:
        missing = [country for country in ("finland", "poland", "portugal")
                   if not (data_root / f"{country}.csv").is_file()
                   and not (data_root / f"{country}.jsonl").is_file()]
        results.append(check("country tables present", not missing, ", ".join(missing) or "all three"))
    return results


def _looks_like_backend_field(column: str) -> bool:
    """Names that must never reach a researcher, whatever the allowlist says."""
    risky = ("_storage_id", "allas_", "frame_file", "video_filename", "storage", "uri", "token",
             "password", "secret", "credential")
    return any(marker in column.lower() for marker in risky)


def _stage_count(value: Any) -> Any:
    """The number a coverage entry reports, whether it is the producer's or the builder's shape."""
    if isinstance(value, dict):
        return value.get("complete", value.get("records"))
    return value


def check_coverage(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Every country states its stage coverage, and a partial stage is visible rather than zero."""
    coverage = manifest.get("stage_coverage") or manifest.get("coverage") or {}
    if not coverage:
        countries = manifest.get("countries") or {}
        coverage = {country: value.get("coverage", {}) for country, value in countries.items()}
    results: list[dict[str, Any]] = []
    for country in sorted(coverage):
        stages = coverage[country] or {}
        measured = {
            str(step): _stage_count(value)
            for step, value in stages.items()
            if str(step)[:1].isdigit() or str(step).startswith("step")
        }
        results.append(
            check(
                f"coverage · {country}",
                bool(measured),
                ", ".join(f"{step}={count}" for step, count in sorted(measured.items())) or "no stage coverage",
            )
        )
        partial = {step: count for step, count in measured.items() if isinstance(count, int) and count == 0}
        if partial:
            results.append(
                check(
                    f"partial stages disclosed · {country}",
                    True,
                    ", ".join(sorted(partial)) + " reported as empty by the producer",
                )
            )
    return results or [check("coverage", False, "the manifest reports no stage coverage")]


def check_approved_cohort(data_root: Path, roster_path: Path) -> list[dict[str, Any]]:
    """Check exact membership against the private approved Monday500 roster.

    Count-only verification is insufficient: an arbitrary 500-row slice can pass
    while containing different videos. The cleaned country CSVs preserve the
    producer's canonical _storage_id; the serving index intentionally does not.
    Never expose these IDs in the researcher interface or exports.
    """
    countries = ("finland", "poland", "portugal")
    try:
        with roster_path.open("r", encoding="utf-8-sig") as handle:
            lines = [line.strip() for line in handle if line.strip() and not line.lstrip().startswith("#")]
    except OSError as error:
        return [check("approved roster", False, str(error))]
    approved = {country: set() for country in countries}
    for value in lines:
        parts = value.split(":", 2)
        if len(parts) != 3 or parts[0] != "monday500" or parts[1] not in approved or not parts[2]:
            return [check("approved roster", False, "invalid namespace in approved roster")]
        approved[parts[1]].add(value)
    results = [check(
        "approved roster",
        len(lines) == 1500 and all(len(approved[country]) == 500 for country in countries),
        "expected exactly 500 distinct namespaced identities per country",
    )]
    if results[0]["status"] == STATUS_FAIL:
        return results
    for country in countries:
        cleaned = data_root / "cleaned" / f"{country}_clean.csv"
        if not cleaned.is_file():
            results.append(check(f"approved membership · {country}", False, f"missing {cleaned}"))
            continue
        actual: list[str] = []
        try:
            with cleaned.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                if "_storage_id" not in (reader.fieldnames or []):
                    results.append(check(f"approved membership · {country}", False, "missing canonical _storage_id"))
                    continue
                for row in reader:
                    actual.append((row.get("_storage_id") or "").strip())
        except (OSError, csv.Error) as error:
            results.append(check(f"approved membership · {country}", False, f"unreadable CSV: {error}"))
            continue
        observed = set(actual)
        missing = len(approved[country] - observed)
        extra = len(observed - approved[country])
        duplicates = len(actual) - len(observed)
        results.append(check(
            f"approved membership · {country}",
            len(actual) == 500 and not missing and not extra and not duplicates,
            f"rows={len(actual)} missing={missing} unapproved={extra} duplicates={duplicates}",
        ))
    return results


def check_checkout(served_dir: Path | None, expected_commit: str | None) -> list[dict[str, Any]]:
    """The served directory is a git checkout, and the commit it is on is reported."""
    if served_dir is None:
        return [check("served checkout", False, "no --served-dir given")]
    commit = served_commit(served_dir)
    if commit is None:
        return [check("served checkout", False, f"{served_dir} is not a git checkout")]
    dirty = subprocess.run(
        ["git", "-C", str(served_dir), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    branch = subprocess.run(
        ["git", "-C", str(served_dir), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    results = [
        check("served commit", True, f"{commit[:7]} on {branch or 'detached HEAD'}"),
        check(
            "served tree clean",
            not dirty,
            "clean" if not dirty else f"{len(dirty.splitlines())} modified path(s); the served code is not the commit",
        ),
    ]
    if expected_commit:
        results.append(
            check(
                "served commit is the expected one",
                commit.startswith(expected_commit) or expected_commit.startswith(commit[:7]),
                f"served {commit[:7]} expected {expected_commit[:7]}",
            )
        )
    return results


def check_http(url: str | None, timeout: float = 5.0) -> list[dict[str, Any]]:
    """The service answers its health endpoint."""
    if not url:
        return [check("http health", False, "no --url given")]
    health = url.rstrip("/") + "/_stcore/health"
    try:
        with urllib.request.urlopen(health, timeout=timeout) as response:
            body = response.read().decode("utf-8", "replace").strip()
            status = response.status
    except (urllib.error.URLError, OSError) as error:
        return [check("http health", False, f"{health}: {error}")]
    return [check("http health", status == 200 and body.lower() == "ok", f"{health} -> {status} {body!r}")]


def run(args: argparse.Namespace) -> list[dict[str, Any]]:
    data_root = Path(args.data_root).expanduser()
    results = [check("artifact directory", data_root.is_dir(), str(data_root))]
    if not data_root.is_dir():
        return results
    manifest, manifest_results = check_manifest(data_root)
    results.extend(manifest_results)
    if manifest:
        # The parser carries `--approved-roster`, not `--allowlist`; the allowlist is chosen
        # automatically from the export, so the argument is only read when a caller supplies one.
        results.extend(check_artifacts(data_root, manifest,
                                       allowlist=getattr(args, "allowlist", "auto")))
        results.extend(check_coverage(manifest))
    results.extend(check_checkout(Path(args.served_dir).expanduser() if args.served_dir else None,
                                  args.expected_commit))
    roster = getattr(args, "approved_roster", None)
    if roster:
        results.extend(check_approved_cohort(data_root, Path(roster).expanduser()))
    results.extend(check_http(args.url))
    return results


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-root", required=True, type=Path,
                        help="private artifact directory the dashboard serves")
    parser.add_argument("--served-dir", type=Path, default=None,
                        help="the checkout the running service was started from")
    parser.add_argument("--url", default=None, help="dashboard base URL, e.g. http://100.115.95.109:8502")
    parser.add_argument("--expected-commit", default=None,
                        help="commit the deployment is supposed to be serving (prefix is enough)")
    parser.add_argument("--allowlist", default="auto",
                        help="allowlist to classify against: auto (default) or a named version")
    parser.add_argument("--approved-roster", type=Path, default=None,
                        help="require exact private Monday500 membership using cleaned country dataframes")
    parser.add_argument("--allowlist", choices=("auto", "research", "display"), default="auto",
                        help="which researcher allowlist the column check applies (default: auto)")
    parser.add_argument("--json", action="store_true", help="print one JSON object instead of lines")
    args = parser.parse_args(argv)

    results = run(args)
    failures = [item for item in results if item["status"] == STATUS_FAIL]
    if args.json:
        print(json.dumps({"checks": results, "failures": len(failures)}, indent=2, sort_keys=True))
    else:
        width = max(len(item["check"]) for item in results)
        for item in results:
            print(f"{item['status']:4}  {item['check']:<{width}}  {item['detail']}")
        print(f"\n{len(results) - len(failures)}/{len(results)} checks passed")
    return len(failures)


if __name__ == "__main__":
    raise SystemExit(main())

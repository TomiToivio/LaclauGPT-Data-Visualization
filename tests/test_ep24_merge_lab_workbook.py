"""The human Excel codebooks decide first, and a matcher may not quietly undo them (#311 §8).

Three properties are pinned here, each of which failed before this module existed:

* a workbook row is applied *before* similarity matching, and its canonical spelling survives even
  when the corpus never writes that spelling;
* a human-decided label set is sealed: an unverified label cannot be absorbed into it on a score;
* a contradiction in a workbook is queued for adjudication instead of being resolved by whichever
  row happened to be read last;
* a registry rewrite keeps the corpus spellings it collapsed, so the run can still show them.

The workbooks in these tests are written to a temporary directory: the real ones are private
research data and never enter the public test suite.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboards"))

from ep24_merge_lab import curation, sources, workbook_evidence, workbook_mappings
from ep24_merge_lab.model import LabelStat
from ep24_merge_lab.similarity import RULES, resolve

openpyxl = pytest.importorskip("openpyxl")


def _workbook(path: Path, rows: list[tuple[object, ...]], *, sheet: str = "Sheet1") -> Path:
    book = openpyxl.Workbook()
    page = book.active
    page.title = sheet
    page.append(("old", "new"))
    for row in rows:
        page.append(row)
    book.save(path)
    return path


def _evidence(directory: Path, rows: dict[str, list[tuple[object, ...]]]) -> dict:
    for category, filename in workbook_mappings.WORKBOOK_CATEGORIES.items():
        _workbook(
            directory / filename,
            rows.get(category, [("placeholder", "Placeholder")]),
            sheet=f"{category}-sheet",
        )
    return workbook_evidence.inspect_workbooks(directory)


def _stats(*labels: str) -> list[LabelStat]:
    return [LabelStat(label=label, count=count) for count, label in enumerate(labels, start=1)]


# ------------------------------------------------------------------ evidence


def test_evidence_reads_pairs_with_sheet_and_row_provenance(tmp_path: Path) -> None:
    directory = tmp_path / "workbooks"
    directory.mkdir()
    evidence = _evidence(
        directory,
        {"person": [("javier milei", "Javier Milei (La Libertad Avanza; Argentina)")]},
    )
    person = evidence["sources"]["person"]
    assert len(person["pairs"]) == 1
    pair = person["pairs"][0]
    assert pair["alias"] == "javier milei"
    assert pair["sheet"] == "person-sheet"
    assert pair["row"] == 2
    assert len(person["sha256"]) == 64
    assert evidence["activation_authorized"] is False


def test_evidence_reports_incomplete_rows_and_lfs_pointers(tmp_path: Path) -> None:
    directory = tmp_path / "workbooks"
    directory.mkdir()
    evidence = _evidence(directory, {"entity": [("afghanistan", "Afghanistan"), ("", "Nameless")]})
    entity = evidence["sources"]["entity"]
    assert [sheet["incomplete_rows"] for sheet in entity["sheets"]] == [[3]]
    # A Git LFS pointer is not data; reading it as a workbook must fail loudly.
    pointer = directory / "themes.xlsx"
    pointer.write_text(
        "version https://git-lfs.github.com/spec/v1\noid sha256:deadbeef\nsize 1\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="hydrate Git LFS"):
        workbook_evidence.inspect_workbooks(directory)


# ------------------------------------------------------------------ mappings


def test_a_case_only_rename_is_a_human_naming_decision(tmp_path: Path) -> None:
    directory = tmp_path / "workbooks"
    directory.mkdir()
    mappings = workbook_mappings.from_evidence(
        _evidence(directory, {"entity": [("afghanistan ", "Afghanistan")]})
    )
    assert mappings.counts["entity"]["identity"] == 0
    assert mappings.forced["entity"] == [("Afghanistan", ["afghanistan"])]


def test_an_identity_row_says_nothing_about_membership(tmp_path: Path) -> None:
    directory = tmp_path / "workbooks"
    directory.mkdir()
    mappings = workbook_mappings.from_evidence(
        _evidence(directory, {"theme": [("activism", "activism"), ("activists", "activism")]})
    )
    assert mappings.counts["theme"]["identity"] == 1
    assert ("activism", ["activists"]) in mappings.forced["theme"]


def test_chains_are_followed_to_the_final_target(tmp_path: Path) -> None:
    directory = tmp_path / "workbooks"
    directory.mkdir()
    mappings = workbook_mappings.from_evidence(
        _evidence(directory, {"theme": [("a", "b"), ("b", "c")]})
    )
    forced = dict(mappings.forced["theme"])
    assert forced["c"] == ["a", "b"]
    assert mappings.adjudication == []


def test_a_conflicting_workbook_row_is_queued_not_resolved(tmp_path: Path) -> None:
    directory = tmp_path / "workbooks"
    directory.mkdir()
    mappings = workbook_mappings.from_evidence(
        _evidence(directory, {"person": [("orpo", "Petteri Orpo"), ("orpo", "Matti Orpo")]})
    )
    # Neither target may be applied: the workbook contradicts itself.
    assert "person" not in mappings.forced or mappings.forced["person"] == []
    assert len(mappings.adjudication) == 1
    item = mappings.adjudication[0]
    assert item["alias"] == "orpo"
    assert sorted(item["targets"]) == ["Matti Orpo", "Petteri Orpo"]
    assert mappings.counts["person"]["conflicting"] == 1


def test_a_cycle_is_queued_rather_than_half_applied(tmp_path: Path) -> None:
    directory = tmp_path / "workbooks"
    directory.mkdir()
    mappings = workbook_mappings.from_evidence(
        _evidence(directory, {"theme": [("a", "b"), ("b", "a")]})
    )
    assert mappings.forced.get("theme") in (None, [])
    reasons = {item["reason"] for item in mappings.adjudication}
    assert reasons  # reported, not silently dropped


def test_two_spellings_of_one_alias_are_one_target(tmp_path: Path) -> None:
    directory = tmp_path / "workbooks"
    directory.mkdir()
    mappings = workbook_mappings.from_evidence(
        _evidence(
            directory,
            {"theme": [("politician  public figure", "politicians"), ("politician public figure", "politicians")]},
        )
    )
    assert mappings.adjudication == []
    # Two rows that differ only in spacing name one alias, so they produce one member.
    assert mappings.forced["theme"] == [("politicians", ["politician public figure"])]


# ------------------------------------------------------------------ precedence


def test_a_workbook_pair_is_applied_before_the_matcher_runs() -> None:
    result = resolve(
        _stats("javier milei", "javier milei (argentina)"),
        RULES["person"],
        forced=[("Javier Milei (La Libertad Avanza; Argentina)", ["javier milei", "javier milei (argentina)"])],
        forced_methods={"Javier Milei (La Libertad Avanza; Argentina)": "workbook"},
    )
    cluster = result.clusters[0]
    assert cluster.canonical == "Javier Milei (La Libertad Avanza; Argentina)"
    assert set(cluster.members) == {"javier milei", "javier milei (argentina)"}
    assert "workbook" in cluster.method.split("+")


def test_a_human_canonical_survives_even_when_the_corpus_never_writes_it() -> None:
    result = resolve(
        _stats("activists", "grassroots movements"),
        RULES["theme"],
        forced=[("activism", ["activists", "grassroots movements"])],
        forced_methods={"activism": "workbook"},
    )
    assert [cluster.canonical for cluster in result.clusters] == ["activism"]


def test_a_sealed_cluster_does_not_absorb_an_unverified_label() -> None:
    """`javier milei` is workbook-decided; `javier milei libertad` is not, and scores 0.94."""
    result = resolve(
        _stats("javier milei", "javier milei libertad"),
        RULES["person"],
        forced=[("Javier Milei (Argentina)", ["javier milei"])],
        forced_methods={"Javier Milei (Argentina)": "workbook"},
    )
    assert len(result.clusters) == 1
    assert result.clusters[0].members == ("javier milei",)
    # The unverified spelling is a question for a person, and it is queued with that reason.
    queued = [candidate for candidate in result.candidates if "milei" in candidate.label]
    assert queued
    assert "human-verified" in queued[0].reason


def test_two_human_clusters_are_never_joined_by_a_score() -> None:
    result = resolve(
        _stats("petteri orpo", "matti orpo"),
        RULES["person"],
        forced=[("Petteri Orpo (Finland)", ["petteri orpo"]), ("Matti Orpo (Finland)", ["matti orpo"])],
        forced_methods={"Petteri Orpo (Finland)": "workbook", "Matti Orpo (Finland)": "workbook"},
    )
    canonical = {cluster.canonical for cluster in result.clusters}
    assert canonical == {"Petteri Orpo (Finland)", "Matti Orpo (Finland)"}


# ------------------------------------------------------------------ registry provenance


def test_a_registry_rewrite_keeps_the_alias_it_collapsed(tmp_path: Path) -> None:
    from ep24_merge_lab.merge_labels import _apply_registry
    from ep24_merge_lab.registry import Registry

    registry_path = tmp_path / "registry.jsonl"
    registry_path.write_text(
        json.dumps(
            {
                "category": "person",
                "alias": "borissov",
                "canonical": "Boyko Borisov",
                "status": "approved",
                "scope": {"country": "", "source": ""},
                "reviewers": ["a/1", "b/2", "c/3"],
                "evidence": ["https://en.wikipedia.org/wiki/Boyko_Borisov"],
                "wikidata": "Q57775",
                "wiki_title": "Boyko Borisov",
                "wiki_url": "https://en.wikipedia.org/wiki/Boyko_Borisov",
                "method": "workbook",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    registry = Registry.load(registry_path)
    pooled = {"person": [LabelStat(label="Borissov", count=7, countries=("Bulgaria",))]}
    rewritten, kept = _apply_registry(pooled, registry, [sources.Source(name="s", kind="records", path=tmp_path)])
    assert rewritten == 1
    assert pooled["person"][0].label == "Boyko Borisov"
    assert kept["person"]["Boyko Borisov"][0]["alias"] == "Borissov"
    assert kept["person"]["Boyko Borisov"][0]["occurrences"] == 7


def test_the_run_writes_registry_aliases_and_workbook_inputs(tmp_path: Path) -> None:
    result = resolve(_stats("borissov", "boyko borissov"), RULES["person"])
    run_dir = curation.write_run(
        tmp_path,
        results={"person": result},
        registry={"pinned": True, "version": "v1"},
        registry_aliases={"person": {"Boyko Borisov": [{"alias": "borissov", "occurrences": 3}]}},
        workbook={"schema": "ep24.workbook_mappings/1", "forced": {}, "counts": {}, "adjudication": []},
        coverage={"person": {"matched": 1}},
        workbook_inputs={"used": True, "files": {"person": {"sha256": "x" * 64}}},
    )
    with (run_dir / "registry_aliases.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["alias"] == "borissov"
    assert rows[0]["canonical"] == "Boyko Borisov"
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["workbook"]["used"] is True
    assert "registry_aliases.csv" in manifest["outputs"]
    assert "workbook_coverage.json" in manifest["outputs"]

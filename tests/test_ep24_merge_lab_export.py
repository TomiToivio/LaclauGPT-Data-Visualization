"""Export, activation and the legacy adapter must be boring and reversible (#300, deliverable 3).

Three promises are tested here, because each of them is a promise to a researcher rather than to a
programmer:

* an export is immutable and self-describing — it names the run, the decisions and the files it
  came from, and a second export never overwrites the first;
* collapsing aliases conserves occurrences, and does not double count a label that appears twice
  in one record under two spellings;
* nothing writes to a legacy source, and activation is a pointer that can be withdrawn.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboards"))

from ep24_merge_lab import adapters, curation, export


def _run(tmp_path: Path) -> Path:
    """A tiny finished run: two person clusters, one entity cluster, one candidate each."""
    run = tmp_path / "runs" / "20260101T000000Z"
    run.mkdir(parents=True)
    (run / "canonical_person.csv").write_text(
        "canonical,members,member_count,occurrences,confidence,method\n"
        'Petteri Orpo,"Orpo | Petteri Orpo",2,241,0.930,surname\n'
        '"Matti Orpo",Matti Orpo,1,12,1.000,canonical\n',
        encoding="utf-8",
    )
    (run / "review_person.csv").write_text(
        "label,occurrences,alternatives,reason\nNato,3,\"NATO (0.870)\",near miss\n",
        encoding="utf-8",
    )
    (run / "canonical_entity.csv").write_text(
        "canonical,members,member_count,occurrences,confidence,method\n"
        '"European Union","the European Union | European Union",2,900,0.940,containment\n',
        encoding="utf-8",
    )
    (run / "review_entity.csv").write_text(
        "label,occurrences,alternatives,reason\nEU,5,\"European Union (0.930)\",near miss\n",
        encoding="utf-8",
    )
    (run / "canonical_topic.csv").write_text(
        "canonical,members,member_count,occurrences,confidence,method\n", encoding="utf-8"
    )
    (run / "canonical_theme.csv").write_text(
        "canonical,members,member_count,occurrences,confidence,method\n", encoding="utf-8"
    )
    (run / "canonical_sentiment.csv").write_text(
        "canonical,members,member_count,occurrences,confidence,method\n", encoding="utf-8"
    )
    (run / "manifest.json").write_text(
        json.dumps({"inputs": [{"source": "legacy", "sha256": "abc"}]}), encoding="utf-8"
    )
    return run


def test_an_export_describes_itself_and_is_immutable(tmp_path: Path):
    run = _run(tmp_path)
    out = tmp_path / "curation"
    first = export.build_export(run, [], out, reviewer="tomi")
    second = export.build_export(run, [], out, reviewer="tomi")

    assert first.path != second.path, "a second export must not reuse the first directory"
    manifest = json.loads((first.path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == export.SCHEMA_VERSION
    assert manifest["base_run"] == "20260101T000000Z"
    assert manifest["base_run_inputs"] == [{"source": "legacy", "sha256": "abc"}]
    assert manifest["reviewer"] == "tomi"
    assert manifest["mapping_version"]
    assert manifest["files"]["alias_map.json"]["sha256"]
    assert manifest["review_status"]["candidates_open"] == 2


def test_collapsing_aliases_conserves_occurrences(tmp_path: Path):
    run = _run(tmp_path)
    result = export.build_export(run, [], tmp_path / "curation")
    person = result.clusters["person"]
    assert sum(cluster.occurrences for cluster in person) == 253
    preview = {row["category"]: row for row in csv.DictReader(
        (result.path / "counts_preview.csv").open(encoding="utf-8")
    )}
    assert preview["person"]["conserved"] == "yes"
    assert preview["person"]["occurrences"] == "253"


def test_a_researcher_merge_joins_two_clusters_and_adds_their_counts(tmp_path: Path):
    run = _run(tmp_path)
    decision = curation.Decision(
        category="person", action="merge", canonical="Petteri Orpo",
        members=("Petteri Orpo", "Matti Orpo"), reviewer="tomi",
    )
    result = export.build_export(run, [decision], tmp_path / "curation")
    persons = {cluster.canonical: cluster for cluster in result.clusters["person"]}
    assert set(persons) == {"Petteri Orpo"}
    assert persons["Petteri Orpo"].occurrences == 253
    assert {"Orpo", "Matti Orpo"} <= set(persons["Petteri Orpo"].members)
    assert persons["Petteri Orpo"].review_status == "REVIEWED"


def test_keep_separate_is_recorded_as_a_reviewed_refusal(tmp_path: Path):
    run = _run(tmp_path)
    decision = curation.Decision(
        category="entity", action="keep_separate", members=("European Union", "EU")
    )
    result = export.build_export(run, [decision], tmp_path / "curation")
    statuses = {cluster.canonical: cluster.review_status for cluster in result.clusters["entity"]}
    assert statuses["European Union"] == "KEPT_SEPARATE"


def test_activation_is_a_pointer_and_rollback_withdraws_it(tmp_path: Path):
    run = _run(tmp_path)
    out = tmp_path / "curation"
    result = export.build_export(run, [], out, reviewer="tomi")

    assert export.current_activation(out) is None
    payload = export.activate(out, result.path.name, reviewer="tomi")
    assert payload["mapping_version"] == result.manifest["mapping_version"]
    assert export.current_activation(out)["export_id"] == result.path.name

    active = export.resolve_active_export(out)
    assert active and active[0] == result.path

    export.rollback(out, reviewer="tomi")
    assert export.current_activation(out) is None
    assert export.resolve_active_export(out) is None
    history = (out / "activation_history.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert [json.loads(line)["event"] for line in history] == ["activate", "rollback"]


def test_an_export_edited_after_activation_is_not_served(tmp_path: Path):
    run = _run(tmp_path)
    out = tmp_path / "curation"
    result = export.build_export(run, [], out)
    export.activate(out, result.path.name)
    alias = result.path / "alias_map.json"
    alias.write_text(alias.read_text(encoding="utf-8").replace("Petteri Orpo", "Someone Else"),
                     encoding="utf-8")
    assert export.resolve_active_export(out) is None, "a tampered export must not be served"


# ------------------------------------------------------------------ the adapter


def _legacy(tmp_path: Path) -> Path:
    path = tmp_path / "legacy.csv"
    path.write_text(
        "country,entities,political_themes,topics,positive\n"
        'Finland,"Petteri Orpo, Orpo, European Union","Social Europe",elections,"good housing"\n'
        'Poland,"Orpo, Petteri Orpo",,elections,\n',
        encoding="utf-8",
    )
    return path


def test_the_adapter_collapses_two_spellings_in_one_record_without_double_counting(tmp_path: Path):
    mapping = {"person": {"orpo": "Petteri Orpo", "petteri orpo": "Petteri Orpo"}}
    labels = adapters.canonicalise_labels(["Orpo", "Petteri Orpo"], mapping["person"])
    assert labels == ["Petteri Orpo"], "one person said twice in one record is one occurrence"
    kept = adapters.canonicalise_labels(["Orpo", "Petteri Orpo"], mapping["person"], dedupe=False)
    assert kept == ["Petteri Orpo", "Petteri Orpo"]


def test_the_adapter_reads_a_legacy_table_without_touching_it(tmp_path: Path):
    run = _run(tmp_path)
    out = tmp_path / "curation"
    result = export.build_export(run, [], out)
    legacy = _legacy(tmp_path)
    before = hashlib.sha256(legacy.read_bytes()).hexdigest()

    mapping = adapters.load_mapping(result.path)
    preview = adapters.count_preview(
        legacy, columns={"person": "entities", "topic": "topics"}, mapping=mapping
    )
    assert preview["rows"] == 2
    assert preview["categories"]["person"]["labels_before"] == 5
    # "Petteri Orpo" and "Orpo" in one row are one person after canonicalisation.
    assert preview["categories"]["person"]["labels_after"] == 3
    assert hashlib.sha256(legacy.read_bytes()).hexdigest() == before


def test_a_canonicalised_copy_never_overwrites_the_source(tmp_path: Path):
    run = _run(tmp_path)
    out = tmp_path / "curation"
    result = export.build_export(run, [], out)
    legacy = _legacy(tmp_path)
    before = hashlib.sha256(legacy.read_bytes()).hexdigest()
    target = adapters.write_canonicalised(
        legacy, tmp_path / "exports", columns={"person": "entities"}, export_dir=result.path
    )
    assert target != legacy and target.exists()
    assert result.path.name in target.name
    provenance = json.loads(
        (target.with_suffix(target.suffix + ".provenance.json")).read_text(encoding="utf-8")
    )
    assert provenance["export_id"] == result.path.name
    assert provenance["rows"] == 2
    # The source is untouched, and writing again lands in a new file, never on top of it.
    assert hashlib.sha256(legacy.read_bytes()).hexdigest() == before
    again = adapters.write_canonicalised(
        legacy, tmp_path / "exports", columns={"person": "entities"}, export_dir=result.path
    )
    assert again == target


def test_a_mapping_from_another_schema_is_refused(tmp_path: Path):
    path = tmp_path / "alias_map.json"
    path.write_text(json.dumps({"schema": "something/else", "mapping": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported mapping schema"):
        adapters.load_mapping(tmp_path)

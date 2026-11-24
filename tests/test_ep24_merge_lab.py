"""The merge lab must merge the Orpos and refuse to merge the Europes (#300).

Every case here is synthetic and tiny. The tests exist because the failure modes of this tool are
silent: a wrong merge does not raise, it just changes every count downstream, and it changes them
in the private corpus where nobody sees the diff.

The four properties the issue names are pinned directly:

* the Orpo example resolves to the full name;
* a bare surname stays a candidate when two people could answer to it;
* multilingual spellings of one name resolve, and non-equivalent themes and opposing sentiments
  never do;
* a researcher decision survives the next run.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboards"))

from ep24_merge_lab import curation, sources
from ep24_merge_lab.model import LabelStat
from ep24_merge_lab.normalization import normalize_label
from ep24_merge_lab.similarity import RULES, resolve, similarity


def stats(*labels: str) -> list[LabelStat]:
    return [LabelStat(label=label, count=count) for count, label in enumerate(labels, start=1)]


def cluster_of(result, label: str):
    for cluster in result.clusters:
        if label in cluster.members or cluster.canonical == label:
            return cluster
    return None


# ------------------------------------------------------------------ normalization


def test_normalization_folds_case_unicode_and_extractor_junk():
    assert normalize_label("  Petteri   ORPO ").folded == "petteri orpo"
    # NFD and NFC must agree, or the same name from two extractors looks like two names.
    import unicodedata

    composed = unicodedata.normalize("NFC", "Åbo Akademi")
    decomposed = unicodedata.normalize("NFD", "Åbo Akademi")
    assert composed != decomposed  # the two forms really are different byte strings
    assert normalize_label(composed).folded == normalize_label(decomposed).folded == "åbo akademi"
    assert normalize_label("“Orpo”").folded == "orpo"
    assert normalize_label("Orpo,").folded == "orpo"


def test_titles_are_stripped_for_people_only_when_the_rule_says_so():
    assert normalize_label("Prime Minister Orpo", strip_titles=True).core == "orpo"
    assert normalize_label("PM Orpo", strip_titles=True).core == "orpo"
    # A theme that happens to start with an office word must keep it.
    assert normalize_label("Minister of Finance", strip_titles=False).core == "minister of finance"


def test_legal_suffixes_are_stripped_for_organisations():
    assert normalize_label("Fortum Oyj", strip_legal_suffixes=True).core == "fortum"
    assert normalize_label("Fortum", strip_legal_suffixes=True).core == "fortum"


# ------------------------------------------------------------------ the Orpo example


def test_the_four_orpo_spellings_resolve_to_the_full_name():
    """#300's own example: Petteri Orpo / Prime Minister Orpo / PM Orpo / Orpo are one person."""
    result = resolve(
        stats("Petteri Orpo", "Prime Minister Orpo", "PM Orpo", "Orpo"),
        RULES["person"],
    )
    assert len(result.clusters) == 1
    cluster = result.clusters[0]
    assert cluster.canonical == "Petteri Orpo"
    assert set(cluster.members) == {"Petteri Orpo", "Prime Minister Orpo", "PM Orpo", "Orpo"}
    assert cluster.count == 10


def test_word_order_does_not_make_two_people():
    result = resolve(stats("Orpo Petteri", "Petteri Orpo"), RULES["person"])
    assert len(result.clusters) == 1
    assert result.clusters[0].method == "token-set"


def test_a_bare_surname_stays_a_candidate_when_two_people_share_it():
    result = resolve(stats("Orpo", "Petteri Orpo", "Matti Orpo"), RULES["person"])
    assert all("Orpo" not in cluster.members or len(cluster.members) == 1 for cluster in result.clusters)
    assert not any(cluster.canonical == "Orpo" for cluster in result.clusters)
    reasons = " ".join(candidate.reason for candidate in result.candidates)
    assert "matches 2 full names" in reasons


def test_a_surname_never_merges_across_two_distinct_people():
    """A~B and B~C must not drag A and C together (no unsafe transitive merge)."""
    result = resolve(stats("Petteri Orpo", "Orpo", "Matti Orpo"), RULES["person"])
    for cluster in result.clusters:
        names = set(cluster.members)
        assert not {"Petteri Orpo", "Matti Orpo"} <= names


# ------------------------------------------------------------------ categories that must not merge


def test_shared_words_do_not_make_two_themes_the_same():
    result = resolve(stats("Social Europe", "Arguments for Europe"), RULES["theme"])
    assert not result.clusters
    assert similarity(
        normalize_label("Social Europe"), normalize_label("Arguments for Europe"), RULES["theme"]
    )[0] < RULES["theme"].auto_merge


def test_a_related_topic_is_not_an_equivalent_topic():
    result = resolve(stats("housing policy", "housing market"), RULES["topic"])
    assert not result.clusters


def test_opposing_sentiment_polarities_never_merge():
    positive = LabelStat(label="good housing policy", count=3, polarity="positive")
    negative = LabelStat(label="good housing policy", count=2, polarity="negative")
    # The two live in different polarity groups: the caller resolves each separately.
    assert positive.group != negative.group
    for polarity in ("positive", "negative"):
        single = curation.resolve_category(
            [LabelStat(label="good housing policy", count=1, polarity=polarity)],
            "sentiment",
        )
        assert not single.clusters


def test_containment_is_a_phrase_not_a_bag_of_words():
    """The regression that renamed 3 885 occurrences: EU is not the European Broadcasting Union."""
    result = resolve(
        stats("European Union", "European Broadcasting Union (EBU)", "the European Union"),
        RULES["entity"],
    )
    merged = [cluster for cluster in result.clusters if len(cluster.members) > 1]
    assert len(merged) == 1, "only the two EU spellings may merge"
    assert set(merged[0].members) == {"European Union", "the European Union"}
    assert all(
        "Broadcasting" not in member for cluster in merged for member in cluster.members
    ), "the broadcasting union is a different organisation"


def test_a_parenthetical_gloss_is_dropped_for_entities_but_kept_for_themes():
    """A gloss names the same thing twice; a year in a theme is meaning, not a gloss."""
    entities = resolve(stats("European Broadcasting Union (EBU)"), RULES["entity"])
    assert entities.clusters[0].canonical == "European Broadcasting Union"
    assert entities.clusters[0].members == ("European Broadcasting Union (EBU)",)
    assert entities.clusters[0].method == "normalization"

    themes = resolve(stats("European Parliament elections (2024)"), RULES["theme"])
    assert not themes.clusters, "the year must not be stripped from a theme"
    assert themes.singletons == ["European Parliament elections (2024)"]


def test_a_curated_party_alias_merges_its_spellings():
    result = resolve(
        stats("True Finns", "Finns Party", "perussuomalaiset"), RULES["entity"]
    )
    assert len(result.clusters) == 1
    assert result.clusters[0].canonical == "Perussuomalaiset"
    assert set(result.clusters[0].members) == {"True Finns", "Finns Party", "perussuomalaiset"}


def test_christian_democrats_is_only_the_cdu_when_the_corpus_says_germany():
    german = resolve(
        [LabelStat(label="Christian Democrats", count=5, countries=("germany",)),
         LabelStat(label="CDU", count=9, countries=("germany",))],
        RULES["entity"],
    )
    assert len(german.clusters) == 1

    dutch = resolve(
        [LabelStat(label="Christian Democrats", count=5, countries=("netherlands",)),
         LabelStat(label="CDU", count=9, countries=("netherlands",))],
        RULES["entity"],
    )
    assert not dutch.clusters, "a Dutch Christian Democrat is not a German CDU"


def test_people_and_organisations_are_separate_categories():
    assert RULES["person"].strip_titles and not RULES["entity"].strip_titles
    assert RULES["person"].surname_merge and not RULES["entity"].surname_merge


# ------------------------------------------------------------------ decisions survive runs


def test_a_keep_separate_decision_holds_across_runs(tmp_path: Path):
    log = tmp_path / "decisions.jsonl"
    curation.append_decision(
        log,
        curation.Decision(
            category="person",
            action="keep_separate",
            members=("Petteri Orpo", "Orpo"),
            reviewer="researcher",
        ),
    )
    decisions = curation.load_decisions(log)
    result = curation.resolve_category(stats("Petteri Orpo", "Orpo"), "person", decisions)
    assert not result.clusters, "a researcher's keep-separate must not be undone by the matcher"
    assert any("researcher decision" in candidate.reason for candidate in result.candidates)


def test_a_merge_decision_forces_labels_the_matcher_would_not_join(tmp_path: Path):
    log = tmp_path / "decisions.jsonl"
    curation.append_decision(
        log,
        curation.Decision(
            category="theme",
            action="merge",
            canonical="Social Europe",
            members=("Social Europe", "European social model"),
            reviewer="researcher",
        ),
    )
    result = curation.resolve_category(
        stats("Social Europe", "European social model"), "theme", curation.load_decisions(log)
    )
    assert len(result.clusters) == 1
    assert result.clusters[0].canonical == "Social Europe"


def test_a_malformed_decision_is_refused_rather_than_ignored(tmp_path: Path):
    log = tmp_path / "decisions.jsonl"
    log.write_text('{"category": "person", "action": "maybe"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="unknown decision action"):
        curation.load_decisions(log)


# ------------------------------------------------------------------ sources and outputs


PROFILE = """
version: 1
sources:
  - name: legacy-dashboard
    kind: records
    path: dashboard.csv
    country_column: country
    lists:
      entities: {column: entities, separator: ","}
      themes: {column: political_themes, separator: "\\n"}
      topics: {column: topics, separator: ","}
      sentiment:
        positive: {column: positive, separator: ","}
  - name: codebook-entities
    kind: entity_codebook
    path: entities.csv
  - name: codebook-topics
    kind: topic_codebook
    path: topics.csv
"""


def _write_legacy_tree(tmp_path: Path) -> Path:
    (tmp_path / "dashboard.csv").write_text(
        "country,entities,political_themes,topics,positive,negative\n"
        'Finland,"Petteri Orpo, Orpo","Social Europe\nArguments for Europe",elections,'
        '"good housing policy",\n'
        'Finland,"PM Orpo","Social Europe",elections,,\n',
        encoding="utf-8",
    )
    (tmp_path / "entities.csv").write_text(
        "label,aliases,entity_type,country\n"
        'Petteri Orpo,"Orpo; PM Orpo",person,Finland\n'
        "European Parliament,,European Parliament political group,Finland\n",
        encoding="utf-8",
    )
    (tmp_path / "topics.csv").write_text(
        "label,aliases,entity_type,country\nelections,,topic,Finland\n",
        encoding="utf-8",
    )
    profile = tmp_path / "profile.yaml"
    profile.write_text(PROFILE, encoding="utf-8")
    return profile


def test_the_profile_is_turned_into_sources_with_the_right_categories(tmp_path: Path):
    profile = _write_legacy_tree(tmp_path)
    loaded = sources.load_profile(profile, root=tmp_path)
    assert [source.kind for source in loaded] == ["records", "entity_codebook", "topic_codebook"]
    assert loaded[0].lists["sentiment"][0].polarity == "positive"
    assert loaded[0].lists["theme"][0].separator == "\n"


def test_extraction_separates_people_from_organisations(tmp_path: Path):
    profile = _write_legacy_tree(tmp_path)
    pooled = sources.extract(sources.load_profile(profile, root=tmp_path))
    assert "Petteri Orpo" in {stat.label for stat in pooled["person"]}
    assert "Petteri Orpo" not in {stat.label for stat in pooled["entity"]}
    assert "European Parliament" in {stat.label for stat in pooled["entity"]}
    assert "elections" in {stat.label for stat in pooled["topic"]}
    assert {stat.polarity for stat in pooled["sentiment"]} == {"positive"}


def test_a_run_writes_versioned_tables_and_a_manifest(tmp_path: Path):
    profile = _write_legacy_tree(tmp_path)
    loaded = sources.load_profile(profile, root=tmp_path)
    pooled = sources.extract(loaded)
    results = {
        category: curation.resolve_category(pooled[category], category)
        for category in pooled
    }
    out = tmp_path / "curation"
    run_dir = curation.write_run(
        out,
        results=results,
        manifest_inputs=[{"source": source.name, "path": str(source.path)} for source in loaded],
        profile_digest=sources.file_digest(profile),
    )
    assert (run_dir / "manifest.json").exists()
    assert (out / "LATEST").read_text(encoding="utf-8").strip() == run_dir.name
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == curation.SCHEMA_VERSION
    assert manifest["inputs"] and manifest["outputs"]["alias_map.csv"]["sha256"]

    canonical = list(csv.DictReader((run_dir / "canonical_person.csv").open(encoding="utf-8")))
    assert canonical and canonical[0]["canonical"] == "Petteri Orpo"
    aliases = {
        row["alias"]
        for row in csv.DictReader((run_dir / "alias_map.csv").open(encoding="utf-8"))
        if row["category"] == "person"
    }
    assert {"PM Orpo", "Orpo"} <= aliases


def test_a_second_run_does_not_overwrite_the_first(tmp_path: Path):
    profile = _write_legacy_tree(tmp_path)
    pooled = sources.extract(sources.load_profile(profile, root=tmp_path))
    results = {category: curation.resolve_category(pooled[category], category) for category in pooled}
    out = tmp_path / "curation"
    first = curation.write_run(out, results=results)
    second = curation.write_run(out, results=results)
    assert first != second
    assert first.exists() and second.exists()


def test_a_semicolon_separated_person_cell_is_split_not_kept_whole():
    """The pledge table's persons column uses ";" while its neighbours use "," (#300)."""
    from ep24_merge_lab.sources import split_labels

    assert split_labels("javier milei; santiago abascal", ";") == ["javier milei", "santiago abascal"]


def test_one_column_may_mix_separators():
    """Themes mix ";" and "," in the same column; neither may survive inside a label."""
    from ep24_merge_lab.sources import split_labels

    assert split_labels("voters and voting; diversity and inclusion", ";,") == [
        "voters and voting",
        "diversity and inclusion",
    ]
    assert split_labels("voters and voting, diversity and inclusion", ";,") == [
        "voters and voting",
        "diversity and inclusion",
    ]
    assert split_labels("climate policy;energy, migration", ";,") == [
        "climate policy",
        "energy",
        "migration",
    ]


def test_a_separator_free_label_is_unchanged_by_the_wider_split():
    from ep24_merge_lab.sources import split_labels

    assert split_labels("pedro sánchez", ";,") == ["pedro sánchez"]
    assert split_labels("", ";,") == []
    assert split_labels("nan", ";,") == []


# ------------------------------------------------------------------ redundant qualifiers (#300)

def test_an_acronym_qualifier_folds_into_the_party_name():
    from ep24_merge_lab.normalization import redundant_qualifier

    assert redundant_qualifier("social democratic party (sdp)") == "social democratic party"
    assert redundant_qualifier("European Union (EU)") == "European Union"  # casing is preserved
    # Letter order varies between exporters: the Finnish SDP is written SPD in some sources.
    assert redundant_qualifier("social democratic party (spd)") == "social democratic party"


def test_a_qualifier_naming_another_thing_is_kept():
    """Common sense: a place, a person, a year or a different body is information, not noise."""
    from ep24_merge_lab.normalization import redundant_qualifier

    for label in (
        "government (france)",
        "government (spain)",
        "speaker (jorge buxadé)",
        "social democratic party (2024)",
        "european union (brussels)",
        "government (opposition)",  # the bracket is the only thing that distinguishes it
        "party (france)",
    ):
        assert redundant_qualifier(label) is None, label


def test_a_repeated_or_organisational_qualifier_on_a_short_name_is_dropped():
    from ep24_merge_lab.normalization import redundant_qualifier

    assert redundant_qualifier("vox (vox)") == "vox"  # pure repetition
    assert redundant_qualifier("vox (party)") == "vox"  # the type is not the name
    assert redundant_qualifier("Party (party)") == "Party"


def test_collapsed_labels_pool_their_counts():
    import csv as _csv

    from ep24_merge_lab import sources

    tmp = Path(__file__).parent / "_tmp_qualifier.csv"
    tmp.write_text(
        'entities\n"sdp social democratic party"\n"social democratic party (sdp)"\n'
        '"social democratic party"\n"government (france)"\n"government (spain)"\n',
        encoding="utf-8",
    )
    try:
        source = sources.Source(
            name="fixture",
            kind="records",
            path=tmp,
            lists={"entity": [sources.ListColumn(column="entities", separator=",")]},
        )
        pooled = sources.extract([source], category="entity")
        counts = {stat.label: stat.count for stat in pooled["entity"]}
        assert counts["social democratic party"] == 2  # the plain row plus the collapsed (sdp) row
        assert "social democratic party (sdp)" not in counts
        assert counts["government (france)"] == 1 and counts["government (spain)"] == 1
    finally:
        tmp.unlink()


def test_the_canonical_label_does_not_carry_its_own_aliases():
    """A cluster whose spellings include a bracket must be named by the plain form."""
    from ep24_merge_lab.similarity import RULES, resolve
    from ep24_merge_lab.sources import LabelStat

    stats = [
        LabelStat(label="psoe (spanish socialist workers' party)", count=40),
        LabelStat(label="psoe", count=12),
        LabelStat(label="spanish socialist workers' party", count=6),
    ]
    result = resolve(stats, RULES["entity"])
    assert result.clusters, "the three spellings should cluster"
    assert "(" not in result.clusters[0].canonical

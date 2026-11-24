"""Tests for the shared merge registry (#311).

The registry is the one artifact every pipeline and dashboard depends on, so the tests here are
about the properties that keep it trustworthy: attributable decisions, scoped mappings, explicit
non-merges that survive, deterministic exports, and a version a run can pin.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboards"))

from ep24_merge_lab.registry import (
    Registry,
    RegistryEntry,
    RegistryError,
    Scope,
)


def _entry(**overrides) -> RegistryEntry:
    payload = {
        "category": "entity",
        "alias": "sdp social democratic party",
        "canonical": "Social Democratic Party",
        "status": "approved",
        "reviewers": ("agent-a/run-1", "agent-b/run-2", "agent-c/run-3"),
        "evidence": ("https://en.wikipedia.org/wiki/Social_Democratic_Party",),
        "method": "wikidata-sitelink",
    }
    payload.update(overrides)
    return RegistryEntry(**payload)


def _write(path: Path, entries: list[RegistryEntry]) -> Path:
    path.write_text(
        "".join(json.dumps(entry.as_json(), sort_keys=True) + "\n" for entry in entries),
        encoding="utf-8",
    )
    return path


def test_a_sound_entry_validates() -> None:
    assert _entry().validate() == []


@pytest.mark.parametrize(
    "overrides, needle",
    [
        ({"reviewers": ()}, "attributable"),
        ({"evidence": ()}, "no evidence"),
        ({"category": "colour"}, "unknown category"),
        ({"status": "maybe"}, "unknown status"),
        ({"wiki_title": "X", "wiki_url": ""}, "verified URL"),
        ({"status": "keep_separate", "canonical": "Something else"}, "point at itself"),
    ],
)
def test_a_bad_entry_names_its_problem(overrides: dict, needle: str) -> None:
    problems = " ".join(_entry(**overrides).validate())
    assert needle in problems


def test_sentiment_must_state_its_polarity() -> None:
    problems = _entry(category="sentiment", alias="hopeful", canonical="hope").validate()
    assert any("polarity" in problem for problem in problems)


def test_the_registry_reads_back_what_it_wrote(tmp_path: Path) -> None:
    path = _write(tmp_path / "registry.jsonl", [_entry()])
    registry = Registry.load(path)
    assert registry.problems() == []
    assert registry.map_label("entity", "sdp social democratic party") == "Social Democratic Party"


def test_a_missing_registry_is_an_error_not_an_empty_mapping(tmp_path: Path) -> None:
    """A pipeline that cannot find the registry must stop, not silently canonicalise nothing."""
    with pytest.raises(RegistryError):
        Registry.load(tmp_path / "absent.jsonl")


def test_a_broken_line_is_reported_with_its_position(tmp_path: Path) -> None:
    good = json.dumps(_entry().as_json(), sort_keys=True)
    path = tmp_path / "registry.jsonl"
    path.write_text(good + "\nnot json\n", encoding="utf-8")
    with pytest.raises(RegistryError) as caught:
        Registry.load(path)
    assert ":2:" in str(caught.value)


def test_alias_matching_is_case_and_space_insensitive(tmp_path: Path) -> None:
    path = _write(tmp_path / "registry.jsonl", [_entry(alias="  SDP Social Democratic Party ")])
    registry = Registry.load(path)
    assert registry.map_label("entity", "sdp social democratic party") == "Social Democratic Party"


def test_a_scoped_mapping_only_applies_in_its_context(tmp_path: Path) -> None:
    """'The party' is a different party in Finland and in Germany."""
    path = _write(
        tmp_path / "registry.jsonl",
        [
            _entry(alias="the party", canonical="Finns Party", scope=Scope(country="Finland")),
            _entry(alias="the party", canonical="Social Democratic Party of Germany", scope=Scope(country="Germany")),
        ],
    )
    registry = Registry.load(path)
    assert registry.map_label("entity", "the party", country="Finland") == "Finns Party"
    assert registry.map_label("entity", "the party", country="Germany") == "Social Democratic Party of Germany"
    # No context, no guess: the alias stays as it is rather than borrowing another country's party.
    assert registry.map_label("entity", "the party") == "the party"


def test_keep_separate_survives_into_every_later_run(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "registry.jsonl",
        [_entry(alias="le pen", canonical="le pen", status="keep_separate")],
    )
    registry = Registry.load(path)
    assert registry.map_label("person", "le pen") == "le pen"


def test_a_later_revision_wins_and_the_old_one_stays_on_disk(tmp_path: Path) -> None:
    old = _entry(canonical="Social Democratic Party", revision=1)
    new = _entry(canonical="Social Democratic Party (Finland)", revision=2, status="approved")
    path = _write(tmp_path / "registry.jsonl", [old, new])
    registry = Registry.load(path)
    assert registry.map_label("entity", "sdp social democratic party") == "Social Democratic Party (Finland)"
    assert len(registry.entries) == 2, "history is append-only; nothing is rewritten"


def test_a_superseded_entry_is_ignored(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "registry.jsonl",
        [
            _entry(canonical="Wrong", revision=1, status="superseded"),
            _entry(canonical="Right", revision=2),
        ],
    )
    assert Registry.load(path).map_label("entity", "sdp social democratic party") == "Right"


def test_appending_refuses_an_unauthorised_decision(tmp_path: Path) -> None:
    path = _write(tmp_path / "registry.jsonl", [_entry()])
    registry = Registry.load(path)
    with pytest.raises(RegistryError):
        registry.append([_entry(alias="x", canonical="y", reviewers=(), evidence=())])


def test_appending_keeps_the_file_loadable_and_the_version_moving(tmp_path: Path) -> None:
    path = _write(tmp_path / "registry.jsonl", [_entry()])
    registry = Registry.load(path)
    before = registry.version
    registry.append([_entry(alias="true finns", canonical="Finns Party")])
    reloaded = Registry.load(path)
    assert reloaded.version != before
    assert reloaded.map_label("entity", "true finns") == "Finns Party"


def test_the_version_is_stable_for_the_same_content(tmp_path: Path) -> None:
    first = Registry.load(_write(tmp_path / "a.jsonl", [_entry()]))
    second = Registry.load(_write(tmp_path / "b.jsonl", [_entry()]))
    assert first.version == second.version


def test_the_csv_export_is_deterministic(tmp_path: Path) -> None:
    path = _write(tmp_path / "registry.jsonl", [_entry(), _entry(alias="true finns", canonical="Finns Party")])
    registry = Registry.load(path)
    first = registry.to_csv(tmp_path / "one.csv").read_bytes()
    second = registry.to_csv(tmp_path / "two.csv").read_bytes()
    assert first == second
    assert b"keep_separate" in first or b"approved" in first


def test_a_proposal_does_not_rewrite_output(tmp_path: Path) -> None:
    """Three reviews make a decision; one review is a proposal and must not reseal the corpus."""
    path = _write(
        tmp_path / "registry.jsonl",
        [
            _entry(
                alias="true finns",
                canonical="Finns Party",
                status="proposed",
                reviewers=("agent-a/run-1",),
            )
        ],
    )
    registry = Registry.load(path)
    assert registry.map_label("entity", "true finns") == "true finns"
    assert registry.latest("entity", "true finns") is not None  # still visible to a reviewer

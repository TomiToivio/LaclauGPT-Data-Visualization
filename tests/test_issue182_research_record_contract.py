"""#182: the visualization consumer accepts Analysis research records at 1.2.0.

The record fixtures below are synthetic but **structurally identical** to what
Analysis actually writes, including the parts a tidied fixture would omit: the
transport envelope (identity and diagnostics at the top level, the canonical
record under ``result``) and the empty sections a fresh record really has. The
envelope shape and the provenance block were read from the live store on
2026-10-15; the routing snapshot is recorded in
``tests/fixtures/ai26_deployed_collections_v1.json``.
"""
from __future__ import annotations

import json
from pathlib import Path

from laclaugpt_visualization.canonical import reconstruct_canonical, unwrap_envelope
from laclaugpt_visualization.data import frame_from_records
from laclaugpt_visualization.distributed import _MONGO_KINDS as MONGO_KINDS
from laclaugpt_visualization.distributed import ProjectNamespace
from laclaugpt_visualization.research_record_contract import (
    EXPERIMENTAL_STAGE_LABEL,
    EXPERIMENTAL_STAGES,
    PHASE_1_STAGES,
    REQUIRED_RECORD_FIELDS,
    SUPPORTED_SCHEMA_VERSIONS,
    VersionStatus,
    accept_record,
    classify_schema_version,
    stage_status_label,
    unsupported_versions,
)

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "research-record.schema.json"
ROUTING_PATH = Path(__file__).resolve().parent / "fixtures" / "ai26_deployed_collections_v1.json"

# --------------------------------------------------------------------------- #
# A canonical record shaped like an Analysis result at 1.2.0, wrapped in the
# transport envelope Analysis persists it in.
# --------------------------------------------------------------------------- #

CANONICAL_1_1_0 = {
    "schema_version": "1.1.0",
    "source_url": "https://example.invalid/ai26/legacy-record",
    "source_native_ids": {"platform": "example-1"},
    "raw_capture": {"ref": "s3://example-bucket/ai26/raw/1.json", "payload": None,
                    "checksum": "0" * 64, "content_type": "application/json",
                    "captured_at": "2026-10-01T10:00:00+00:00", "metadata": {}},
    "source": {"kind": "web_source", "name": "example source", "arena": "elites"},
    "content": {"text": "An example post used by the contract tests.", "language": "en"},
    "intermediate": {"asr": [], "ocr": [], "frames": [], "frame_analysis": [],
                     "translations": [], "stage_outputs": {}},
    "analysis": {},
    "human_readable": {"summary": "", "markdown": ""},
    "provenance": [],
    "review": {},
    "legacy": {},
}

CANONICAL_1_2_0 = {
    **CANONICAL_1_1_0,
    "schema_version": "1.2.0",
    "source_url": "https://example.invalid/ai26/analysis-origin-record",
    "analysis": {
        "signifiers": ["public infrastructure"],
        "nodal_points": ["accountability"],
        "formations": [{"name": "public-interest techno-optimism", "provisional": True}],
        "imaginaries": [
            {
                "label": "shared compute as public infrastructure",
                "desirable": True,
                "evidence": ["https://example.invalid/ai26/analysis-origin-record"],
                "uncertain": True,
            }
        ],
    },
    "evidence": [
        {
            "source_url": "https://example.invalid/ai26/analysis-origin-record",
            "quote": "An example post used by the contract tests.",
            "char_start": 0,
            "char_end": 48,
        }
    ],
    "provenance": [
        {"kind": "model_annotation", "producer": "gemma4:12b", "prompt_version": "ai26-crossover-v1"}
    ],
    "review": {"status": "PROVISIONAL", "reviewer": "", "notes": ""},
}

#: The transport-level provenance Data Analysis writes beside the record.
TRANSPORT_PROVENANCE = {
    "codebook_sha256": "7a40f3aaea9025185eaae29d514f81f00f735c2f",
    "config_sha256": "a7c547d5c5e6baff6aac41a0f7323ef818f4c2da",
    "model": "gemma4:12b",
    "phase": "phase-1",
    "phase1_codebook_revision": "8ea0b7303a5272f8272637b8117a0be2ce34a1b8",
    "phase1_config_revision": "7d67b5f5ac3d59d03eeba81ae880b095a18a5105",
    "phase1_date_after": "2026-09-01T00:00:00+00:00",
}

ANALYSIS_ENVELOPE = {
    "_id": "68f0c0ffee00000000000001",
    "idempotency_key": "b" * 64,
    "project_id": "ai26",
    "run_id": "ai26-distributed-001",
    "created_at": 1792058627.9148667,
    "source_url": CANONICAL_1_2_0["source_url"],
    "provenance": TRANSPORT_PROVENANCE,
    "result": CANONICAL_1_2_0,
}


# --------------------------------------------------------------------------- #
# Criterion 1: accept both declared versions, and never guess at a third.
# --------------------------------------------------------------------------- #


def test_both_declared_versions_are_accepted() -> None:
    for record in (CANONICAL_1_1_0, CANONICAL_1_2_0):
        acceptance = accept_record(record)
        assert acceptance.status is VersionStatus.SUPPORTED
        assert acceptance.accepted is True
        assert acceptance.schema_version == record["schema_version"]


def test_an_unknown_version_is_reported_with_its_original_text() -> None:
    acceptance = accept_record({**CANONICAL_1_2_0, "schema_version": "1.3.0"})
    assert acceptance.status is VersionStatus.UNKNOWN
    assert acceptance.accepted is False
    # The upstream value must survive: a reader has to see what was not recognised.
    assert acceptance.schema_version == "1.3.0"
    assert "1.3.0" in acceptance.label()


def test_a_missing_version_is_distinct_from_an_unknown_one() -> None:
    absent = {key: value for key, value in CANONICAL_1_2_0.items() if key != "schema_version"}
    assert classify_schema_version(None) is VersionStatus.ABSENT
    assert classify_schema_version("") is VersionStatus.ABSENT
    assert classify_schema_version("1.2.0") is VersionStatus.SUPPORTED
    assert classify_schema_version("2.0.0") is VersionStatus.UNKNOWN
    assert accept_record(absent).status is VersionStatus.ABSENT


def test_a_missing_required_field_is_reported_by_name() -> None:
    incomplete = {key: value for key, value in CANONICAL_1_2_0.items() if key != "review"}
    acceptance = accept_record(incomplete)
    assert acceptance.status is VersionStatus.SUPPORTED
    assert acceptance.missing_required == ("review",)
    assert acceptance.accepted is False
    assert "review" in acceptance.label()


def test_the_supported_count_only_counts_unsupported_versions() -> None:
    assert unsupported_versions([CANONICAL_1_1_0, CANONICAL_1_2_0]) == {}
    counts = unsupported_versions(
        [CANONICAL_1_2_0, {**CANONICAL_1_2_0, "schema_version": "1.3.0"},
         {**CANONICAL_1_2_0, "schema_version": "1.3.0"}, {"source_url": "x"}]
    )
    assert counts == {"1.3.0": 2, "(none)": 1}


def test_the_published_schema_and_the_supported_set_cannot_drift() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    declared = schema["properties"]["schema_version"]["enum"]
    assert set(declared) == set(SUPPORTED_SCHEMA_VERSIONS), (
        "schemas/research-record.schema.json and SUPPORTED_SCHEMA_VERSIONS disagree"
    )
    assert set(schema["required"]) == set(REQUIRED_RECORD_FIELDS), (
        "the schema's required list and REQUIRED_RECORD_FIELDS disagree"
    )


# --------------------------------------------------------------------------- #
# Criterion 2: an Analysis-origin record keeps everything through the real path.
# --------------------------------------------------------------------------- #


def test_an_analysis_origin_record_survives_the_visualization_path() -> None:
    unwrapped = unwrap_envelope(dict(ANALYSIS_ENVELOPE))

    # The canonical record wins for canonical fields ...
    assert unwrapped["schema_version"] == "1.2.0"
    assert set(unwrapped) >= set(REQUIRED_RECORD_FIELDS)
    assert unwrapped["analysis"]["imaginaries"][0]["label"].startswith("shared compute")
    assert unwrapped["evidence"][0]["char_end"] == 48
    assert unwrapped["provenance"][0]["producer"] == "gemma4:12b"
    assert unwrapped["review"]["status"] == "PROVISIONAL"

    # ... the transport identity is not lost either.
    assert unwrapped["run_id"] == "ai26-distributed-001"
    assert unwrapped["transport_provenance"] == TRANSPORT_PROVENANCE
    for key in ("codebook_sha256", "config_sha256", "model",
                "phase1_codebook_revision", "phase1_config_revision", "phase1_date_after"):
        assert unwrapped["transport_provenance"][key]

    reconstructed = reconstruct_canonical(dict(ANALYSIS_ENVELOPE))
    assert set(reconstructed) >= set(REQUIRED_RECORD_FIELDS)
    assert reconstructed["intermediate"]["stage_outputs"] == {}
    assert accept_record(reconstructed).accepted is True


def test_the_frame_the_dashboard_reads_keeps_the_record_and_its_version() -> None:
    """The view layer flattens the canonical sections into columns.

    So what has to survive is the *projection*: the record is not rendered as
    collection-only, and the analysis, evidence and provenance sections are all
    reachable in the frame the dashboard reads.
    """
    frame = frame_from_records([dict(ANALYSIS_ENVELOPE)])
    row = frame.to_dict(orient="records")[0]
    assert row["schema_version"] == "1.2.0"
    assert row["source_url"] == CANONICAL_1_2_0["source_url"]

    # the analysis section is present as flat columns, not dropped as empty
    assert row["imaginaries"], "the imaginaries did not reach the frame"
    assert row["signifiers"] == ["public infrastructure"]
    assert row["nodal_points"] == ["accountability"]
    # evidence pointers and review survive
    assert row["evidence"], "the evidence pointers did not reach the frame"
    assert row["review_status"] == "PROVISIONAL"
    # and so does provenance
    assert row["provenance"]


def test_no_canonical_field_is_lost_on_the_way_through() -> None:
    unwrapped = unwrap_envelope(dict(ANALYSIS_ENVELOPE))
    lost = sorted(set(CANONICAL_1_2_0) - set(unwrapped))
    assert lost == [], f"fields dropped by the envelope adapter: {lost}"


# --------------------------------------------------------------------------- #
# Criterion 3: Phase 2 outputs are labelled experimental, Phase 1 never is.
# --------------------------------------------------------------------------- #


def test_experimental_stages_are_labelled_and_phase_1_stages_are_not() -> None:
    for stage in ("dna", "dna_statement_coding", "sna", "network_projection"):
        assert stage in EXPERIMENTAL_STAGES
        assert stage_status_label(stage) == EXPERIMENTAL_STAGE_LABEL
        assert "Phase 1" in stage_status_label(stage)
    for stage in ("summary", "context", "discourse", "laclau", "palonen"):
        assert stage in PHASE_1_STAGES
        assert stage_status_label(stage) == ""


def test_the_experimental_and_phase_1_stage_sets_do_not_overlap() -> None:
    assert EXPERIMENTAL_STAGES.isdisjoint(PHASE_1_STAGES)


# --------------------------------------------------------------------------- #
# Criterion 4: the declared namespaces cover what the deployed Analysis writes.
# --------------------------------------------------------------------------- #


def test_every_collection_analysis_writes_is_declared_or_explicitly_not_consumed() -> None:
    snapshot = json.loads(ROUTING_PATH.read_text(encoding="utf-8"))
    namespace = ProjectNamespace(snapshot["provenance"]["project_id"])
    declared = {namespace.mongo_collection(kind) for kind in MONGO_KINDS}
    produced = set(snapshot["deployed_collections"])
    explained = set(snapshot["produced_but_not_consumed_by_visualization"])

    unexplained = sorted(produced - declared - explained)
    assert unexplained == [], (
        "Analysis produces these collections and the visualization neither "
        f"declares nor explains them: {unexplained}"
    )


def test_the_declared_names_match_the_deployed_convention() -> None:
    namespace = ProjectNamespace("ai26")
    assert namespace.mongo_collection("records") == "ai26__records"
    assert namespace.mongo_collection("analysis_results") == "ai26__analysis_results"
    assert namespace.mongo_collection("processing") == "ai26__processing"
    assert namespace.mongo_collection("periodic_summaries") == "ai26__periodic_summaries"
    snapshot = json.loads(ROUTING_PATH.read_text(encoding="utf-8"))
    assert snapshot["provenance"]["mongo_separator"] == namespace.mongo_separator


def test_the_absent_namespaces_stay_absent_by_design_under_the_phase_1_profile() -> None:
    snapshot = json.loads(ROUTING_PATH.read_text(encoding="utf-8"))
    produced = set(snapshot["deployed_collections"])
    for name in snapshot["absent_and_not_expected_under_the_phase_1_profile"]:
        assert name not in produced, (
            f"{name} now exists; the capability gate may have opened and this "
            "snapshot needs refreshing deliberately"
        )

import json
from pathlib import Path

from laclaugpt_visualization.data import load_frame
from laclaugpt_visualization.transforms import explore, monitor

FIXTURE = Path(__file__).parent / "fixtures" / "canonical_parity_v1.json"


def test_shared_canonical_parity_fixture_renders_generically():
    frame = load_frame(FIXTURE)
    assert len(frame) == 1
    row = frame.iloc[0]

    assert row["source_url"] == "https://example.invalid/laclaugpt/synthetic/record-001"
    assert row["source_native_ids"]["legacy_document_id"] == "legacy-001"
    assert row["raw_metadata"]["legacy_optional_field"] == "must-survive-roundtrip"

    assert row["transcript"] == "A synthetic transcript segment."
    assert row["ocr"] == ["SYNTHETIC ONLY"]
    assert row["frames"][0]["media_ref"] == "fixture://canonical-parity-v1/frame/002"
    assert row["media_references"][0]["ref"] == "fixture://canonical-parity-v1/media/video"

    assert row["uncertainties"][0]["value"] == 0.64
    assert row["codebook_refs"][0]["id"] == "synthetic-codebook"
    assert row["model_runs"][0]["model"] == "fixture-model"
    assert row["provenance"][-1]["provenance_id"] == "prov_analysis_001"
    assert row["review_status"] == "PROVISIONAL"
    assert row["analysis_objects"][0]["epistemic_type"] == "CANDIDATE_INTERPRETATION"
    assert row["analysis_objects"][0]["review_status"] == "PROVISIONAL"
    assert row["evidence"][0]["provenance_id"] == "prov_analysis_001"

    metrics = monitor(frame)
    assert metrics["documents"] == 1
    assert metrics["analyzed"] == 1
    assert metrics["awaiting_review"] == 1

    views = explore(frame)
    assert views["formations"].iloc[0]["formations"] == "synthetic formation"
    assert views["topics"].iloc[0]["topics"] == "synthetic governance"
    assert views["entities"].iloc[0]["entities"] == "the system"


def test_shared_fixture_partial_optional_sections_are_safe(tmp_path):
    record = json.loads(FIXTURE.read_text(encoding="utf-8"))
    record.pop("alignments")
    record["content"].pop("ocr")
    record["content"].pop("frames")
    record["analysis"].pop("uncertainty")
    record["analysis"].pop("codebook_refs")
    record["review"] = {}

    path = tmp_path / "partial.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    frame = load_frame(path)
    row = frame.iloc[0]

    assert row["alignments"] == []
    assert row["ocr"] == []
    assert row["frames"] == []
    assert row["uncertainties"] == []
    assert row["codebook_refs"] == []
    assert row["review_status"] == "PROVISIONAL"
    assert monitor(frame)["documents"] == 1

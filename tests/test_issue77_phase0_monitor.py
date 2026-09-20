from __future__ import annotations

from laclaugpt_visualization.data import frame_from_records
from laclaugpt_visualization.transforms import monitor


def _record(
    source_url: str,
    *,
    source_date: str = "",
    stage_status: str = "pending",
    updated_at: str = "",
    actor: str = "",
    formation: str = "",
    signifiers: list[str] | None = None,
) -> dict:
    discourse: dict[str, object] = {"status": stage_status}
    if updated_at:
        discourse["updated_at"] = updated_at
    record = {
        "source_url": source_url,
        "source_date": source_date,
        "actor_name": actor,
        "phase0": {
            "preprocess": {"status": "ok"},
            "summary": {"status": "ok"} if stage_status == "ok" else {"status": "pending"},
            "postprocess": {"status": "ok"} if stage_status == "ok" else {"status": "pending"},
            "discourse": discourse,
        },
        "phase0_discourse": {"signifiers": signifiers or []},
    }
    if formation:
        record["ai_formation"] = formation
    return record


def test_phase0_monitor_counts_analyzed_awaiting_and_error_records() -> None:
    records = [
        _record(
            "urn:analyzed",
            source_date="2026-09-18T10:00:00Z",
            stage_status="ok",
            updated_at="2026-09-18T10:05:00Z",
            actor="Actor A",
            formation="Formation A",
            signifiers=["future"],
        ),
        _record("urn:awaiting", source_date="2026-09-18T11:00:00Z"),
        _record(
            "urn:error",
            source_date="2026-09-18T12:00:00Z",
            stage_status="error",
            updated_at="2026-09-18T12:05:00Z",
            actor="Actor A",
        ),
    ]

    values = monitor(frame_from_records(records))

    assert values["documents"] == 3
    assert values["analyzed"] == 1
    assert values["awaiting_analysis"] == 1
    assert values["errors"] == 1
    assert values["latest_source"] == "2026-09-18T12:00:00+00:00"
    assert values["latest_analysis"] == "2026-09-18T12:05:00+00:00"
    assert values["actors"].to_dict(orient="records") == [{"source_author": "Actor A", "count": 2}]
    assert values["formations"].to_dict(orient="records") == [
        {"formations": "Formation A", "count": 1}
    ]
    assert values["signifiers"].to_dict(orient="records") == [
        {"signifiers": "future", "count": 1}
    ]


def test_phase0_monitor_handles_missing_timestamps_and_empty_labels() -> None:
    values = monitor(frame_from_records([_record("urn:empty")]))

    assert values["documents"] == 1
    assert values["analyzed"] == 0
    assert values["awaiting_analysis"] == 1
    assert values["errors"] == 0
    assert values["latest_source"] == ""
    assert values["latest_analysis"] == ""
    assert values["formations"].empty
    assert values["signifiers"].empty
    assert values["actors"].empty


def test_phase0_monitor_marks_frequency_as_descriptive_only() -> None:
    note = str(monitor(frame_from_records([_record("urn:note")]))["frequency_note"]).casefold()

    assert "descriptive" in note
    assert "hegemony" in note
    assert "nodal status" in note
    assert "ideology identity" in note

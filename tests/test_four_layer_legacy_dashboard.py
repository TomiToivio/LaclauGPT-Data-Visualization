from pathlib import Path

from laclaugpt_visualization.data import frame_from_records


def _canonical_record() -> dict:
    return {
        "schema_version": "1.1.0",
        "source_url": "https://example.invalid/post/1",
        "source_native_ids": {"video_id": "vid-1", "new_id": "new-1"},
        "raw_capture": {
            "ref": "raw/x/1.json",
            "payload": {"id": "1", "native": {"kept": True}},
            "checksum": None,
            "content_type": "application/json",
            "captured_at": "2026-09-16T00:00:00Z",
            "metadata": {},
        },
        "source": {
            "platform": "x",
            "source_type": "post",
            "author": "synthetic",
            "country": "XX",
            "language": "en",
            "created_at": "2026-09-16T00:00:00Z",
            "raw_ref": "raw/x/1.json",
        },
        "content": {
            "text": "Collected text",
            "transcripts": [
                {
                    "id": "t1",
                    "text": "Whisper transcript",
                    "language": "en",
                    "translated_text": "Translated transcript",
                }
            ],
            "ocr": [{"id": "ocr_1", "text": "OCR text"}],
            "frames": [{"id": "frame_1", "timestamp_seconds": 0, "description": "Frame description"}],
            "media_references": [],
            "file_references": [],
        },
        "intermediate": {
            "asr": [{"id": "t1", "text": "Whisper transcript"}],
            "ocr": [{"id": "ocr_1", "text": "OCR text"}],
            "frames": [{"id": "frame_1", "timestamp_seconds": 0}],
            "frame_analysis": [{"id": "frame_1", "description": "Frame description"}],
            "translations": [{"id": "tr1", "text": "Translated transcript"}],
            "stage_outputs": {"llm_analysis": [{"proposal": {"summary": "Analysis summary"}}]},
        },
        "evidence": [],
        "analysis": {
            "status": "analyzed",
            "summary": "Analysis summary",
            "entities": [{"label": "Entity A"}],
            "topics": [{"canonical_label": "Topic A"}],
            "formations": [{"label": "Formation A"}],
            "signifiers": [{"label": "Signifier A"}],
            "discourses": [{"label": "Discourse A"}],
            "sentiments": [{"label": "positive"}],
            "model_runs": [],
        },
        "human_readable": {
            "summary": "Researcher summary",
            "markdown": "# Researcher report\n\nEverything important.",
            "generated_at": "2026-09-16T00:00:00Z",
            "generator": "synthetic",
            "sections": {},
        },
        "provenance": [],
        "review": {},
        "legacy": {"lda_topic": "Legacy topic 7", "political_preference": "synthetic"},
    }


def test_canonical_dashboard_view_contains_legacy_and_new_fields() -> None:
    frame = frame_from_records([_canonical_record()])
    row = frame.iloc[0]

    assert row["whisper_transcript"] == "Whisper transcript"
    assert row["whisper_language"] == "en"
    assert row["whisper_translated"] == "Translated transcript"
    assert row["ocr_1"] == "OCR text"
    assert row["frame_1"] == "Frame description"
    assert row["summary_analysis"] == "Analysis summary"
    assert row["human_readable_summary"] == "Researcher summary"
    assert row["raw_ref"] == "raw/x/1.json"
    assert row["raw_payload"]["native"]["kept"] is True
    assert row["lda_topic"] == "Legacy topic 7"
    assert row["entities"] == ["Entity A"]
    assert row["formations"] == ["Formation A"]
    assert row["intermediate"]["stage_outputs"]["llm_analysis"]


def test_legacy_flat_row_keeps_old_dashboard_columns() -> None:
    frame = frame_from_records(
        [
            {
                "new_id": "legacy-1",
                "source_type": "tiktok",
                "country": "FI",
                "whisper_transcript": "Old whisper",
                "whisper_language": "fi",
                "whisper_translated": "Old translation",
                "ocr_1": "Old OCR",
                "frame_1": "Old frame analysis",
                "summary_analysis": "Old summary",
                "formula_of_populism_analysis": "Old populism analysis",
                "lda_topic": "Old LDA topic",
                "new_entity": "Person A",
                "new_theme": "Theme A",
            }
        ]
    )
    row = frame.iloc[0]
    assert row["whisper_transcript"] == "Old whisper"
    assert row["ocr_1"] == "Old OCR"
    assert row["frame_1"] == "Old frame analysis"
    assert row["summary_analysis"] == "Old summary"
    assert row["formula_of_populism_analysis"] == "Old populism analysis"
    assert row["lda_topic"] == "Old LDA topic"
    assert row["entities"] == ["Person A"]
    assert row["topics"] == ["Theme A"]


def test_dashboard_source_always_exposes_research_layers() -> None:
    source = (Path(__file__).parents[1] / "src" / "laclaugpt_visualization" / "app.py").read_text(
        encoding="utf-8"
    )
    for label in (
        "Research Data",
        "Legacy researcher fields",
        "Raw collected/scraped material",
        "Intermediate stage outputs",
        "New structured LaclauGPT analysis",
        "Human-readable research report",
    ):
        assert label in source

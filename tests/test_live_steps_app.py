"""The live steps app, asserted by behaviour: it renders, filters and never fabricates a stage.

`streamlit.testing.v1.AppTest` executes the real script, so these pin the numbers a researcher reads
(unfiltered totals equal the manifest) and the honesty rules (a stage the export lacks reads as
unavailable, not as zero).
"""
from __future__ import annotations

import csv
import importlib.util
import json
import os
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src" / "laclaugpt_visualization" / "live_steps_app.py"
BUILDER = ROOT / "tools" / "build_live_steps_artifacts.py"

HEADER = ["_storage_id", "country", "video_id", "allas_filename", "source_type",
          "political_preference", "video_duration_seconds", "asr_transcript", "asr_language",
          "ocr_1", "frame_analysis_1", "vllm_video_analysis", "summary_analysis",
          "summary_summary_md", "postprocess_entities", "postprocess_themes", "laclau_status",
          "laclau_structured_json", "dna_status", "dna_statements_json", "sna_status",
          "sna_edges_json", "positive", "neutral", "negative", "processing_status",
          "preprocess_status", "frame_analysis_status", "vllm_video_status",
          "summary_quality_status", "step_01_status", "step_02_status", "step_03_status",
          "step_04_status", "step_05_status", "step_06_status", "step_07_status",
          "rag_context_json", "vllm_video_prompt"]


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, path
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = _load(BUILDER, "build_live_steps_artifacts_app_test")


def row(country: str, index: int, *, platform: str = "Instagram",
        preference: str = "Centre right", with_sna: bool = True) -> dict:
    video = f"HEPP24-{country[:2].upper()}-RG-IG-2024060{index}-100000"
    return {
        "_storage_id": f"monday500:{country}:{index}", "country": country, "video_id": video,
        "allas_filename": f"https://example.invalid/{video}.mp4", "source_type": platform,
        "political_preference": preference, "video_duration_seconds": "120",
        "asr_transcript": "a transcript", "asr_language": "fi", "ocr_1": "on-screen text",
        "frame_analysis_1": "a frame", "vllm_video_analysis": "the video shows a rally",
        "summary_analysis": "summary", "summary_summary_md": "summary md",
        "postprocess_entities": '["Entity A"]', "postprocess_themes": '["grievance politics"]',
        "laclau_status": "ok", "laclau_structured_json": "{}", "dna_status": "ok",
        "dna_statements_json": json.dumps([{"statement_id": f"s{index}", "actor_name_raw": "Actor A"}]),
        "sna_status": "ok" if with_sna else "",
        "sna_edges_json": json.dumps([{"source": "Actor A", "target": "Actor B",
                                       "edge_type": "critique", "confidence": 0.8,
                                       "evidence_quote": "after rolling back"}]) if with_sna else "",
        "positive": '["Entity A"]', "neutral": "[]", "negative": '["Entity B"]',
        "processing_status": "OK", "preprocess_status": "ok", "frame_analysis_status": "ok",
        "vllm_video_status": "ok", "summary_quality_status": "OK",
        "rag_context_json": "{}", "vllm_video_prompt": "a prompt",
        **{f"step_0{step}_status": "complete" for step in range(1, 8)},
    }


class LiveStepsAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import tempfile

        cls._temporary = tempfile.TemporaryDirectory()
        base = Path(cls._temporary.name)
        source = base / "src"
        source.mkdir()
        records = {
            "finland": [row("finland", 1), row("finland", 2, platform="Tiktok",
                                               preference="Far right", with_sna=False)],
            "poland": [row("poland", 3)],
            "portugal": [row("portugal", 4)],
        }
        for country, rows in records.items():
            path = source / f"{country}_live_steps_1_7.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=HEADER, extrasaction="ignore")
                writer.writeheader()
                for item in rows:
                    writer.writerow(item)
        cls.data = base / "data"
        builder.main(["--source-dir", str(source), "--out", str(cls.data)])
        cls.manifest = json.loads((cls.data / "MANIFEST.json").read_text(encoding="utf-8"))
        os.environ["LACLAUGPT_VIS_LIVE_STEPS_DATA"] = str(cls.data)

    @classmethod
    def tearDownClass(cls) -> None:
        os.environ.pop("LACLAUGPT_VIS_LIVE_STEPS_DATA", None)
        cls._temporary.cleanup()

    def app(self) -> AppTest:
        at = AppTest.from_file(str(APP), default_timeout=300)
        at.run()
        return at

    def test_it_renders_without_exceptions_and_reports_the_manifest_totals(self):
        at = self.app()
        self.assertEqual([str(e.value) for e in at.exception], [])
        metrics = {metric.label: metric.value for metric in at.metric}
        self.assertEqual(metrics["Videos"].replace(",", ""),
                         str(self.manifest["records"]))
        self.assertEqual(metrics["Countries"], "3")
        self.assertTrue(at.get("plotly_chart"), "the overview must draw charts, not only text")
        self.assertGreaterEqual(len(at.dataframe), 5)

    def test_the_country_filter_narrows_every_view(self):
        at = self.app()
        country = next(w for w in at.multiselect if w.label == "Country")
        country.set_value(["poland"])
        at.run()
        self.assertEqual([str(e.value) for e in at.exception], [])
        self.assertIn("1 of 4 videos match", " ".join(caption.value for caption in at.caption))

    def test_a_stage_the_export_lacks_reads_as_unavailable_not_zero(self):
        """Build a second cut without the video-VLM column and point the app at it."""
        header = [name for name in HEADER if name != "vllm_video_analysis"]
        source = Path(self._temporary.name) / "src_missing_stage"
        source.mkdir()
        data = Path(self._temporary.name) / "data_missing_stage"
        for country in ("finland", "poland", "portugal"):
            with (source / f"{country}_live_steps_1_7.csv").open("w", newline="",
                                                                 encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=header, extrasaction="ignore")
                writer.writeheader()
                writer.writerow(row(country, 9))
        builder.main(["--source-dir", str(source), "--out", str(data)])
        os.environ["LACLAUGPT_VIS_LIVE_STEPS_DATA"] = str(data)
        try:
            texts = " ".join(str(element.value) for element in self.app().dataframe)
        finally:
            os.environ["LACLAUGPT_VIS_LIVE_STEPS_DATA"] = str(self.data)
        self.assertIn("unavailable in this source", texts)

    def test_the_data_quality_tab_keeps_the_dropped_columns_visible(self):
        at = self.app()
        frames = [frame.value for frame in at.dataframe]
        dropped = [frame for frame in frames
                   if "reason" in getattr(frame, "columns", [])]
        self.assertTrue(dropped, "the dropped-column table must be rendered")
        self.assertIn("column", dropped[0].columns)


if __name__ == "__main__":
    unittest.main()

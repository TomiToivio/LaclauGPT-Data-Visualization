"""Synthetic, privacy-safe tests for researcher-facing output in issue #62."""
from __future__ import annotations

import unittest

from laclaugpt_visualization.researcher_views import (
    dna_network_figure, evidence_fields, readable_value, statement_links, status_label,
)


class ResearcherViewTests(unittest.TestCase):
    def test_producer_stage_mapping_is_preserved(self):
        expected = {
            1: "asr_transcript", 2: "ocr_1", 3: "frame_analysis_1",
            4: "vllm_video_analysis", 5: "summary_analysis",
            6: "laclau_structured_json", 7: "dna_statements_json",
        }
        for stage, field in expected.items():
            self.assertIn(field, [name for name, _ in evidence_fields(
                stage, {"step_01_status": "complete"}, {field: "synthetic evidence"})])

    def test_missing_outputs_are_not_invented(self):
        self.assertEqual(evidence_fields(7, {}, {}), [])
        self.assertEqual(status_label(None), "Not reported / unavailable")
        self.assertEqual(status_label("failed"), "failed")

    def test_json_is_parsed_without_discaring_invalid_source(self):
        self.assertEqual(readable_value('[{"actor": "test"}]'), [{"actor": "test"}])
        self.assertEqual(readable_value("{broken"), "{broken")

    def test_only_observed_statement_links_appear(self):
        statements = [
            {"actor_name_raw": "A", "concept": "C", "evidence_quote": "quote"},
            {"actor_name_raw": "A", "concept": "C"},
            {"actor_name_raw": "B", "concept": "D"},
            {"actor_name_raw": "C"},
        ]
        self.assertEqual(statement_links(statements), [("A", "C", 2), ("B", "D", 1)])
        fig = dna_network_figure(statements)
        self.assertIsNotNone(fig)
        self.assertIsNone(dna_network_figure([{"actor_name_raw": "A"}]))

    def test_evidence_prefers_bundle_and_keeps_index_metadata(self):
        fields = dict(evidence_fields(1, {"asr_language": "fi", "asr_transcript": "index"},
                                      {"asr_transcript": "verbatim bundle"}))
        self.assertEqual(fields["asr_transcript"], "verbatim bundle")
        self.assertEqual(fields["asr_language"], "fi")


if __name__ == "__main__":
    unittest.main()

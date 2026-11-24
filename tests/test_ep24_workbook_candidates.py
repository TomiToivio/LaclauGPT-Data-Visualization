from dashboards.ep24_merge_lab.workbook_candidates import build_plan


def test_protected_candidates_and_chains():
    pairs = [
        {"alias": "A", "canonical": "Alpha (Party; Country)", "sheet": "Sheet", "row": 2},
        {"alias": "B", "canonical": "Intermediate", "sheet": "Sheet", "row": 3},
        {"alias": "Intermediate", "canonical": "Final", "sheet": "Sheet", "row": 4},
    ]
    coverage = {
        "inputs": [],
        "workbook_evidence": {"sources": {"person": {
            "pairs": pairs, "sha256": "test", "conflicts": {},
        }}},
        "categories": {"person": {
            "matched": [{"alias": p["alias"], "canonical": p["canonical"]} for p in pairs[:2]],
            "unmatched": ["alpha (party; country)", "Unrelated"],
            "conflicting": [],
            "counts": {"observed": 4},
        }},
    }
    plan = build_plan(coverage)
    result = plan["categories"]["person"]
    assert result["protected_candidates"][0]["canonical"] == "Alpha (Party; Country)"
    assert result["protected_candidates"][0]["provenance"][0]["rows"][0]["row"] == 2
    assert result["quarantined_candidates"][0]["canonical"] == "Intermediate"
    assert result["reserved_unmatched"] == ["alpha (party; country)"]
    assert result["matcher_only"] == ["Unrelated"]
    assert not plan["activation_authorized"]
    assert plan == build_plan(coverage)

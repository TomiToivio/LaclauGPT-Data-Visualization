"""Regression tests for #315 frozen review identities."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dashboards"))
from ep24_merge_lab.review import inventory


def test_freeze_digest_stable_and_verified(tmp_path):
    unit = inventory.DecisionUnit("id", "entity", "cluster", ["A"], "A", 1, 1.0, "test")
    path = tmp_path / "inventory.json"
    first = inventory.freeze(tmp_path, path, [unit])
    second = inventory.freeze(tmp_path, path, [unit])
    assert first["digest"] == second["digest"]
    inventory.load_inventory(path)
    data = json.loads(path.read_text())
    data["units"][0]["canonical"] = "changed"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="digest"):
        inventory.load_inventory(path)


def test_polarity_is_part_of_identity():
    assert inventory._unit_id("sentiment", "cluster", ["A"], "positive") != inventory._unit_id(
        "sentiment", "cluster", ["A"], "negative"
    )


def test_duplicate_ids_rejected(tmp_path):
    unit = inventory.DecisionUnit("id", "entity", "cluster", ["A"], "A", 1, 1.0, "test")
    with pytest.raises(ValueError, match="Duplicate"):
        inventory.freeze(tmp_path, tmp_path / "inventory.json", [unit, unit])

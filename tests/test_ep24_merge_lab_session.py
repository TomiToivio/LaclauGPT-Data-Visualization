"""Synthetic legacy rows. Each occurrence retains the source observation."""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ep24/merge_lab"))
from lab import FIELDS, connect, curated_rows, current, inventory, save


class TestMergeLab(unittest.TestCase):
    def test_inventory_review_export_and_resume(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        tmp_path = Path(directory.name)
        (tmp_path / ".git").mkdir()
        source = tmp_path / "analysis/ep24/source"
        source.mkdir(parents=True)
        path = source / "fixture.csv"
        base = dict.fromkeys(FIELDS, "")
        rows = [dict(base, new_id=str(i), country="FI", new_entity=persons,
                     summary_analysis=context, new_theme="Health;Healthcare", topics="tax, Tax",
                     positive="hope", negative="hope", entities="EU, Euroopan unioni")
                for i, (persons, context) in enumerate([
                    ("Petteri Orpo;Prime Minister Orpo;PM Orpo;Orpo", "Petteri Orpo spoke"),
                    ("Other Orpo;Orpo", "Unspecified speaker")])]
        with path.open("w") as stream:
            writer = csv.DictWriter(stream, fieldnames=rows[0])
            writer.writeheader()
            writer.writerows(rows)
        seed = inventory([path], equivalents={"entities": {"euroopan unioni": "EU"}})
        exported = list(curated_rows(path, seed))
        assert exported[0]["new_entity"] == "Petteri Orpo"
        assert exported[1]["new_entity"] == "Other Orpo;Orpo"
        assert exported[0]["entities"] == "EU"
        assert exported[0]["new_theme"] == "Health;Healthcare"
        db, _ = connect(tmp_path)
        save(db, 0, "inventory", initial=seed)
        ids = [g for g, label in seed["names"].items() if label == "hope"]
        with self.assertRaises(ValueError):
            save(db, 1, "merge", (ids, "hope"))
        themes = [g for g, label in seed["names"].items() if label in ("Health", "Healthcare")]
        save(db, 1, "separate", (themes,))
        with self.assertRaises(ValueError):
            save(db, 2, "merge", (themes, "Health"))
        save(db, 2, "undo")
        save(db, 3, "redo")
        with self.assertRaises(ValueError):
            save(db, 2, "undo")
        db.close()
        db, _ = connect(tmp_path)
        assert current(db)[1]["separate"]
        save(db, 4, "undo")
        save(db, 5, "merge", (themes, "Policy"))
        state = current(db)[1]
        assert next(iter(curated_rows(path, state)))["new_theme"] == "Policy"
        save(db, 6, "split", ([themes[0]], "Health", state["groups"][themes[0]][0]))
        assert len(current(db)[1]["groups"]) == len(seed["groups"])


if __name__ == "__main__":
    unittest.main()

"""Exact approved cohort verification for the private EP24 researcher snapshot."""
from __future__ import annotations

import csv
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_ep24_dashboard", ROOT / "scripts" / "ep24" / "verify_researcher_dashboard.py"
)
assert SPEC and SPEC.loader
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)


def fixture(tmp_path: Path) -> tuple[Path, Path]:
    data = tmp_path / "data"
    cleaned = data / "cleaned"
    cleaned.mkdir(parents=True)
    roster = tmp_path / "monday500_roster.txt"
    identities = []
    for country in ("finland", "poland", "portugal"):
        with (cleaned / f"{country}_clean.csv").open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(["_storage_id", "country", "video_id"])
            for i in range(500):
                identity = f"monday500:{country}:{i:024x}"
                identities.append(identity)
                writer.writerow([identity, country, str(i)])
    roster.write_text("\n".join(identities) + "\n", encoding="utf-8")
    return data, roster


def statuses(results):
    return {item["check"]: item["status"] for item in results}


def test_exact_roster_passes(tmp_path):
    data, roster = fixture(tmp_path)
    result = VERIFY.check_approved_cohort(data, roster)
    assert set(statuses(result).values()) == {"PASS"}


def test_equal_row_counts_with_wrong_identity_fail(tmp_path):
    data, roster = fixture(tmp_path)
    path = data / "cleaned" / "poland_clean.csv"
    content = path.read_text()
    path.write_text(content.replace("monday500:poland:000000000000000000000000",
                                    "monday500:poland:ffffffffffffffffffffffff"))
    result = VERIFY.check_approved_cohort(data, roster)
    assert statuses(result)["approved membership · poland"] == "FAIL"
    assert "unapproved=1" in next(item["detail"] for item in result if item["check"] == "approved membership · poland")


def test_duplicate_identity_fails(tmp_path):
    data, roster = fixture(tmp_path)
    path = data / "cleaned" / "finland_clean.csv"
    content = path.read_text()
    path.write_text(content.replace("monday500:finland:000000000000000000000001",
                                    "monday500:finland:000000000000000000000000"))
    result = VERIFY.check_approved_cohort(data, roster)
    assert statuses(result)["approved membership · finland"] == "FAIL"


def test_missing_cleaned_frame_fails(tmp_path):
    data, roster = fixture(tmp_path)
    (data / "cleaned" / "portugal_clean.csv").unlink()
    result = VERIFY.check_approved_cohort(data, roster)
    assert statuses(result)["approved membership · portugal"] == "FAIL"


def test_invalid_roster_fails_closed(tmp_path):
    data, roster = fixture(tmp_path)
    roster.write_text(roster.read_text().replace("monday500:finland:", "wrong:finland:", 1))
    result = VERIFY.check_approved_cohort(data, roster)
    assert statuses(result)["approved roster"] == "FAIL"

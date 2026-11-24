"""Synthetic tests; no private workbook contents."""
from pathlib import Path

import pytest

from dashboards.ep24_merge_lab.workbook_evidence import FILES, inspect_workbooks


def test_workbook_provenance_and_conflicts(tmp_path: Path):
    from openpyxl import Workbook

    for name in FILES.values():
        book = Workbook()
        sheet = book.active
        sheet.append(["old", "new"])
        sheet.append(["Example", "Example (Party; Country)"])
        sheet.append(["example", "Another identity"])
        sheet.append(["missing", None])
        book.save(tmp_path / name)
    result = inspect_workbooks(tmp_path)
    for source in result["sources"].values():
        assert len(source["sha256"]) == 64
        assert source["pairs"][0]["row"] == 2
        assert source["pairs"][0]["canonical"] == "Example (Party; Country)"
        assert "example" in source["conflicts"]
        assert source["sheets"][0]["incomplete_rows"] == [4]
    assert not result["activation_authorized"]


def test_lfs_pointer_is_not_a_workbook(tmp_path: Path):
    (tmp_path / "entities.xlsx").write_text("version https://git-lfs.github.com/spec/v1\n")
    with pytest.raises(ValueError, match="hydrate Git LFS"):
        inspect_workbooks(tmp_path)

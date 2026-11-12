"""
The walkthrough Excel may keep all steps in one cell, or one step per row
(S. No., Feature Name and Feature Key only on the first row, as merged cells).
Both layouts must load every step.
"""
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.services.walkthrough_access_service import WALKTHROUGH_FILE, WalkthroughEngine

HEADER = ["S. No.", "Feature Name", "Step-by-Step Walkthrough", "Feature Key "]


def engine_from(tmp_path, rows, merge=()):
    book = Workbook()
    sheet = book.active
    sheet.append(HEADER)
    for row in rows:
        sheet.append(row)
    for cell_range in merge:
        sheet.merge_cells(cell_range)
    book.save(tmp_path / WALKTHROUGH_FILE)
    return WalkthroughEngine(directory=tmp_path)


def test_one_cell_layout_unchanged(tmp_path):
    e = engine_from(tmp_path, [
        ["1", "Change Password", "Step 1: A\nStep 2: B\nStep 3: C", "ChangePassword"],
        ["2", "Log Out", "Step 1: X\nStep 2: Y", "Logout"],
    ])
    assert e.guides["change password"].steps == "Step 1: A\nStep 2: B\nStep 3: C"
    assert e.guides["log out"].steps == "Step 1: X\nStep 2: Y"


def test_one_step_per_row_layout(tmp_path):
    e = engine_from(tmp_path, [
        ["1", "Unit Details Page", "Step 1: A", "UDPage"],
        [None, None, "Step 2: B", None],
        [None, None, "Step 3: C", None],
        ["2", "Daily Activity Report", "Step 1: X", "DARView,DARCreate"],
        [None, None, "Step 2: Y", None],
    ], merge=["A2:A4", "B2:B4", "D2:D4", "A5:A6", "B5:B6", "D5:D6"])

    assert e.guides["unit details page"].steps == "Step 1: A\nStep 2: B\nStep 3: C"
    assert e.guides["daily activity report"].steps == "Step 1: X\nStep 2: Y"
    assert e.guides["daily activity report"].key == "DARView,DARCreate"
    assert e.issues == []


def test_mixed_layouts(tmp_path):
    e = engine_from(tmp_path, [
        ["1", "Log Out", "Step 1: X\nStep 2: Y", "Logout"],
        ["2", "My Profile", "Step 1: A", "MyProfile"],
        [None, None, "Step 2: B", None],
    ])
    assert e.guides["log out"].steps == "Step 1: X\nStep 2: Y"
    assert e.guides["my profile"].steps == "Step 1: A\nStep 2: B"


def test_numbered_row_without_name_ends_the_walkthrough(tmp_path):
    e = engine_from(tmp_path, [
        ["1", "Log Out", "Step 1: X", "Logout"],
        [None, None, "Step 2: Y", None],
        ["24", None, None, None],
        [None, None, "Stray text", None],
    ])
    assert e.guides["log out"].steps == "Step 1: X\nStep 2: Y"


def test_not_authorized_row_is_not_a_walkthrough_or_a_step(tmp_path):
    e = engine_from(tmp_path, [
        ["1", "Log Out", "Step 1: X", "Logout"],
        ["25", "Based on the login if any feature is not authorized. ", "Great question!", None],
        [None, None, "More text", None],
    ])
    assert list(e.guides) == ["log out"]
    assert e.guides["log out"].steps == "Step 1: X"


def test_key_on_a_later_row_is_used_when_first_row_has_none(tmp_path):
    e = engine_from(tmp_path, [
        ["1", "Log Out", "Step 1: X", None],
        [None, None, "Step 2: Y", "Logout"],
    ])
    assert e.guides["log out"].key == "Logout"


def test_name_without_any_step_is_skipped(tmp_path):
    e = engine_from(tmp_path, [
        ["1", "Log Out", None, "Logout"],
        ["2", "My Profile", "Step 1: A", "MyProfile"],
    ])
    assert list(e.guides) == ["my profile"]


def test_duplicate_feature_still_rejected(tmp_path):
    with pytest.raises(ValueError, match="Duplicate walkthrough feature"):
        engine_from(tmp_path, [
            ["1", "Log Out", "Step 1: X", "Logout"],
            ["2", "Log Out", "Step 1: Y", "Logout"],
        ])


# ---------------------------------------------------------------------------
# The real workbook
# ---------------------------------------------------------------------------

REAL = WalkthroughEngine(directory=Path("app/data/walkthrough"))


def test_real_workbook_has_every_walkthrough_with_a_key():
    assert len(REAL.guides) == 22
    assert REAL.issues == []


@pytest.mark.parametrize("name", sorted(REAL.guides))
def test_real_workbook_every_walkthrough_has_all_its_steps(name):
    steps = [line for line in REAL.guides[name].steps.splitlines() if line.strip()]
    assert len(steps) >= 2, name
    for number, line in enumerate(steps, start=1):
        assert line.strip().lower().startswith(f"step {number}"), (name, line)


def test_real_workbook_daily_activity_report_steps():
    assert REAL.guides["daily activity report"].steps.splitlines() == [
        "Step 1: Select the MENU tab from the navigation bar.",
        "Step 2: Scroll down and select Reporting-> Daily Activity Report.",
        "Step 3: Click on New DAR Request to log your daily activity.",
    ]

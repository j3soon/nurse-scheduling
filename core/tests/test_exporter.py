"""Focused tests for exporter helpers and formatting edge cases."""

# This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
#
# Copyright (C) 2023-2026 Johnson Sun
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# This test is mostly AI generated.

import os
import sys
from io import BytesIO

import pandas as pd
import pytest
from openpyxl import load_workbook

# Add the project root to the Python path so imports will work when running directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nurse_scheduling import exporter, schedule


def test_export_to_csv_writes_utf8_bom():
    df = pd.DataFrame([["A", "B"], ["C", "D"]])
    output = BytesIO()

    exporter.export_to_csv(df, output)

    payload = output.getvalue()
    assert payload.startswith(b"\xef\xbb\xbf")
    assert payload.decode("utf-8-sig") == "A,B\nC,D\n"


def test_export_to_excel_supports_legacy_comment_info_shape():
    df = pd.DataFrame([["x"]])
    output = BytesIO()

    # Legacy shape: {(row, col): [weights]}
    exporter.export_to_excel(df, output, {(1, 1): [3, 7]})

    wb = load_workbook(output)
    ws = wb.active
    assert ws["A1"].comment is not None
    assert "Weights of unmet single-style requests: 10" in ws["A1"].comment.text
    assert "3, 7" in ws["A1"].comment.text


def test_export_to_excel_applies_style_and_font_contrast():
    df = pd.DataFrame([["dark", "light"]])
    output = BytesIO()
    cell_export_info = {
        "comments": {},
        "styles": {
            (1, 1): {"backgroundColor": "#111111"},
            (1, 2): {"backgroundColor": "#f5f5f5", "bottomBorderColor": "#0ea5e9"},
        },
    }

    exporter.export_to_excel(df, output, cell_export_info)

    wb = load_workbook(output)
    ws = wb.active
    assert ws["A1"].fill.fgColor.rgb == "FF111111"
    assert ws["A1"].font.color is not None
    assert ws["A1"].font.color.rgb == "FFFFFFFF"
    assert ws["B1"].fill.fgColor.rgb == "FFF5F5F5"
    assert ws["B1"].font.color is not None
    assert ws["B1"].font.color.rgb == "FF000000"
    assert ws["B1"].border.bottom.color is not None
    assert ws["B1"].border.bottom.color.rgb == "FF0EA5E9"


def test_prettify_generates_comment_info_for_unmet_single_style_requests():
    yaml_content = b"""
apiVersion: alpha
dates:
  range:
    startDate: 2025-01-01
    endDate: 2025-01-02
people:
  items:
    - id: n1
      history: [D]
shiftTypes:
  items:
    - id: D
preferences:
  - type: at most one shift per day
  - type: shift type requirement
    shiftType: D
    requiredNumPeople: 1
    qualifiedPeople: ALL
    date: ALL
    weight: -1
  - type: shift request
    person: n1
    date: ["2025-01-01"]
    shiftType: D
    weight: -10
"""

    df, _solution, _score, _status, cell_export_info = schedule(yaml_content, prettify=True)
    assert hasattr(df, "to_excel")
    assert "comments" in cell_export_info
    assert "styles" in cell_export_info
    assert cell_export_info["comments"]

    first_target_cell = next(iter(cell_export_info["comments"].keys()))
    output = BytesIO()
    exporter.export_to_excel(df, output, cell_export_info)

    wb = load_workbook(output)
    ws = wb.active
    row, col = first_target_cell
    comment = ws.cell(row=row, column=col).comment
    assert comment is not None
    assert "Weight of unmet single-style request: 10" in comment.text


def test_invalid_row_target_in_export_formatting_raises():
    yaml_content = b"""
apiVersion: alpha
dates:
  range:
    startDate: 2025-01-01
    endDate: 2025-01-01
people:
  items:
    - id: n1
shiftTypes:
  items:
    - id: D
preferences:
  - type: at most one shift per day
  - type: shift type requirement
    shiftType: D
    requiredNumPeople: 1
    qualifiedPeople: ALL
    date: ALL
    weight: -1
export:
  formatting:
    - type: row
      targets: [unknown_person]
      backgroundColor: "#22c55e"
"""

    with pytest.raises(ValueError, match="Invalid person identifier"):
        schedule(yaml_content, prettify=False)


def test_invalid_cell_target_in_export_formatting_raises():
    yaml_content = b"""
apiVersion: alpha
dates:
  range:
    startDate: 2025-01-01
    endDate: 2025-01-01
people:
  items:
    - id: n1
shiftTypes:
  items:
    - id: D
preferences:
  - type: at most one shift per day
  - type: shift type requirement
    shiftType: D
    requiredNumPeople: 1
    qualifiedPeople: ALL
    date: ALL
    weight: -1
export:
  formatting:
    - type: cell
      targets: [UNKNOWN_SHIFT]
      backgroundColor: "#ef4444"
"""

    with pytest.raises(ValueError, match="Invalid shift type identifier"):
        schedule(yaml_content, prettify=False)

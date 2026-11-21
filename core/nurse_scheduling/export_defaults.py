"""Generate workbook defaults from the current Schedule Spec."""

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

# This file is mostly AI generated.


def generate_export_defaults(
    shift_type_ids: list[int | str], shift_group_ids: list[str], date_groups: set[str]
) -> dict:
    """Build workbook defaults from the current Schedule Spec entities."""
    selector = {"people": ["ALL"], "dates": ["ALL"], "shiftTypes": ["ALL", "OFF"]}
    preference = {
        "types": ["shift request"],
        "requestShape": ["person-item-to-date-item"],
        "weightRange": [-float("inf"), float("inf")],
    }
    formatting = [
        {"type": "cell", "appendText": " [{shortShiftType}]", **selector, "when": {"preference": preference}},
        {
            "type": "cell",
            "fontColor": "#c00000",
            "note": {"text": "Weight of unmet single-style request: {totalAbsWeight}"},
            **selector,
            "when": {"preference": {**preference, "satisfied": False}},
        },
        {"type": "history header", "backgroundColor": "#fefce8"},
        {"type": "history", "people": ["ALL"], "backgroundColor": "#fefce8"},
        {"type": "column", "dates": ["SATURDAY", "SUNDAY"], "backgroundColor": "#dbeafe"},
        {"type": "column", "dates": ["SATURDAY"], "rightBorderColor": "#9ca3af"},
    ]
    if "FREEDAY" in date_groups:
        formatting.append({"type": "column", "dates": ["FREEDAY"], "backgroundColor": "#dcfce7"})
    columns = [
        {
            "type": "count",
            "header": "OFF (Total)",
            "countShiftTypes": ["OFF"],
            "countDates": ["ALL"],
            "rightBorderColor": "#000000",
        }
    ]
    holiday_columns = [
        {"type": "count", "header": f"OFF ({group})", "countShiftTypes": ["OFF"], "countDates": [group]}
        for group in ("WORKDAY", "FREEDAY")
        if group in date_groups
    ]
    if holiday_columns:
        holiday_columns[-1]["rightBorderColor"] = "#000000"
    columns.extend(holiday_columns)
    columns.extend(
        [
            {"type": "count", "header": "OFF (Weekday)", "countShiftTypes": ["OFF"], "countDates": ["WEEKDAY"]},
            {
                "type": "count",
                "header": "OFF (Weekend)",
                "countShiftTypes": ["OFF"],
                "countDates": ["WEEKEND"],
                "rightBorderColor": "#000000",
            },
        ]
    )
    rows = []
    for index, shift_id in enumerate([*shift_type_ids, *shift_group_ids]):
        column = {
            "type": "count",
            "header": f"{shift_id} Count",
            "countShiftTypes": [shift_id],
            "countDates": ["ALL"],
        }
        row = {
            "type": "count",
            "header": f"{shift_id} Count",
            "countShiftTypes": [shift_id],
            "countPeople": ["ALL"],
        }
        if index == len(shift_type_ids) - 1:
            column["rightBorderColor"] = "#000000"
            row["bottomBorderColor"] = "#000000"
        columns.append(column)
        rows.append(row)
    return {"formatting": formatting, "extraColumns": columns, "extraRows": rows}

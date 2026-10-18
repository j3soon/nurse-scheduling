"""Tests for calendar date group generation from the authoritative frontend table."""

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

import copy
import json
import subprocess
import sys

import pytest

from nurse_scheduling.ai.attachment_tools.build_taiwan_holiday_groups import build_groups, load_calendar
from nurse_scheduling.ai.schema import TAIWAN_HOLIDAYS_SOURCE
from nurse_scheduling.ai.workspace import REFERENCE_ATTACHMENT_TOOLS

from .ai_test_helper import base_schedule_payload, schedule_yaml


def test_calendar_groups_include_holidays_and_makeup_workdays_without_mutating_input():
    schedule = base_schedule_payload()
    custom = {"id": "Custom", "description": "Preserve this", "members": ["01"]}
    schedule["dates"]["groups"] = [custom, {"id": "FREEDAY", "description": "Old", "members": ["17"]}]
    before = copy.deepcopy(schedule)
    result = build_groups(schedule, TAIWAN_HOLIDAYS_SOURCE, start="2024-02-01", end="2024-02-18")
    assert result["groups"] == [
        custom,
        {
            "id": "WORKDAY",
            "description": "Taiwan workdays imported from the current holiday calendar",
            "members": ["01", "02", "05", "06", "07", "15", "16", "17"],
        },
        {
            "id": "FREEDAY",
            "description": "Taiwan freedays imported from the current holiday calendar",
            "members": ["03", "04", "08", "09", "10", "11", "12", "13", "14", "18"],
        },
    ]
    assert schedule == before


@pytest.mark.parametrize(
    "first,last,expected",
    [
        ("2024-02-29", "2024-03-01", ["02-29", "03-01"]),
        ("2024-12-31", "2025-01-02", ["2024-12-31", "2025-01-02"]),
    ],
)
def test_calendar_ids_match_frontend_month_and_year_boundaries(first, last, expected):
    groups = build_groups(base_schedule_payload(), TAIWAN_HOLIDAYS_SOURCE, start=first, end=last)["groups"]
    assert groups[-2]["members"] == expected


@pytest.mark.parametrize(
    "first,last", [("2027-01-01", "2027-01-02"), ("2024-02-20", "2024-02-01"), ("2024-02-01", None)]
)
def test_calendar_rejects_unsupported_reversed_and_incomplete_ranges(first, last):
    with pytest.raises(ValueError):
        build_groups(base_schedule_payload(), TAIWAN_HOLIDAYS_SOURCE, start=first, end=last)


def test_changed_calendar_format_fails_instead_of_falling_back_to_weekends(tmp_path):
    source = TAIWAN_HOLIDAYS_SOURCE.read_text(encoding="utf-8")
    calendar = tmp_path / "calendar.ts"
    calendar.write_text(source.replace("['2024-02-17',", "['invalid-date',"), encoding="utf-8")
    with pytest.raises(ValueError, match="calendar row"):
        load_calendar(calendar)


def test_calendar_cli_works_in_a_hydrated_directory_without_project_imports(tmp_path):
    source = REFERENCE_ATTACHMENT_TOOLS["/reference/tools/build_taiwan_holiday_groups.py"]
    tool = tmp_path / source.name
    tool.write_bytes(source.read_bytes())
    schedule = tmp_path / "schedule.yaml"
    schedule.write_text(schedule_yaml(), encoding="utf-8")
    before = schedule.read_bytes()
    completed = subprocess.run(
        [
            sys.executable,
            str(tool),
            str(schedule),
            "--calendar",
            str(TAIWAN_HOLIDAYS_SOURCE),
            "--start",
            "2024-02-01",
            "--end",
            "2024-02-18",
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "17" in json.loads(completed.stdout)["groups"][-2]["members"]
    assert schedule.read_bytes() == before

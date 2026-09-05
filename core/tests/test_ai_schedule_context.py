"""Tests for compact schedule context sent to the AI provider."""

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

from nurse_scheduling.ai.schedule_context import describe_schedule

from .ai_test_helper import base_schedule_payload, schedule_yaml


def test_describe_schedule_reports_shape_without_item_contents():
    payload = base_schedule_payload()
    payload["people"]["items"][0]["description"] = "private marker"

    summary = describe_schedule(schedule_yaml(payload))

    assert "2 people, 2 shift types, 2 preferences" in summary
    assert "Dates run from 2026-01-01 to 2026-01-02" in summary
    assert "Group ids: people PEOPLE" in summary
    assert "private marker" not in summary


def test_describe_schedule_reports_a_file_that_does_not_parse():
    assert describe_schedule("people: [unclosed\n") == "schedule.yaml is 1 lines and does not currently parse."

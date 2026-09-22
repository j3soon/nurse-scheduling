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


def test_describe_schedule_requires_reading_the_working_copy():
    payload = base_schedule_payload()
    payload["people"]["items"][0]["description"] = "private marker"

    summary = describe_schedule(schedule_yaml(payload))

    assert summary == "schedule.yaml is available at /workspace/schedule.yaml. Read it for schedule facts."
    assert "2026-01-01" not in summary
    assert "PEOPLE" not in summary
    assert "private marker" not in summary

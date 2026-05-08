"""Tests for scheduling progress events."""

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

from pathlib import Path

import nurse_scheduling
from nurse_scheduling.progress import ProgressEvent


VALID_YAML_FILE = Path(__file__).parent / "testcases" / "basics" / "01_1nurse_1shift_1day.yaml"


def test_schedule_emits_phase_progress_events():
    events: list[ProgressEvent] = []

    _df, _solution, score, status, _cell_export_info = nurse_scheduling.schedule(
        VALID_YAML_FILE.read_bytes(),
        progress=events.append,
    )

    assert score == 0
    assert status == "OPTIMAL"
    assert [event.code for event in events] == [
        "loading_scenario",
        "parsing_data",
        "initializing_solver",
        "creating_shift_variables",
        "creating_off_variables",
        "creating_lookup_maps",
        "adding_preferences",
        "solving",
        "exporting",
        "completed",
    ]
    assert events[-1].type == "completed"
    assert events[-1].progress == 1.0


def test_schedule_without_progress_preserves_result():
    events: list[ProgressEvent] = []

    _df_with, _solution_with, score_with, status_with, _info_with = nurse_scheduling.schedule(
        VALID_YAML_FILE.read_bytes(),
        progress=events.append,
    )
    _df_without, _solution_without, score_without, status_without, _info_without = nurse_scheduling.schedule(
        VALID_YAML_FILE.read_bytes(),
    )

    assert events
    assert score_with == score_without
    assert status_with == status_without

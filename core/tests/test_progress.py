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
VALID_PREFS_YAML_FILE = Path(__file__).parent / "testcases" / "basics" / "01_1nurse_1shift_1day_all_prefs.yaml"


def test_schedule_emits_phase_progress_events():
    events: list[ProgressEvent] = []

    _df, _solution, score, status, _cell_export_info = nurse_scheduling.schedule(
        VALID_YAML_FILE.read_bytes(),
        progress=events.append,
    )

    assert score == 0
    assert status == "OPTIMAL"
    phase_and_completion_codes = [event.code for event in events if event.type != "solution"]
    assert phase_and_completion_codes == [
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


def test_ortools_solver_emits_solution_progress_event():
    events: list[ProgressEvent] = []

    _df, _solution, _score, status, _cell_export_info = nurse_scheduling.schedule(
        VALID_PREFS_YAML_FILE.read_bytes(),
        progress=events.append,
        solver="ortools/cp-sat",
    )

    solution_events = [event for event in events if event.type == "solution"]
    assert status == "OPTIMAL"
    assert solution_events
    assert solution_events[0].code == "solution_found"
    assert solution_events[0].score is not None
    assert solution_events[0].solution_count is not None
    assert solution_events[0].elapsed_seconds is not None

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

# This test is mostly AI generated.

from datetime import UTC, datetime, timedelta
from pathlib import Path

import nurse_scheduling
from nurse_scheduling.jobs import JOB_TTL, MAX_EVENTS_PER_JOB, JobLimitError, OptimizationJobManager
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


def test_job_replays_terminal_completed_event_for_late_subscriber():
    manager = OptimizationJobManager()
    job = manager.create()

    job.emit(ProgressEvent(type="phase", code="loading_scenario", message="Loading scenario", progress=0.1))
    job.complete(filename="schedule.xlsx", xlsx_bytes=b"xlsx", score=0, solver_status="OPTIMAL")

    offset, events = job.events_after(0)

    assert offset == len(events)
    assert [event.type for event in events] == ["phase", "completed"]
    assert events[-1].code == "completed"
    assert job.snapshot()["status"] == "completed"


def test_job_replays_terminal_failed_event_for_late_subscriber():
    manager = OptimizationJobManager()
    job = manager.create()

    job.fail("Invalid scheduling data")

    _offset, events = job.events_after(0)

    assert [event.type for event in events] == ["failed"]
    assert events[-1].message == "Invalid scheduling data"
    assert job.snapshot()["status"] == "failed"


def test_job_cleanup_removes_expired_terminal_jobs():
    manager = OptimizationJobManager()
    job = manager.create()
    job.complete(filename="schedule.xlsx", xlsx_bytes=b"xlsx", score=0, solver_status="OPTIMAL")
    job.updated_at = datetime.now(UTC) - JOB_TTL - timedelta(seconds=1)

    manager.cleanup()

    assert manager.get(job.id) is None


def test_job_manager_rejects_too_many_running_jobs():
    manager = OptimizationJobManager()
    manager.create()
    manager.create()

    try:
        manager.create()
    except JobLimitError as exc:
        assert "running" in str(exc)
    else:
        raise AssertionError("Expected JobLimitError")


def test_terminal_event_survives_event_buffer_overflow():
    manager = OptimizationJobManager()
    job = manager.create()

    for index in range(MAX_EVENTS_PER_JOB):
        job.emit(ProgressEvent(type="phase", code=f"phase_{index}", message="Phase"))
    offset, _events = job.events_after(0)

    job.complete(filename="schedule.xlsx", xlsx_bytes=b"xlsx", score=0, solver_status="OPTIMAL")
    _next_offset, events = job.events_after(offset)

    assert [event.type for event in events] == ["completed"]

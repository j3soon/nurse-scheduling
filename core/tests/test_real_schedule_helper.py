"""Tests for the opt-in real-world scheduling smoke-test helper."""

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

from nurse_scheduling.solver_interface import SolverProgress
from tests.real import schedule_real_helper


def test_ortools_real_smoke_test_stops_after_progress_has_no_critical_notes(monkeypatch):
    seen = {}
    monotonic_time = 100.0
    final_export_info = {"comments": {}}

    def fake_monotonic():
        return monotonic_time

    def fake_schedule(_file_content, **kwargs):
        nonlocal monotonic_time
        seen.update(kwargs)
        critical_export_info = {"comments": {"cell": [f"{schedule_real_helper.CRITICAL_REQUEST_NOTE_PREFIX} D"]}}
        kwargs["progress_callback"](SolverProgress("test", 0, 0.5))
        assert not kwargs["should_stop"]()

        kwargs["progress_callback"](SolverProgress("test", 1, 1.0, cell_export_info=critical_export_info))
        assert not kwargs["should_stop"]()

        kwargs["progress_callback"](SolverProgress("test", 2, 2.0, cell_export_info=final_export_info))
        assert not kwargs["should_stop"]()
        monotonic_time += schedule_real_helper.ZERO_CRITICAL_NOTES_STABILITY_SECONDS
        assert kwargs["should_stop"]()
        return object(), {(0, 0, 0): 1}, 2, "FEASIBLE", final_export_info

    monkeypatch.setattr(schedule_real_helper.nurse_scheduling, "schedule", fake_schedule)
    monkeypatch.setattr(schedule_real_helper.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(schedule_real_helper, "EXPECTED_SOLUTION_SIZE", 1)

    schedule_real_helper.run_real_schedule_smoke_test("ortools/cp-sat")

    assert seen["timeout"] is None
    assert seen["prettify"] is True

"""Focused scheduler tests for error/status branches."""

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
from pathlib import Path

import pytest

# Add the project root to the Python path so imports work when running directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nurse_scheduling import scheduler
from nurse_scheduling.solver_interface import SolverStatus

TEST_DIR = Path(__file__).parent / "testcases" / "basics"
VALID_YAML_PATH = TEST_DIR / "01_1nurse_1shift_1day.yaml"


def _load_valid_yaml_bytes() -> bytes:
    return VALID_YAML_PATH.read_bytes()


def test_scheduler_rejects_unsupported_api_version():
    content = _load_valid_yaml_bytes().replace(b"apiVersion: alpha", b"apiVersion: beta")

    with pytest.raises(NotImplementedError, match="Unsupported API version"):
        scheduler.schedule(content)


def test_scheduler_rejects_unsupported_country():
    content = _load_valid_yaml_bytes() + b"\ncountry: US\n"

    with pytest.raises(ValueError, match="Country US is not supported yet"):
        scheduler.schedule(content)


def test_scheduler_rejects_unsupported_solver_selector():
    content = _load_valid_yaml_bytes()

    with pytest.raises(ValueError, match="Unsupported solver configuration"):
        scheduler.schedule(content, solver="invalid/backend")


def test_scheduler_rejects_invalid_avoid_solution_value():
    content = _load_valid_yaml_bytes()
    avoid_solution = {(0, 0, 0): 2}

    with pytest.raises(ValueError, match="Invalid value: 2"):
        scheduler.schedule(content, avoid_solution=avoid_solution)


@pytest.mark.parametrize(
    ("stale_reference_yaml", "expected_message"),
    [
        (b"person: stale_nurse\n    date: 2025-01-01\n    shiftType: D", "Unknown person ID: stale_nurse"),
        (b"person: n1\n    date: 2025-01-02\n    shiftType: D", "out of the range of start date and end date"),
        (b"person: n1\n    date: 2025-01-01\n    shiftType: stale_shift", "Unknown shift type ID: stale_shift"),
    ],
)
def test_scheduler_rejects_stale_preference_references_before_solving(stale_reference_yaml, expected_message):
    content = (
        b"""
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
  - type: shift request
    """
        + stale_reference_yaml
        + b"""
    weight: 1
"""
    )

    with pytest.raises(ValueError, match=expected_message):
        scheduler.schedule(content)


def test_scheduler_feasible_status_and_date_group_member_parsing(monkeypatch):
    content = b"""
apiVersion: alpha
dates:
  range:
    startDate: 2025-01-01
    endDate: 2025-01-02
  groups:
    - id: first_day
      members: ["2025-01-01"]
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
"""

    monkeypatch.setattr(
        "nurse_scheduling.solver_ortools_cp_sat.ORToolsSolver.solve", lambda *args, **kwargs: SolverStatus.FEASIBLE
    )
    monkeypatch.setattr(
        "nurse_scheduling.solver_ortools_cp_sat.ORToolsSolver.get_status_name", lambda *args, **kwargs: "FEASIBLE"
    )
    monkeypatch.setattr(
        "nurse_scheduling.solver_ortools_cp_sat.ORToolsSolver.get_statistics", lambda *args, **kwargs: {}
    )
    monkeypatch.setattr(
        "nurse_scheduling.solver_ortools_cp_sat.ORToolsSolver.get_objective_value", lambda *args, **kwargs: 0
    )

    def fake_get_value(_self, var):
        name = var.Name() if hasattr(var, "Name") else ""
        return 1 if name.startswith("off_") else 0

    monkeypatch.setattr("nurse_scheduling.solver_ortools_cp_sat.ORToolsSolver.get_value", fake_get_value)

    df, solution, score, status_name, _cell_export_info = scheduler.schedule(content)

    assert df is not None
    assert isinstance(solution, dict)
    assert score == 0
    assert status_name == "FEASIBLE"


def test_scheduler_model_build_stats_callback_reports_build_steps(monkeypatch):
    content = _load_valid_yaml_bytes()
    events = []

    monkeypatch.setattr(
        "nurse_scheduling.solver_ortools_cp_sat.ORToolsSolver.solve", lambda *args, **kwargs: SolverStatus.FEASIBLE
    )
    monkeypatch.setattr(
        "nurse_scheduling.solver_ortools_cp_sat.ORToolsSolver.get_status_name", lambda *args, **kwargs: "FEASIBLE"
    )
    monkeypatch.setattr(
        "nurse_scheduling.solver_ortools_cp_sat.ORToolsSolver.get_statistics", lambda *args, **kwargs: {}
    )
    monkeypatch.setattr(
        "nurse_scheduling.solver_ortools_cp_sat.ORToolsSolver.get_objective_value", lambda *args, **kwargs: 0
    )

    def fake_get_value(_self, var):
        name = var.Name() if hasattr(var, "Name") else ""
        return 1 if name.startswith("off_") else 0

    monkeypatch.setattr("nurse_scheduling.solver_ortools_cp_sat.ORToolsSolver.get_value", fake_get_value)

    _df, _solution, _score, status_name, _cell_export_info = scheduler.schedule(
        content,
        model_build_stats_callback=events.append,
    )

    assert status_name == "FEASIBLE"
    assert [event.step for event in events[:3]] == [
        "create_shift_variables",
        "create_off_variables",
        "create_lookup_maps",
    ]
    assert [event.step for event in events[3:]] == ["add_preference", "add_preference"]
    assert [event.preferenceType for event in events[3:]] == [
        "at most one shift per day",
        "shift type requirement",
    ]
    assert events[0].variablesAdded == 1
    assert events[1].variablesAdded == 1
    assert events[1].constraintsAdded == 1
    assert events[3].constraintsAdded == 0
    assert events[-1].totalVariables >= events[-1].variablesAdded
    assert isinstance(events[-1].to_dict(), dict)


def test_scheduler_passes_progress_callback_without_creating_solution_callback(monkeypatch):
    content = _load_valid_yaml_bytes()
    seen = {}

    def fake_solve(_self, timeout=None, deterministic=False, solution_callback=None, progress_callback=None):
        seen["solution_callback"] = solution_callback
        seen["progress_callback"] = progress_callback
        return SolverStatus.FEASIBLE

    monkeypatch.setattr("nurse_scheduling.solver_ortools_cp_sat.ORToolsSolver.solve", fake_solve)
    monkeypatch.setattr(
        "nurse_scheduling.solver_ortools_cp_sat.ORToolsSolver.get_status_name", lambda *args, **kwargs: "FEASIBLE"
    )
    monkeypatch.setattr(
        "nurse_scheduling.solver_ortools_cp_sat.ORToolsSolver.get_statistics", lambda *args, **kwargs: {}
    )
    monkeypatch.setattr(
        "nurse_scheduling.solver_ortools_cp_sat.ORToolsSolver.get_objective_value", lambda *args, **kwargs: 0
    )

    def fake_get_value(_self, var):
        name = var.Name() if hasattr(var, "Name") else ""
        return 1 if name.startswith("off_") else 0

    monkeypatch.setattr("nurse_scheduling.solver_ortools_cp_sat.ORToolsSolver.get_value", fake_get_value)

    scheduler.schedule(content, progress_callback=lambda _payload: None)

    assert seen["solution_callback"] is None
    assert seen["progress_callback"] is not None


def test_scheduler_unknown_status_raises(monkeypatch):
    content = _load_valid_yaml_bytes()

    monkeypatch.setattr("nurse_scheduling.solver_ortools_cp_sat.ORToolsSolver.solve", lambda *args, **kwargs: "MYSTERY")
    monkeypatch.setattr(
        "nurse_scheduling.solver_ortools_cp_sat.ORToolsSolver.get_status_name", lambda *args, **kwargs: "MYSTERY"
    )

    with pytest.raises(ValueError, match="No solution found! Status: MYSTERY"):
        scheduler.schedule(content)


@pytest.mark.parametrize("status", [SolverStatus.INFEASIBLE, SolverStatus.MODEL_INVALID])
def test_scheduler_returns_none_tuple_for_non_solution_status(monkeypatch, status):
    content = _load_valid_yaml_bytes()

    monkeypatch.setattr("nurse_scheduling.solver_ortools_cp_sat.ORToolsSolver.solve", lambda *args, **kwargs: status)
    monkeypatch.setattr(
        "nurse_scheduling.solver_ortools_cp_sat.ORToolsSolver.get_status_name", lambda *args, **kwargs: status.value
    )
    monkeypatch.setattr(
        "nurse_scheduling.solver_ortools_cp_sat.ORToolsSolver.get_statistics",
        lambda *args, **kwargs: {"branches": 0, "conflicts": 0, "wall_time": 0.0},
    )

    df, solution, score, status_name, cell_export_info = scheduler.schedule(content)

    assert df is None
    assert solution is None
    assert score is None
    assert status_name == status.value
    assert cell_export_info is None

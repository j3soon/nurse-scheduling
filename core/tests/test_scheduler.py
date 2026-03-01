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

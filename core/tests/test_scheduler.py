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
import textwrap
from pathlib import Path

import pytest

# Add the project root to the Python path so imports work when running directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nurse_scheduling import scheduler
from nurse_scheduling.solver_interface import SchedulePhaseProgress, SolverProgress, SolverStatus

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


def test_scheduler_rejects_normalized_selector_without_backend(monkeypatch):
    content = _load_valid_yaml_bytes()
    unsupported = scheduler.SolverSelector(
        backend="unsupported",
        api=None,
        engine="unsupported",
        canonical="unsupported",
    )
    monkeypatch.setattr(scheduler, "normalize_solver_selector", lambda _solver: unsupported)

    with pytest.raises(ValueError, match="Unsupported solver configuration"):
        scheduler.schedule(content, solver="unsupported")


@pytest.mark.parametrize(
    ("raw_selector", "canonical", "api", "engine"),
    [
        ("ortools/cp-sat", "ortools/cp-sat", "cp-sat", "cp-sat"),
        ("ortools/mpsolver/cbc", "ortools/mpsolver/cbc", "mpsolver", "cbc"),
        ("ortools/mpsolver/scip", "ortools/mpsolver/scip", "mpsolver", "scip"),
        ("ortools/mpsolver/cp-sat", "ortools/mpsolver/cp-sat", "mpsolver", "cp-sat"),
        ("ortools/mpsolver/bop", "ortools/mpsolver/bop", "mpsolver", "bop"),
        ("ortools/mathopt/gscip", "ortools/mathopt/gscip", "mathopt", "gscip"),
        ("ortools/mathopt/cp-sat", "ortools/mathopt/cp-sat", "mathopt", "cp-sat"),
        ("ortools/mathopt/highs", "ortools/mathopt/highs", "mathopt", "highs"),
        ("pulp/cbc", "pulp/cbc", None, "cbc"),
        ("pulp/cuopt", "pulp/cuopt", None, "cuopt"),
        ("pulp/highs", "pulp/highs", None, "highs"),
        ("pulp/scip", "pulp/scip", None, "scip"),
    ],
)
def test_normalize_solver_selector(raw_selector, canonical, api, engine):
    selector = scheduler.normalize_solver_selector(raw_selector)

    assert selector.canonical == canonical
    assert selector.api == api
    assert selector.engine == engine


@pytest.mark.parametrize(
    "raw_selector",
    [
        "ortools/cbc",
        "ortools/scip",
        "ortools/sat",
        "ortools/bop",
        "ortools/mpsolver/glop",
        "ortools/mathopt/glop",
        "ortools/mathopt/gurobi",
        "ortools/native/cp-sat",
    ],
)
def test_normalize_solver_selector_rejects_unsupported_hierarchies(raw_selector):
    with pytest.raises(ValueError):
        scheduler.normalize_solver_selector(raw_selector)


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


def test_scheduler_shift_type_requirement_nested_group_counts_across_shift_types():
    content = b"""
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
    - id: E
preferences:
  - type: at most one shift per day
  - type: shift type requirement
    shiftType: [[D, E]]
    requiredNumPeople: 1
"""

    df, solution, _score, status_name, _cell_export_info = scheduler.schedule(content)

    assert df is not None
    assert status_name in {"FEASIBLE", "OPTIMAL"}
    assert solution[(0, 0, 0)] + solution[(0, 1, 0)] == 1


def test_scheduler_shift_type_requirement_coefficient_scales_effective_people():
    content = b"""
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
  - type: shift type requirement
    shiftType: D
    shiftTypeCoefficients:
      - [D, 2]
    requiredNumPeople: 2
"""

    df, solution, _score, status_name, _cell_export_info = scheduler.schedule(content)

    assert df is not None
    assert status_name in {"FEASIBLE", "OPTIMAL"}
    assert solution[(0, 0, 0)] == 1


def test_scheduler_shift_type_requirement_coefficient_scales_aggregate_group():
    content = b"""
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
    - id: E
preferences:
  - type: at most one shift per day
  - type: shift type requirement
    shiftType: [[D, E]]
    shiftTypeCoefficients:
      - [D, 2]
    requiredNumPeople: 2
  - type: shift request
    person: n1
    date: 2025-01-01
    shiftType: E
    weight: 100
"""

    df, solution, _score, status_name, _cell_export_info = scheduler.schedule(content)

    assert df is not None
    assert status_name in {"FEASIBLE", "OPTIMAL"}
    assert solution[(0, 0, 0)] == 1
    assert solution[(0, 1, 0)] == 0


def test_scheduler_shift_type_requirement_coefficient_can_reference_selected_group_member():
    content = b"""
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
    - id: E
  groups:
    - id: Work
      members: [D, E]
preferences:
  - type: at most one shift per day
  - type: shift type requirement
    shiftType: Work
    shiftTypeCoefficients:
      - [D, 2]
    requiredNumPeople: 2
  - type: shift request
    person: n1
    date: 2025-01-01
    shiftType: E
    weight: 100
"""

    df, solution, _score, status_name, _cell_export_info = scheduler.schedule(content)

    assert df is not None
    assert status_name in {"FEASIBLE", "OPTIMAL"}
    assert solution[(0, 0, 0)] == 1
    assert solution[(0, 1, 0)] == 0


def test_scheduler_shift_type_requirement_flat_list_keeps_independent_counts():
    content = b"""
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
    - id: E
preferences:
  - type: at most one shift per day
  - type: shift type requirement
    shiftType: [D, E]
    requiredNumPeople: 1
"""

    df, solution, score, status_name, cell_export_info = scheduler.schedule(content)

    assert (df, solution, score, cell_export_info) == (None, None, None, None)
    assert status_name == "INFEASIBLE"


def test_scheduler_shift_type_requirement_nested_group_id_counts_across_members():
    content = b"""
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
    - id: E
  groups:
    - id: DayOrEvening
      members: [D, E]
preferences:
  - type: at most one shift per day
  - type: shift type requirement
    shiftType: [[DayOrEvening]]
    requiredNumPeople: 1
"""

    df, solution, _score, status_name, _cell_export_info = scheduler.schedule(content)

    assert df is not None
    assert status_name in {"FEASIBLE", "OPTIMAL"}
    assert solution[(0, 0, 0)] + solution[(0, 1, 0)] == 1


def test_scheduler_shift_type_requirement_scalar_group_counts_across_members():
    content = b"""
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
    - id: E
  groups:
    - id: DayOrEvening
      members: [D, E]
preferences:
  - type: at most one shift per day
  - type: shift type requirement
    shiftType: DayOrEvening
    requiredNumPeople: 1
"""

    df, solution, _score, status_name, _cell_export_info = scheduler.schedule(content)

    assert df is not None
    assert status_name in {"FEASIBLE", "OPTIMAL"}
    assert solution[(0, 0, 0)] + solution[(0, 1, 0)] == 1


def test_scheduler_shift_type_requirement_flat_group_list_counts_across_members():
    content = b"""
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
    - id: E
  groups:
    - id: DayOrEvening
      members: [D, E]
preferences:
  - type: at most one shift per day
  - type: shift type requirement
    shiftType: [DayOrEvening]
    requiredNumPeople: 1
"""

    df, solution, _score, status_name, _cell_export_info = scheduler.schedule(content)

    assert df is not None
    assert status_name in {"FEASIBLE", "OPTIMAL"}
    assert solution[(0, 0, 0)] + solution[(0, 1, 0)] == 1


def test_scheduler_shift_type_requirement_qualified_people_applies_to_aggregate_group():
    content = b"""
apiVersion: alpha
dates:
  range:
    startDate: 2025-01-01
    endDate: 2025-01-01
people:
  items:
    - id: n1
    - id: n2
shiftTypes:
  items:
    - id: D
    - id: E
preferences:
  - type: at most one shift per day
  - type: shift type requirement
    shiftType: [[D, E]]
    requiredNumPeople: 1
    qualifiedPeople: n1
  - type: shift request
    person: n2
    date: 2025-01-01
    shiftType: [D, E]
    weight: 100
"""

    df, solution, _score, status_name, _cell_export_info = scheduler.schedule(content)

    assert df is not None
    assert status_name in {"FEASIBLE", "OPTIMAL"}
    assert solution[(0, 0, 0)] + solution[(0, 1, 0)] == 1
    assert solution[(0, 0, 1)] == 0
    assert solution[(0, 1, 1)] == 0


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

    def fake_solve(
        _self,
        timeout=None,
        deterministic=False,
        solution_callback=None,
        progress_callback=None,
        should_stop=None,
    ):
        seen["solution_callback"] = solution_callback
        seen["progress_callback"] = progress_callback
        seen["should_stop"] = should_stop
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


def test_scheduler_emits_phase_progress_events():
    events = []

    _df, _solution, score, status_name, _cell_export_info = scheduler.schedule(
        _load_valid_yaml_bytes(),
        progress_callback=events.append,
    )

    assert score == 0
    assert status_name == "OPTIMAL"
    phase_codes = [event.code for event in events if isinstance(event, SchedulePhaseProgress)]
    assert phase_codes == [
        "loading_scenario",
        "parsing_data",
        "initializing_solver",
        "creating_shift_variables",
        "creating_off_variables",
        "creating_lookup_maps",
        "adding_preferences",
        "solving",
        "exporting",
    ]


def test_scheduler_ortools_progress_includes_solution_index():
    events = []

    _df, _solution, _score, status_name, _cell_export_info = scheduler.schedule(
        (TEST_DIR / "01_1nurse_1shift_1day_all_prefs.yaml").read_bytes(),
        progress_callback=events.append,
    )

    assert status_name == "OPTIMAL"
    solver_events = [event for event in events if isinstance(event, SolverProgress)]
    assert solver_events
    assert all(event.source == "ortools/cp-sat:solution-callback" for event in solver_events)
    assert all(event.df is None for event in solver_events)
    assert all(event.cell_export_info is None for event in solver_events)
    assert all(isinstance(event.solutionIndex, int) for event in solver_events)


def test_scheduler_ortools_prettify_progress_includes_export_info():
    events = []
    yaml_content = textwrap.dedent(
        """
        apiVersion: alpha
        dates:
          range:
            startDate: 2023-08-18
            endDate: 2023-08-18
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
          - type: shift request
            person: n1
            date: "2023-08-18"
            shiftType: D
            weight: -10
        export:
          formatting:
            - type: cell
              people: [ALL]
              dates: [ALL]
              shiftTypes: [ALL, OFF]
              when:
                preference:
                  types: ["shift request"]
                  satisfied: false
                  weightRange: [-.inf, .inf]
              note:
                text: "Unsatisfied request: {shiftType}, weight={weight}"
        """
    ).encode()

    _df, _solution, _score, status_name, _cell_export_info = scheduler.schedule(
        yaml_content,
        prettify=True,
        progress_callback=events.append,
    )

    assert status_name == "OPTIMAL"
    solver_events = [event for event in events if isinstance(event, SolverProgress)]
    assert solver_events
    assert all(event.df is not None for event in solver_events)
    assert all(event.cell_export_info is not None for event in solver_events)
    assert all(sum(len(notes) for notes in event.cell_export_info["comments"].values()) == 1 for event in solver_events)


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

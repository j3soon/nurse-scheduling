"""Low-level OR-Tools CP-SAT solver encoding tests for comparison constraints."""

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
import threading

import pytest
from ortools.sat.python import cp_model

# Add the project root to the Python path so imports work when running directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nurse_scheduling.constants import Operator
from nurse_scheduling.solver_interface import SolverStatus
from nurse_scheduling.solver_ortools_cp_sat import ORToolsSolver
from tests.solver_test_utils import expected_bool_value

# This module mirrors the low-level comparator truth-table checks in
# test_solver_pulp_cbc.py, but targets the OR-Tools backend implementation.
# It validates create_bool_var_with_constraint(...) behavior directly,
# independent of the scheduling pipeline.
#
# The main purpose is to catch backend-specific channeling bugs (especially
# off-by-one mistakes in GE/GT/LE/LT complements) using small exhaustive
# truth-table checks over integer domains.


def _solve_with_fixed_x(m: int, M: int, operator: Operator, k: int, x_value: int) -> int:
    # Minimal model:
    # - create y <=> (x <op> k)
    # - pin x to a concrete test value
    # - solve and compare y with the expected Python truth value
    solver = ORToolsSolver()
    x = solver.new_int_var(m, M, "x")
    y = solver.create_bool_var_with_constraint("cmp", x, operator, k, (m, M))
    solver.add_constraint(x == x_value)
    solver.set_objective(0, maximize=True)
    status = solver.solve()
    assert status == SolverStatus.OPTIMAL
    return int(solver.get_value(y))


def _solve_with_fixed_affine(
    x_lb: int,
    x_ub: int,
    operator: Operator,
    k: int,
    x_value: int,
    expr_offset: int,
    provided_range: tuple[int, int],
) -> int:
    # Same as _solve_with_fixed_x, but source_expr is affine (x + offset),
    # so we validate channeling on linear expressions as well as variables.
    solver = ORToolsSolver()
    x = solver.new_int_var(x_lb, x_ub, "x")
    expr = x + expr_offset
    y = solver.create_bool_var_with_constraint("cmp_affine", expr, operator, k, provided_range)
    solver.add_constraint(x == x_value)
    solver.set_objective(0, maximize=True)
    status = solver.solve()
    assert status == SolverStatus.OPTIMAL
    return int(solver.get_value(y))


@pytest.mark.parametrize(
    ("operator", "k"),
    [
        (Operator.EQ, 2),
        (Operator.NE, 2),
        (Operator.GE, 2),
        (Operator.GT, 2),
        (Operator.LE, 2),
        (Operator.LT, 2),
        # Boundary and out-of-range thresholds.
        (Operator.GE, -1),
        (Operator.GE, 5),
        (Operator.GT, -1),
        (Operator.GT, 4),
        (Operator.LE, -1),
        (Operator.LE, 5),
        (Operator.LT, 0),
        (Operator.LT, 5),
    ],
)
def test_create_bool_var_with_constraint_all_ops_truth_table(operator: Operator, k: int):
    """All operators should match Python truth values over a bounded integer domain.

    Includes interior, boundary, and out-of-range thresholds to exercise both
    the true and false branches of the OR-Tools channeling constraints.
    """
    m, M = 0, 4
    for x_value in range(m, M + 1):
        y_value = _solve_with_fixed_x(m, M, operator, k, x_value)
        assert y_value == expected_bool_value(operator, x_value, k)


@pytest.mark.parametrize(
    ("operator", "k"),
    [
        (Operator.EQ, -1),
        (Operator.NE, -1),
        (Operator.GE, -1),
        (Operator.GT, -1),
        (Operator.LE, -1),
        (Operator.LT, -1),
    ],
)
def test_create_bool_var_with_constraint_negative_domain_truth_table(operator: Operator, k: int):
    """Comparisons should work on domains spanning negative values.

    This helps catch sign/threshold mistakes that do not show up on [0, M].
    """
    m, M = -3, 2
    for x_value in range(m, M + 1):
        y_value = _solve_with_fixed_x(m, M, operator, k, x_value)
        assert y_value == expected_bool_value(operator, x_value, k)


def test_create_bool_var_with_constraint_affine_expression_truth_table():
    """Reification should work for bounded affine expressions, not only plain variables.

    Confirms channeling behaves correctly when source_expr is x + c.
    """
    x_lb, x_ub = 0, 4
    expr_offset = 2
    expr_range = (2, 6)
    operator = Operator.LE
    k = 4
    for x_value in range(x_lb, x_ub + 1):
        expr_value = x_value + expr_offset
        y_value = _solve_with_fixed_affine(x_lb, x_ub, operator, k, x_value, expr_offset, expr_range)
        assert y_value == expected_bool_value(operator, expr_value, k)


@pytest.mark.parametrize(
    ("operator", "k", "expected"),
    [
        (Operator.EQ, 3, 1),
        (Operator.EQ, 2, 0),
        (Operator.NE, 3, 0),
        (Operator.GE, 3, 1),
        (Operator.GT, 3, 0),
        (Operator.LE, 3, 1),
        (Operator.LT, 3, 0),
    ],
)
def test_create_bool_var_with_constraint_constant_expression(operator: Operator, k: int, expected: int):
    """Reification should handle constant source expressions.

    Ensures the backend can reify a comparison with no free variable in the
    source expression and still produce the correct fixed boolean.
    """
    solver = ORToolsSolver()
    y = solver.create_bool_var_with_constraint("const_cmp", 3, operator, k, (3, 3))
    solver.set_objective(0, maximize=True)
    status = solver.solve()
    assert status == SolverStatus.OPTIMAL
    assert int(solver.get_value(y)) == expected


def test_set_objective_minimize_branch():
    solver = ORToolsSolver()
    x = solver.new_int_var(0, 1, "x")

    solver.set_objective(x, maximize=False)

    assert solver.maximize is False


@pytest.mark.parametrize(
    ("native_status", "expected"),
    [
        (cp_model.FEASIBLE, SolverStatus.FEASIBLE),
        (cp_model.MODEL_INVALID, SolverStatus.MODEL_INVALID),
        (999, SolverStatus.UNKNOWN),
    ],
)
def test_solve_maps_non_optimal_statuses(monkeypatch, native_status, expected):
    solver = ORToolsSolver()

    class DummyParams:
        pass

    class DummyCpSolver:
        def __init__(self):
            self.parameters = DummyParams()

        def Solve(self, model, callback=None):
            return native_status

    solver.solver = DummyCpSolver()
    status = solver.solve(deterministic=True, timeout=3, solution_callback=object())

    assert status == expected
    assert solver.get_status_name() == expected.value
    assert solver.solver.parameters.random_seed == 0
    assert solver.solver.parameters.num_workers == 1
    assert solver.solver.parameters.max_time_in_seconds == 3.0


def test_solve_timeout_parameter_warning_on_assignment_failure(caplog):
    solver = ORToolsSolver()

    class BadParams:
        def __setattr__(self, name, value):
            if name == "max_time_in_seconds":
                raise AttributeError("unsupported")
            object.__setattr__(self, name, value)

    class DummyCpSolver:
        def __init__(self):
            self.parameters = BadParams()

        def Solve(self, model, callback=None):
            return cp_model.OPTIMAL

    solver.solver = DummyCpSolver()

    with caplog.at_level("WARNING"):
        status = solver.solve(timeout=1)

    assert status == SolverStatus.OPTIMAL
    assert "Unable to set solver timeout parameter" in caplog.text


def test_create_bool_var_with_constraint_rejects_unknown_operator():
    solver = ORToolsSolver()
    x = solver.new_int_var(0, 1, "x")

    with pytest.raises(NotImplementedError, match="not implemented for OR-Tools solver"):
        solver.create_bool_var_with_constraint("cmp", x, "BAD", 0, (0, 1))


@pytest.mark.parametrize(("x_value", "z_value"), [(0, 0), (0, 1), (1, 0), (1, 1)])
def test_create_bool_and_var_matches_truth_table_with_negated_literal(x_value: int, z_value: int):
    solver = ORToolsSolver()
    x = solver.new_bool_var("x")
    z = solver.new_bool_var("z")
    y = solver.create_bool_and_var("and", [x, solver.negate(z)])
    solver.add_constraint(x == x_value)
    solver.add_constraint(z == z_value)
    solver.set_objective(0, maximize=True)

    status = solver.solve()

    assert status == SolverStatus.OPTIMAL
    assert int(solver.get_value(y)) == int(bool(x_value) and not bool(z_value))


def test_create_bool_and_var_empty_literals_is_true():
    solver = ORToolsSolver()
    y = solver.create_bool_and_var("and", [])
    solver.set_objective(0, maximize=True)

    status = solver.solve()

    assert status == SolverStatus.OPTIMAL
    assert int(solver.get_value(y)) == 1


def test_should_use_bool_and_var_for_any_literal_count():
    solver = ORToolsSolver()

    assert solver.should_use_bool_and_var(1)
    assert solver.should_use_bool_and_var(3)
    assert solver.should_use_bool_and_var(10)


def test_solution_callback_logs_progress(caplog):
    solver = ORToolsSolver()
    x = solver.new_int_var(0, 1, "x")
    events = []
    callback = solver.create_solution_callback(x, progress_callback=events.append)

    callback.Value = lambda _var: 7
    callback.start_time = 0.0

    with caplog.at_level("INFO"):
        callback.on_solution_callback()

    assert "# of (best) solutions found: 1" in caplog.text
    assert "current score: 7" in caplog.text
    assert "elapsed time:" in caplog.text
    assert events[0].source == "ortools/cp-sat:solution-callback"
    assert events[0].currentBestScore == 7
    assert events[0].elapsedSeconds >= 0


def test_solve_progress_callback_uses_solution_callback():
    solver = ORToolsSolver()
    x = solver.new_bool_var("x")
    solver.add_constraint(x == 1)
    solver.set_objective(x, maximize=True)
    events = []

    status = solver.solve(progress_callback=events.append)

    assert status == SolverStatus.OPTIMAL
    assert int(solver.get_value(x)) == 1
    assert events
    assert all(event.source == "ortools/cp-sat:solution-callback" for event in events)
    assert events[-1].currentBestScore == 1


def test_solve_allows_solution_callback_and_progress_callback_together():
    solver = ORToolsSolver()
    x = solver.new_bool_var("x")
    solver.add_constraint(x == 1)
    solver.set_objective(x, maximize=True)
    progress_events = []
    solution_events = []

    def count_solution(callback):
        solution_events.append(int(callback.Value(x)))

    status = solver.solve(solution_callback=count_solution, progress_callback=progress_events.append)

    assert status == SolverStatus.OPTIMAL
    assert progress_events
    assert solution_events == [1]
    assert progress_events[-1].currentBestScore == 1


def test_solve_always_registers_internal_solution_callback():
    solver = ORToolsSolver()

    class DummyCpSolver:
        def __init__(self):
            self.callback = None

        def Solve(self, model, callback=None):
            self.callback = callback
            return cp_model.OPTIMAL

    dummy_solver = DummyCpSolver()
    solver.solver = dummy_solver

    status = solver.solve()

    assert status == SolverStatus.OPTIMAL
    assert isinstance(dummy_solver.callback, cp_model.CpSolverSolutionCallback)


def test_solve_should_stop_interrupts_search_between_solution_callbacks():
    solver = ORToolsSolver()
    solver.set_objective(0, maximize=True)

    class BlockingCpSolver:
        def __init__(self):
            self.callback = None
            self.solve_started = threading.Event()
            self.stop_search_called = threading.Event()

        def Solve(self, model, callback=None):
            self.callback = callback
            self.solve_started.set()
            # Simulates CP-SAT spending a long time searching before the next
            # solution callback. A responsive wrapper should interrupt this via
            # StopSearch() after should_stop() becomes true.
            self.stop_search_called.wait(timeout=0.5)
            return cp_model.UNKNOWN

        def StopSearch(self):
            self.stop_search_called.set()

    dummy_solver = BlockingCpSolver()
    solver.solver = dummy_solver
    stop_requested = threading.Event()
    result = {}

    def run_solve():
        result["status"] = solver.solve(should_stop=stop_requested.is_set)

    solve_thread = threading.Thread(target=run_solve)
    solve_thread.start()
    assert dummy_solver.solve_started.wait(timeout=1)

    stop_requested.set()
    solve_thread.join(timeout=1)

    assert not solve_thread.is_alive()
    assert isinstance(dummy_solver.callback, cp_model.CpSolverSolutionCallback)
    assert dummy_solver.stop_search_called.is_set()
    assert result["status"] == SolverStatus.UNKNOWN

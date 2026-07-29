"""Low-level OR-Tools linear solver encoding tests."""

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

import logging
import os
import sys
import threading
from types import SimpleNamespace

import pytest
from ortools.linear_solver import pywraplp

# Add the project root to the Python path so imports work when running directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nurse_scheduling.constants import Operator
from nurse_scheduling.model_build_stats import get_model_entity_counts
from nurse_scheduling.solver_interface import SolverStatus
from nurse_scheduling.solver_ortools_linear import ORTOOLS_MPSOLVER_MIP_ENGINES, ORToolsLinearSolver
from tests.solver_test_utils import expected_bool_value


def _solve_with_fixed_x(m: int, M: int, operator: Operator, k: int, x_value: int) -> int:
    solver = ORToolsLinearSolver(engine="cbc")
    x = solver.new_int_var(m, M, "x")
    y = solver.create_bool_var_with_constraint("cmp", x, operator, k, (m, M))
    solver.add_constraint(x == x_value, name="fix_x")
    solver.set_objective(0, maximize=True)

    status = solver.solve()

    assert status == SolverStatus.OPTIMAL
    return round(solver.get_value(y))


def _solve_with_fixed_affine(
    x_lb: int,
    x_ub: int,
    operator: Operator,
    k: int,
    x_value: int,
    expr_offset: int,
    provided_range: tuple[int, int],
) -> int:
    solver = ORToolsLinearSolver(engine="cbc")
    x = solver.new_int_var(x_lb, x_ub, "x")
    expr = x + expr_offset
    y = solver.create_bool_var_with_constraint("cmp_affine", expr, operator, k, provided_range)
    solver.add_constraint(x == x_value, name="fix_x")
    solver.set_objective(0, maximize=True)

    status = solver.solve()

    assert status == SolverStatus.OPTIMAL
    return round(solver.get_value(y))


@pytest.mark.parametrize("engine", sorted(ORTOOLS_MPSOLVER_MIP_ENGINES))
def test_mip_engines_preserve_integrality(engine: str):
    solver = ORToolsLinearSolver(engine=engine)
    x = solver.new_int_var(0, 1, "x")
    y = solver.new_int_var(0, 1, "y")
    solver.add_constraint(x + y <= 1.5)
    solver.set_objective(x + y, maximize=True)

    status = solver.solve()

    assert status == SolverStatus.OPTIMAL
    assert solver.get_objective_value() == 1
    assert {solver.get_value(x), solver.get_value(y)} <= {0, 1}


@pytest.mark.parametrize(
    ("engine", "supports_interrupt"),
    [("cbc", False), ("scip", True), ("cp-sat", True), ("bop", True)],
)
def test_mip_engine_interrupt_support(engine: str, supports_interrupt: bool):
    solver = ORToolsLinearSolver(engine=engine)

    assert solver.model.InterruptSolve() is supports_interrupt


def test_unsupported_engine_is_rejected():
    with pytest.raises(ValueError, match="Unsupported OR-Tools MPSolver engine"):
        ORToolsLinearSolver(engine="unknown")


def test_unavailable_engine_is_rejected(monkeypatch):
    monkeypatch.setattr(pywraplp.Solver, "CreateSolver", lambda _name: None)

    with pytest.raises(RuntimeError, match="backend is not available"):
        ORToolsLinearSolver(engine="cbc")


def test_numeric_and_bound_normalization_errors():
    assert ORToolsLinearSolver._normalize_numeric_value(None) is None
    assert ORToolsLinearSolver._normalize_numeric_value(1.25) == 1.25

    with pytest.raises(ValueError, match="unbounded variable"):
        ORToolsLinearSolver._finite_int_bound(float("inf"), "x")
    with pytest.raises(ValueError, match="Non-integer bound"):
        ORToolsLinearSolver._finite_int_bound(1.5, "x")


def test_infer_expr_bounds_handles_negative_coefficients_and_invalid_constants():
    solver = ORToolsLinearSolver(engine="cbc")
    x = solver.new_int_var(-1, 4, "x")

    assert solver._infer_expr_bounds(-2 * x + 3) == (-5, 5)
    with pytest.raises(ValueError, match="Non-integer constant"):
        solver._infer_expr_bounds(1.5)


class _BlockingSolveModel:
    def __init__(self, *, accepts_interrupt: bool):
        self.accepts_interrupt = accepts_interrupt
        self.solve_started = threading.Event()
        self.interrupt_called = threading.Event()

    def Solve(self):
        self.solve_started.set()
        assert self.interrupt_called.wait(timeout=2)
        return pywraplp.Solver.NOT_SOLVED

    def InterruptSolve(self):
        self.interrupt_called.set()
        return self.accepts_interrupt


@pytest.mark.parametrize("engine", ["scip", "cp-sat", "bop"])
def test_stop_watcher_interrupts_supported_engine(engine: str):
    solver = ORToolsLinearSolver(engine=engine)
    blocking_model = _BlockingSolveModel(accepts_interrupt=True)
    solver.model = blocking_model

    status = solver.solve(should_stop=blocking_model.solve_started.is_set)

    assert blocking_model.interrupt_called.is_set()
    assert status == SolverStatus.UNKNOWN


def test_stop_watcher_warns_when_cbc_rejects_interrupt(caplog):
    solver = ORToolsLinearSolver(engine="cbc")
    blocking_model = _BlockingSolveModel(accepts_interrupt=False)
    solver.model = blocking_model

    with caplog.at_level(logging.WARNING):
        status = solver.solve(should_stop=blocking_model.solve_started.is_set)

    assert blocking_model.interrupt_called.is_set()
    assert status == SolverStatus.UNKNOWN
    assert "did not accept solve interruption" in caplog.text


def test_stop_watcher_isolates_callback_errors(caplog):
    callback_called = threading.Event()

    class CallbackWaitingModel:
        def Solve(self):
            assert callback_called.wait(timeout=2)
            return pywraplp.Solver.NOT_SOLVED

    def failing_should_stop():
        callback_called.set()
        raise RuntimeError("stop callback boom")

    solver = ORToolsLinearSolver(engine="cbc")
    solver.model = CallbackWaitingModel()

    with caplog.at_level(logging.ERROR):
        status = solver.solve(should_stop=failing_should_stop)

    assert status == SolverStatus.UNKNOWN
    assert "Stop callback failed" in caplog.text


def test_generated_variable_name_skips_existing_suffix():
    solver = ORToolsLinearSolver(engine="cbc")
    first = solver.new_bool_var("duplicate")
    occupied_suffix = solver.new_bool_var("duplicate__1")

    generated = solver.new_bool_var("duplicate")

    assert [first.name(), occupied_suffix.name(), generated.name()] == ["duplicate", "duplicate__1", "duplicate__2"]
    assert len(solver.variables) == solver.model.NumVariables() == 3


@pytest.mark.parametrize("engine", ["glop", "pdlp", "clp"])
def test_lp_only_engines_are_rejected(engine: str):
    with pytest.raises(ValueError, match="LP-only engine"):
        ORToolsLinearSolver(engine=engine)


@pytest.mark.parametrize(
    ("operator", "k"),
    [
        (Operator.EQ, 2),
        (Operator.NE, 2),
        (Operator.GE, 2),
        (Operator.GT, 2),
        (Operator.LE, 2),
        (Operator.LT, 2),
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
    m, M = -3, 2
    for x_value in range(m, M + 1):
        y_value = _solve_with_fixed_x(m, M, operator, k, x_value)
        assert y_value == expected_bool_value(operator, x_value, k)


def test_create_bool_var_with_constraint_affine_expression_truth_table():
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
    solver = ORToolsLinearSolver(engine="cbc")
    y = solver.create_bool_var_with_constraint("const_cmp", 3, operator, k, (3, 3))
    solver.set_objective(0, maximize=True)

    status = solver.solve()

    assert status == SolverStatus.OPTIMAL
    assert round(solver.get_value(y)) == expected


def test_create_bool_var_with_constraint_rejects_invalid_provided_range_order():
    solver = ORToolsLinearSolver(engine="cbc")
    x = solver.new_int_var(0, 4, "x")

    with pytest.raises(ValueError, match="Invalid provided source expression bounds"):
        solver.create_bool_var_with_constraint("bad_range", x, Operator.EQ, 2, (5, 4))


def test_create_bool_var_with_constraint_rejects_range_exceeding_inferred_bounds():
    solver = ORToolsLinearSolver(engine="cbc")
    x = solver.new_int_var(0, 4, "x")

    with pytest.raises(ValueError, match="exceed inferred bounds"):
        solver.create_bool_var_with_constraint("bad_range", x, Operator.EQ, 2, (-1, 5))


@pytest.mark.parametrize(("x_value", "z_value"), [(0, 0), (0, 1), (1, 0), (1, 1)])
def test_create_bool_and_var_matches_truth_table_with_negated_literal(x_value: int, z_value: int):
    solver = ORToolsLinearSolver(engine="cbc")
    x = solver.new_bool_var("x")
    z = solver.new_bool_var("z")
    y = solver.create_bool_and_var("and", [x, solver.negate(z)])
    solver.add_constraint(x == x_value, name="fix_x")
    solver.add_constraint(z == z_value, name="fix_z")
    solver.set_objective(0, maximize=True)

    status = solver.solve()

    assert status == SolverStatus.OPTIMAL
    assert round(solver.get_value(y)) == int(bool(x_value) and not bool(z_value))


def test_create_bool_and_var_empty_literals_is_true():
    solver = ORToolsLinearSolver(engine="cbc")
    y = solver.create_bool_and_var("and", [])
    solver.set_objective(0, maximize=True)

    status = solver.solve()

    assert status == SolverStatus.OPTIMAL
    assert round(solver.get_value(y)) == 1


@pytest.mark.parametrize(
    ("y_value", "expected_status"),
    [(1, SolverStatus.OPTIMAL), (0, SolverStatus.INFEASIBLE)],
)
def test_add_bool_or_requires_at_least_one_true_literal(y_value, expected_status):
    solver = ORToolsLinearSolver(engine="cbc")
    x = solver.new_bool_var("x")
    y = solver.new_bool_var("y")
    solver.add_bool_or([x, y])
    solver.add_constraint(x == 0)
    solver.add_constraint(y == y_value)
    solver.set_objective(0)

    assert solver.solve() == expected_status


def test_should_use_bool_and_var_only_for_compact_literal_counts():
    solver = ORToolsLinearSolver(engine="cbc")

    assert solver.should_use_bool_and_var(1)
    assert solver.should_use_bool_and_var(3)
    assert not solver.should_use_bool_and_var(4)


def test_infer_expr_bounds_rejects_non_integer_coefficient():
    solver = ORToolsLinearSolver(engine="cbc")
    x = solver.new_int_var(0, 3, "x")
    expr = 0.5 * x + 1

    with pytest.raises(ValueError, match="Non-integer coefficient"):
        solver._infer_expr_bounds(expr)


def test_infer_expr_bounds_rejects_unsupported_expression_type():
    solver = ORToolsLinearSolver(engine="cbc")

    with pytest.raises(TypeError, match="Unsupported expression type"):
        solver._infer_expr_bounds("bad-expr")


def test_set_objective_minimize_branch():
    solver = ORToolsLinearSolver(engine="cbc")
    x = solver.new_int_var(0, 2, "x")

    solver.set_objective(x, maximize=False)

    assert solver.maximize is False


def test_validate_model_reports_missing_objective_and_constraints():
    solver = ORToolsLinearSolver(engine="cbc")

    report = solver.validate_model()

    assert "No objective function set" in report
    assert "No constraints defined" in report


def test_validate_model_returns_ok_when_objective_and_constraints_present():
    solver = ORToolsLinearSolver(engine="cbc")
    x = solver.new_int_var(0, 1, "x_valid")
    solver.add_constraint(x >= 0)
    solver.set_objective(x)

    assert solver.validate_model() == "Model appears valid"


def test_solve_emits_final_progress_event():
    solver = ORToolsLinearSolver(engine="cbc")
    x = solver.new_bool_var("x")
    solver.add_constraint(x == 1)
    solver.set_objective(x, maximize=True)
    events = []

    status = solver.solve(progress_callback=events.append)

    assert status == SolverStatus.OPTIMAL
    assert events
    assert events[-1].source == "ortools/mpsolver/cbc:final-result"
    assert events[-1].currentBestScore == 1


def test_solve_isolates_progress_callback_errors(caplog):
    solver = ORToolsLinearSolver(engine="cbc")
    x = solver.new_bool_var("x")
    solver.add_constraint(x == 1)
    solver.set_objective(x)

    def failing_progress_callback(_payload):
        raise RuntimeError("progress callback boom")

    with caplog.at_level(logging.ERROR):
        status = solver.solve(progress_callback=failing_progress_callback)

    assert status == SolverStatus.OPTIMAL
    assert "Progress callback failed" in caplog.text


def test_solve_applies_options_and_isolates_deterministic_configuration_errors(caplog):
    class ConfigurableModel:
        def __init__(self):
            self.time_limit_ms = None

        def SetNumThreads(self, _threads):
            raise RuntimeError("threads unsupported")

        def SetTimeLimit(self, time_limit_ms):
            self.time_limit_ms = time_limit_ms

        def Solve(self):
            return pywraplp.Solver.OPTIMAL

    solver = ORToolsLinearSolver(engine="cbc")
    model = ConfigurableModel()
    solver.model = model

    with caplog.at_level(logging.INFO):
        status = solver.solve(timeout=3, deterministic=True, solution_callback=lambda _value: None)

    assert status == SolverStatus.OPTIMAL
    assert model.time_limit_ms == 3000
    assert "Unable to force single-threaded solving" in caplog.text
    assert "Solution callbacks are not supported" in caplog.text


@pytest.mark.parametrize(
    ("raw_status", "expected_status", "warning"),
    [
        (pywraplp.Solver.FEASIBLE, SolverStatus.FEASIBLE, None),
        (pywraplp.Solver.INFEASIBLE, SolverStatus.INFEASIBLE, None),
        (pywraplp.Solver.MODEL_INVALID, SolverStatus.MODEL_INVALID, None),
        (pywraplp.Solver.UNBOUNDED, SolverStatus.UNKNOWN, "Model is unbounded"),
        (pywraplp.Solver.ABNORMAL, SolverStatus.UNKNOWN, "Solver returned abnormal status"),
    ],
)
def test_solve_maps_backend_statuses(raw_status, expected_status, warning, caplog):
    solver = ORToolsLinearSolver(engine="cbc")
    solver.model = SimpleNamespace(Solve=lambda: raw_status)

    with caplog.at_level(logging.WARNING):
        status = solver.solve()

    assert status == expected_status
    if warning is not None:
        assert warning in caplog.text


def test_value_objective_and_statistics_accessors():
    solver = ORToolsLinearSolver(engine="cbc")

    assert solver.get_value(1.25) == 1.25
    assert solver.get_objective_value() == 0

    x = solver.new_bool_var("x")
    solver.add_constraint(x == 1)
    solver.set_objective(x)
    assert solver.solve() == SolverStatus.OPTIMAL
    assert solver.get_statistics().keys() >= {"iterations", "nodes"}


@pytest.mark.parametrize("objective_value", [None, 1.25])
def test_objective_rejects_missing_or_fractional_values(objective_value):
    solver = ORToolsLinearSolver(engine="cbc")
    solver._has_objective = True
    solver.model = SimpleNamespace(Objective=lambda: SimpleNamespace(Value=lambda: objective_value))

    if objective_value is None:
        assert solver.get_objective_value() == 0
    else:
        with pytest.raises(ValueError, match="should be an integer"):
            solver.get_objective_value()


def test_bop_statistics_omit_unavailable_iteration_and_node_counts():
    solver = ORToolsLinearSolver(engine="bop")
    x = solver.new_bool_var("x")
    solver.add_constraint(x == 1)
    solver.set_objective(x, maximize=True)

    assert solver.solve() == SolverStatus.OPTIMAL

    statistics = solver.get_statistics()
    assert "iterations" not in statistics
    assert "nodes" not in statistics


@pytest.mark.parametrize("source_value", range(-2, 3))
def test_add_abs_equality_matches_truth_table(source_value: int):
    solver = ORToolsLinearSolver(engine="cbc")
    source = solver.new_int_var(-2, 2, "x")
    target = solver.new_int_var(0, 2, "abs_x")
    solver.add_abs_equality(target, source, (-2, 2))
    solver.add_constraint(source == source_value)
    solver.set_objective(target, maximize=True)

    status = solver.solve()

    assert status == SolverStatus.OPTIMAL
    assert solver.get_value(target) == abs(source_value)


def test_add_abs_equality_rejects_invalid_ranges():
    solver = ORToolsLinearSolver(engine="cbc")
    source = solver.new_int_var(-2, 2, "x")
    target = solver.new_int_var(0, 2, "abs_x")

    with pytest.raises(ValueError, match="Invalid source expression bounds"):
        solver.add_abs_equality(target, source, (2, -2))
    with pytest.raises(ValueError, match="exceed inferred bounds"):
        solver.add_abs_equality(target, source, (-3, 3))


def test_add_squared_equality_variable_source():
    solver = ORToolsLinearSolver(engine="cbc")
    source = solver.new_int_var(0, 4, "x")
    target = solver.new_int_var(0, 16, "x_sq")
    solver.add_squared_equality(target, source, (0, 4))
    solver.add_constraint(source == 3)
    solver.set_objective(target, maximize=True)

    status = solver.solve()

    assert status == SolverStatus.OPTIMAL
    assert solver.get_value(target) == 9


def test_add_squared_equality_constant_source():
    solver = ORToolsLinearSolver(engine="cbc")
    target = solver.new_int_var(0, 16, "constant_squared")
    solver.add_squared_equality(target, 3, (0, 4))
    solver.set_objective(target)

    assert solver.solve() == SolverStatus.OPTIMAL
    assert solver.get_value(target) == 9


def test_add_squared_equality_validation_errors():
    solver = ORToolsLinearSolver(engine="cbc")
    target = solver.new_int_var(0, 100, "t")
    bounded = solver.new_int_var(0, 5, "x")
    large = solver.new_int_var(0, 200, "x_large")

    with pytest.raises(NotImplementedError, match="expects a bounded variable or constant"):
        solver.add_squared_equality(target, "bad-source", (0, 1))
    with pytest.raises(ValueError, match="finite integer"):
        solver.add_squared_equality(target, 1.5, (0, 2))
    with pytest.raises(ValueError, match="finite integer"):
        solver.add_squared_equality(target, float("inf"), (0, 2))
    with pytest.raises(ValueError, match="outside declared range"):
        solver.add_squared_equality(target, 6, (0, 5))
    with pytest.raises(ValueError, match="Invalid source variable bounds for square"):
        solver.add_squared_equality(target, bounded, (5, 4))
    with pytest.raises(ValueError, match="Negative lower bound"):
        solver.add_squared_equality(target, bounded, (-1, 5))
    with pytest.raises(ValueError, match="exceed inferred bounds"):
        solver.add_squared_equality(target, bounded, (0, 6))
    with pytest.raises(NotImplementedError, match="Domain too large"):
        solver.add_squared_equality(target, large, (0, 200))


def test_create_bool_var_with_constraint_rejects_unknown_operator():
    solver = ORToolsLinearSolver(engine="cbc")
    x = solver.new_int_var(0, 1, "x_unknown_op")

    with pytest.raises(NotImplementedError, match="not implemented for OR-Tools linear solver"):
        solver.create_bool_var_with_constraint("cmp", x, "BAD", 0, (0, 1))


def test_model_counts_and_unsupported_solution_callback(caplog):
    solver = ORToolsLinearSolver(engine="cbc")
    x = solver.new_bool_var("x")
    solver.add_constraint(x >= 0)
    context = SimpleNamespace(solver=solver, model_vars={})

    assert get_model_entity_counts(context) == (1, 1)
    with caplog.at_level(logging.INFO):
        assert solver.create_solution_callback() is None
    assert "Solution callbacks are not supported" in caplog.text

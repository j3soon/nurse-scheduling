"""Low-level PuLP CBC solver encoding tests for comparison constraints."""

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

import pulp
import pytest

# Add the project root to the Python path so imports work when running directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nurse_scheduling import solver_pulp as solver_pulp_module
from nurse_scheduling.constants import Operator
from nurse_scheduling.solver_interface import SolverStatus
from nurse_scheduling.solver_pulp_cbc import PuLPSolver
from tests.solver_test_utils import expected_bool_value

# This module focuses on low-level PuLP solver encodings, especially
# create_bool_var_with_constraint(...), using tiny synthetic models.
# The goal is to validate:
# - exact truth-table behavior for each comparison operator,
# - edge behavior at domain boundaries (e.g. K == m / K == M),
# - out-of-range targets that should collapse to constants (always true/false),
# - handling of negative domains,
# - handling of affine and constant source expressions,
# - and rejection of invalid caller-provided bounds.
#
# These tests isolate the encoding logic from the scheduling pipeline so
# regressions in reification/channeling are caught quickly and locally.


def _solve_eq_with_fixed_x(m: int, M: int, K: int, x_value: int) -> int:
    # Minimal model for EQ-specific checks:
    # - create y <=> (x == K)
    # - pin x to a concrete value
    # - solve and read back y
    solver = PuLPSolver()
    x = solver.new_int_var(m, M, "x")
    y = solver.create_bool_var_with_constraint("is_k", x, Operator.EQ, K, (m, M))
    solver.add_constraint(x == x_value, name="fix_x")
    solver.set_objective(0, maximize=True)

    status = solver.solve()
    assert status == SolverStatus.OPTIMAL
    return round(solver.get_value(y))


def _solve_with_fixed_x(m: int, M: int, operator: Operator, K: int, x_value: int) -> int:
    # Generic helper for truth-table checks:
    # each test pins x to every value in a small domain and verifies the
    # reified boolean matches the corresponding Python comparison result.
    solver = PuLPSolver()
    x = solver.new_int_var(m, M, "x")
    y = solver.create_bool_var_with_constraint("cmp", x, operator, K, (m, M))
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
    # Same idea as _solve_with_fixed_x, but source_expr is affine (x + offset).
    # This catches regressions where encodings only work for plain variables
    # and fail on LpAffineExpression inputs.
    solver = PuLPSolver()
    x = solver.new_int_var(x_lb, x_ub, "x")
    expr = x + expr_offset
    y = solver.create_bool_var_with_constraint("cmp_affine", expr, operator, k, provided_range)
    solver.add_constraint(x == x_value, name="fix_x")
    solver.set_objective(0, maximize=True)
    status = solver.solve()
    assert status == SolverStatus.OPTIMAL
    return round(solver.get_value(y))


def test_generated_variable_name_skips_existing_suffix():
    solver = PuLPSolver()
    first = solver.new_bool_var("duplicate")
    occupied_suffix = solver.new_bool_var("duplicate__1")

    generated = solver.new_bool_var("duplicate")

    assert [first.name, occupied_suffix.name, generated.name] == ["duplicate", "duplicate__1", "duplicate__2"]
    assert len(solver.variables) == 3


@pytest.mark.parametrize("k", [0, 2, 4])
def test_create_bool_var_with_constraint_eq_matches_truth_table(k: int):
    """EQ reification should match x == k for each x in-domain, including edge K values."""
    m, M = 0, 4
    for x_value in range(m, M + 1):
        y_value = _solve_eq_with_fixed_x(m, M, k, x_value)
        expected = 1 if x_value == k else 0
        assert y_value == expected


@pytest.mark.parametrize("k", [-1, 5])
def test_create_bool_var_with_constraint_eq_out_of_range_is_always_zero(k: int):
    """If K is outside [m, M], EQ is impossible, so the reified variable must be 0."""
    m, M = 0, 4
    for x_value in range(m, M + 1):
        y_value = _solve_eq_with_fixed_x(m, M, k, x_value)
        assert y_value == 0


@pytest.mark.parametrize(
    ("operator", "k"),
    [
        (Operator.EQ, 2),
        (Operator.NE, 2),
        (Operator.GE, 2),
        (Operator.GT, 2),
        (Operator.LE, 2),
        (Operator.LT, 2),
        # Boundary and out-of-range thresholds for inequality operators.
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

    The parameter set includes:
    - an interior threshold (k=2) for all operators,
    - boundary thresholds (e.g. LT with k=0, GT with k=4),
    - and out-of-range thresholds that should simplify to constants.
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

    This specifically exercises sign-sensitive Big-M coefficients and
    threshold handling when m < 0 < M.
    """
    m, M = -3, 2
    for x_value in range(m, M + 1):
        y_value = _solve_with_fixed_x(m, M, operator, k, x_value)
        assert y_value == expected_bool_value(operator, x_value, k)


def test_create_bool_var_with_constraint_affine_expression_truth_table():
    """Reification should work for bounded affine expressions, not only plain variables.

    This ensures the implementation correctly supports source_expr built from
    variables plus constants and respects the caller-provided expression range.
    """
    # expr = x + 2, x in [0, 4] => expr in [2, 6]
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

    This verifies the implementation can short-circuit/fix the boolean value
    without requiring a decision variable source expression.
    """
    solver = PuLPSolver()
    y = solver.create_bool_var_with_constraint("const_cmp", 3, operator, k, (3, 3))
    solver.set_objective(0, maximize=True)
    status = solver.solve()
    assert status == SolverStatus.OPTIMAL
    assert round(solver.get_value(y)) == expected


def test_create_bool_var_with_constraint_rejects_invalid_provided_range_order():
    """Provided bounds must be ordered as (lb, ub).

    A reversed range should fail immediately before any encoding is built.
    """
    solver = PuLPSolver()
    x = solver.new_int_var(0, 4, "x")
    with pytest.raises(ValueError, match="Invalid provided source expression bounds"):
        solver.create_bool_var_with_constraint("bad_range", x, Operator.EQ, 2, (5, 4))


def test_create_bool_var_with_constraint_rejects_range_exceeding_inferred_bounds():
    """Provided bounds wider than inferred bounds should be rejected.

    This guards against incorrect Big-M constants caused by callers passing a
    range that is not a valid bound for the actual source expression.
    """
    solver = PuLPSolver()
    x = solver.new_int_var(0, 4, "x")
    with pytest.raises(ValueError, match="exceed inferred bounds"):
        solver.create_bool_var_with_constraint("bad_range", x, Operator.EQ, 2, (-1, 5))


@pytest.mark.parametrize(("x_value", "z_value"), [(0, 0), (0, 1), (1, 0), (1, 1)])
def test_create_bool_and_var_matches_truth_table_with_negated_literal(x_value: int, z_value: int):
    solver = PuLPSolver()
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
    solver = PuLPSolver()
    y = solver.create_bool_and_var("and", [])
    solver.set_objective(0, maximize=True)

    status = solver.solve()

    assert status == SolverStatus.OPTIMAL
    assert round(solver.get_value(y)) == 1


def test_should_use_bool_and_var_only_for_compact_literal_counts():
    solver = PuLPSolver()

    assert solver.should_use_bool_and_var(1)
    assert solver.should_use_bool_and_var(3)
    assert not solver.should_use_bool_and_var(4)


def test_infer_expr_bounds_rejects_unbounded_variable():
    solver = PuLPSolver()
    unbounded = solver.model.add_variable("x_unbounded", lowBound=0, cat=pulp.LpInteger)

    with pytest.raises(ValueError, match="unbounded variable"):
        solver._infer_expr_bounds(unbounded)


def test_infer_expr_bounds_rejects_non_integer_coefficient():
    solver = PuLPSolver()
    x = solver.new_int_var(0, 3, "x")
    expr = 0.5 * x + 1

    with pytest.raises(ValueError, match="Non-integer coefficient"):
        solver._infer_expr_bounds(expr)


def test_infer_expr_bounds_rejects_unsupported_expression_type():
    solver = PuLPSolver()

    with pytest.raises(TypeError, match="Unsupported expression type"):
        solver._infer_expr_bounds("bad-expr")


def test_set_objective_minimize_sets_model_sense():
    solver = PuLPSolver()
    x = solver.new_int_var(0, 2, "x")

    solver.set_objective(x, maximize=False)

    assert solver.model.sense == pulp.LpMinimize


def test_validate_model_reports_missing_objective_and_constraints():
    solver = PuLPSolver()

    report = solver.validate_model()

    assert "No objective function set" in report
    assert "No constraints defined" in report


@pytest.mark.parametrize(
    ("status_code", "warning_text"),
    [
        (pulp.LpStatusUnbounded, "Model is unbounded"),
        (pulp.LpStatusUndefined, "Solver returned undefined status"),
    ],
)
def test_solve_maps_unbounded_and_undefined_to_unknown(monkeypatch, caplog, status_code, warning_text):
    solver = PuLPSolver()
    seen = {}

    class DummyCmd:
        def __str__(self):
            return "DummyCBC"

    def fake_cbc_cmd(*args, **kwargs):
        seen["kwargs"] = kwargs
        return DummyCmd()

    monkeypatch.setattr(solver_pulp_module.pulp, "PULP_CBC_CMD", fake_cbc_cmd)
    monkeypatch.setattr(solver.model, "solve", lambda _solver: status_code)

    with caplog.at_level("INFO"):
        status = solver.solve(timeout=9, deterministic=True, solution_callback=object())

    assert status == SolverStatus.UNKNOWN
    assert solver.get_status_name() == "UNKNOWN"
    assert seen["kwargs"]["timeLimit"] == 9
    assert "randomS 0" in seen["kwargs"]["options"]
    assert "threads 1" in seen["kwargs"]["options"]
    assert "Solution callbacks are not fully supported with PuLP solver" in caplog.text
    assert warning_text in caplog.text


@pytest.mark.parametrize("status_code", [pulp.LpStatusNotSolved, 123456])
def test_solve_maps_not_solved_and_unknown_status_to_unknown(monkeypatch, status_code):
    solver = PuLPSolver()

    class DummyCmd:
        def __str__(self):
            return "DummyCBC"

    monkeypatch.setattr(solver_pulp_module.pulp, "PULP_CBC_CMD", lambda *a, **k: DummyCmd())
    monkeypatch.setattr(solver.model, "solve", lambda _solver: status_code)

    status = solver.solve()
    assert status == SolverStatus.UNKNOWN


def test_get_objective_value_raises_for_non_integer(monkeypatch):
    solver = PuLPSolver()
    x = solver.new_int_var(0, 1, "x")
    solver.set_objective(x, maximize=True)

    monkeypatch.setattr(solver_pulp_module.pulp, "value", lambda _expr: 1.5)

    with pytest.raises(ValueError, match="Objective value should be an integer"):
        solver.get_objective_value()


def test_feasible_solution_check_rejects_fractional_integer_relaxation():
    solver = PuLPSolver()
    x = solver.new_int_var(-1, 1, "x")
    solver.add_constraint(x >= 0)

    x.varValue = None
    assert not solver._has_feasible_solution()

    x.varValue = 0.5
    assert not solver._has_feasible_solution()

    x.varValue = -1
    assert not solver._has_feasible_solution()

    x.varValue = 1
    assert solver._has_feasible_solution()


def test_feasible_solution_check_allows_unset_zero_coefficient_variables():
    solver = PuLPSolver()
    used = solver.new_bool_var("used")
    unused = solver.new_bool_var("unused")
    solver.add_constraint(used + 0 * unused >= 0)

    used.varValue = 1
    assert unused.varValue is None
    assert solver._has_feasible_solution()


def test_get_objective_value_returns_zero_when_objective_missing():
    solver = PuLPSolver()
    assert solver.get_objective_value() == 0


def test_validate_model_returns_ok_when_objective_and_constraints_present():
    solver = PuLPSolver()
    x = solver.new_int_var(0, 1, "x_valid")
    solver.add_constraint(x >= 0)
    solver.set_objective(x)

    assert solver.validate_model() == "Model appears valid"


def test_add_abs_equality_rejects_invalid_or_excessive_bounds():
    solver = PuLPSolver()
    t = solver.new_int_var(0, 10, "t")
    x = solver.new_int_var(0, 4, "x")

    with pytest.raises(ValueError, match="Invalid source expression bounds for abs"):
        solver.add_abs_equality(t, x, (5, 4))
    with pytest.raises(ValueError, match="exceed inferred bounds"):
        solver.add_abs_equality(t, x, (-1, 4))


def test_add_squared_equality_validation_errors():
    solver = PuLPSolver()
    t = solver.new_int_var(0, 100, "t")
    bounded = solver.new_int_var(0, 5, "x")
    unbounded = solver.model.add_variable("x_unbounded_sq", lowBound=0, cat=pulp.LpInteger)
    large = solver.new_int_var(0, 200, "x_large")

    with pytest.raises(NotImplementedError, match="expects a bounded variable or constant"):
        solver.add_squared_equality(t, "bad-source", (0, 1))
    with pytest.raises(ValueError, match="finite integer"):
        solver.add_squared_equality(t, 1.5, (0, 2))
    with pytest.raises(ValueError, match="outside declared range"):
        solver.add_squared_equality(t, 6, (0, 5))
    with pytest.raises(ValueError, match="Cannot linearize square for unbounded variable"):
        solver.add_squared_equality(t, unbounded, (0, 10))
    with pytest.raises(ValueError, match="Invalid source variable bounds for square"):
        solver.add_squared_equality(t, bounded, (5, 4))
    with pytest.raises(ValueError, match="Negative lower bound"):
        solver.add_squared_equality(t, bounded, (-1, 5))
    with pytest.raises(ValueError, match="exceed inferred bounds"):
        solver.add_squared_equality(t, bounded, (0, 6))
    with pytest.raises(NotImplementedError, match="Domain too large"):
        solver.add_squared_equality(t, large, (0, 200))


def test_add_squared_equality_constant_source_branch():
    solver = PuLPSolver()
    target = solver.new_int_var(0, 100, "square_target")
    solver.add_squared_equality(target, 5, (0, 10))
    solver.set_objective(0)

    status = solver.solve()
    assert status == SolverStatus.OPTIMAL
    assert round(solver.get_value(target)) == 25


def test_infer_expr_bounds_rejects_unbounded_variable_inside_affine():
    solver = PuLPSolver()
    x = solver.model.add_variable("x_affine_unbounded", lowBound=0, cat=pulp.LpInteger)
    expr = x + 1

    with pytest.raises(ValueError, match="unbounded variable in expression"):
        solver._infer_expr_bounds(expr)


def test_create_bool_var_with_constraint_rejects_unknown_operator():
    solver = PuLPSolver()
    x = solver.new_int_var(0, 1, "x_unknown_op")

    with pytest.raises(NotImplementedError, match="not implemented for PuLP solver"):
        solver.create_bool_var_with_constraint("cmp", x, "BAD", 0, (0, 1))

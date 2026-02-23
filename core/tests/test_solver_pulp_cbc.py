import os
import sys

import pytest

# Add the project root to the Python path so imports work when running directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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

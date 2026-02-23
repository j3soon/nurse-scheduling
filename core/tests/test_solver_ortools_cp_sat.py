import os
import sys

import pytest

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

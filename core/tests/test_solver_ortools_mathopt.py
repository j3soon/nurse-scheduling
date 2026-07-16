"""Low-level OR-Tools MathOpt solver adapter tests."""

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

import threading
import time
from types import SimpleNamespace

import pytest
from ortools.math_opt.python import mathopt

from nurse_scheduling.constants import Operator
from nurse_scheduling.model_build_stats import get_model_entity_counts
from nurse_scheduling.solver_interface import SolverStatus
from nurse_scheduling.solver_ortools_mathopt import (
    ORTOOLS_MATHOPT_MIP_ENGINES,
    ORToolsMathOptSolver,
)
from tests.solver_test_utils import expected_bool_value


@pytest.mark.parametrize("engine", sorted(ORTOOLS_MATHOPT_MIP_ENGINES))
def test_mathopt_mip_engines_preserve_integrality(engine: str):
    solver = ORToolsMathOptSolver(engine=engine)
    x = solver.new_int_var(0, 1, "x")
    y = solver.new_int_var(0, 1, "y")
    solver.add_constraint(x + y <= 1.5)
    solver.set_objective(x + y, maximize=True)

    status = solver.solve(deterministic=True)

    assert status == SolverStatus.OPTIMAL
    assert solver.get_objective_value() == 1
    assert {solver.get_value(x), solver.get_value(y)} <= {0, 1}


@pytest.mark.parametrize("engine", ["glop", "pdlp", "osqp", "ecos", "scs"])
def test_mathopt_lp_only_engines_are_rejected(engine: str):
    with pytest.raises(ValueError, match="LP-only engine"):
        ORToolsMathOptSolver(engine=engine)


def test_mathopt_unknown_engine_is_rejected():
    with pytest.raises(ValueError, match="Unsupported OR-Tools MathOpt engine"):
        ORToolsMathOptSolver(engine="unknown")


def test_mathopt_generated_names_are_unique():
    solver = ORToolsMathOptSolver()
    first = solver.new_bool_var("duplicate")
    occupied_suffix = solver.new_bool_var("duplicate__1")

    generated = solver.new_bool_var("duplicate")

    assert [first.name, occupied_suffix.name, generated.name] == ["duplicate", "duplicate__1", "duplicate__2"]
    assert len(solver.variables) == solver.model.get_num_variables() == 3


@pytest.mark.parametrize(
    "operator",
    [Operator.EQ, Operator.NE, Operator.GE, Operator.GT, Operator.LE, Operator.LT],
)
def test_mathopt_reified_comparisons_match_truth_table(operator: Operator):
    for x_value in range(-2, 3):
        solver = ORToolsMathOptSolver()
        x = solver.new_int_var(-2, 2, "x")
        is_match = solver.create_bool_var_with_constraint("cmp", x, operator, 0, (-2, 2))
        solver.add_constraint(x == x_value)
        solver.set_objective(0)

        assert solver.solve() == SolverStatus.OPTIMAL
        assert solver.get_value(is_match) == expected_bool_value(operator, x_value, 0)


def test_mathopt_expression_values_and_bounds():
    solver = ORToolsMathOptSolver()
    x = solver.new_int_var(-2, 3, "x")
    expression = 2 * x + 1
    solver.add_constraint(x == 2)
    solver.set_objective(expression)

    assert solver._infer_expr_bounds(expression) == (-3, 7)
    assert solver.solve() == SolverStatus.OPTIMAL
    assert solver.get_value(expression) == 5


def test_mathopt_expression_bounds_handle_negative_coefficients_and_invalid_types(monkeypatch):
    solver = ORToolsMathOptSolver()
    x = solver.new_int_var(-1, 4, "x")

    assert solver._infer_expr_bounds(-2 * x + 3) == (-5, 5)

    def reject_expression(_expr):
        raise TypeError("bad expression")

    monkeypatch.setattr(
        "nurse_scheduling.solver_ortools_mathopt.mathopt.as_flat_linear_expression",
        reject_expression,
    )
    with pytest.raises(TypeError, match="Unsupported expression type"):
        solver._infer_expr_bounds("bad-expression")


def test_mathopt_abs_and_square_linearizations():
    solver = ORToolsMathOptSolver()
    source = solver.new_int_var(-2, 2, "source")
    absolute = solver.new_int_var(0, 2, "absolute")
    squared_source = solver.new_int_var(0, 4, "squared_source")
    squared = solver.new_int_var(0, 16, "squared")
    solver.add_abs_equality(absolute, source, (-2, 2))
    solver.add_squared_equality(squared, squared_source, (0, 4))
    solver.add_constraint(source == -2)
    solver.add_constraint(squared_source == 3)
    solver.set_objective(absolute + squared)

    assert solver.solve() == SolverStatus.OPTIMAL
    assert solver.get_value(absolute) == 2
    assert solver.get_value(squared) == 9


def test_mathopt_infeasible_status_and_statistics():
    solver = ORToolsMathOptSolver(engine="highs")
    x = solver.new_bool_var("x")
    solver.add_constraint(x == 0)
    solver.add_constraint(x == 1)
    solver.set_objective(x)

    assert solver.solve() == SolverStatus.INFEASIBLE
    assert solver.get_status_name() == "INFEASIBLE"
    assert solver.get_statistics()["status"] == "INFEASIBLE"


def test_mathopt_solve_emits_final_progress_event():
    solver = ORToolsMathOptSolver(engine="cp-sat")
    x = solver.new_bool_var("x")
    solver.add_constraint(x == 1)
    solver.set_objective(x)
    events = []

    assert solver.solve(progress_callback=events.append) == SolverStatus.OPTIMAL
    assert events[-1].source == "ortools/mathopt/cp-sat:final-result"
    assert events[-1].currentBestScore == 1


def test_mathopt_solve_passes_timeout_determinism_and_callback_options(monkeypatch, caplog):
    captured = {}

    def fake_solve(_model, _solver_type, *, params, interrupter):
        captured["params"] = params
        captured["interrupter"] = interrupter
        return SimpleNamespace(termination=SimpleNamespace(reason=mathopt.TerminationReason.OPTIMAL))

    monkeypatch.setattr("nurse_scheduling.solver_ortools_mathopt.mathopt.solve", fake_solve)
    solver = ORToolsMathOptSolver(engine="gscip")

    status = solver.solve(timeout=3, deterministic=True, solution_callback=lambda _value: None)

    assert status == SolverStatus.OPTIMAL
    assert captured["params"].time_limit.total_seconds() == 3
    assert captured["params"].random_seed == 0
    assert captured["params"].threads == 1
    assert captured["interrupter"] is None
    assert "Solution callbacks are not exposed" in caplog.text


def test_mathopt_highs_deterministic_solve_after_default_solve():
    solver = ORToolsMathOptSolver(engine="highs")
    x = solver.new_bool_var("x")
    solver.set_objective(x)
    assert solver.solve() == SolverStatus.OPTIMAL

    second_solver = ORToolsMathOptSolver(engine="highs")
    y = second_solver.new_bool_var("y")
    second_solver.set_objective(y)

    assert second_solver.solve(deterministic=True) == SolverStatus.OPTIMAL


def test_mathopt_model_build_counts():
    solver = ORToolsMathOptSolver()
    x = solver.new_bool_var("x")
    solver.add_constraint(x == 1)

    context = type("Context", (), {"solver": solver, "model_vars": {}})()

    assert get_model_entity_counts(context) == (1, 1)


def test_mathopt_stop_callback_interrupts_solve(monkeypatch):
    reference_solver = ORToolsMathOptSolver(engine="cp-sat")
    reference_var = reference_solver.new_bool_var("reference")
    reference_solver.set_objective(reference_var)
    reference_result = mathopt.solve(reference_solver.model, reference_solver.solver_type)

    solver = ORToolsMathOptSolver(engine="cp-sat")
    x = solver.new_bool_var("x")
    solver.set_objective(x)
    solve_started = threading.Event()

    def blocking_solve(_model, _solver_type, *, params, interrupter):
        del params
        solve_started.set()
        assert interrupter is not None
        deadline = time.monotonic() + 2
        while not interrupter.interrupted and time.monotonic() < deadline:
            time.sleep(0.01)
        assert interrupter.interrupted
        return reference_result

    monkeypatch.setattr("nurse_scheduling.solver_ortools_mathopt.mathopt.solve", blocking_solve)
    result = {}
    solve_thread = threading.Thread(
        target=lambda: result.setdefault("status", solver.solve(should_stop=lambda: solve_started.is_set()))
    )
    solve_thread.start()
    solve_thread.join(timeout=3)

    assert not solve_thread.is_alive()
    assert result["status"] == SolverStatus.OPTIMAL


def test_mathopt_stop_watcher_isolates_callback_errors(monkeypatch, caplog):
    callback_called = threading.Event()

    def fake_solve(_model, _solver_type, *, params, interrupter):
        del params
        assert interrupter is not None
        assert callback_called.wait(timeout=2)
        return SimpleNamespace(termination=SimpleNamespace(reason=mathopt.TerminationReason.NO_SOLUTION_FOUND))

    def failing_should_stop():
        callback_called.set()
        raise RuntimeError("stop callback boom")

    monkeypatch.setattr("nurse_scheduling.solver_ortools_mathopt.mathopt.solve", fake_solve)
    solver = ORToolsMathOptSolver(engine="cp-sat")

    status = solver.solve(should_stop=failing_should_stop)

    assert status == SolverStatus.UNKNOWN
    assert "Stop callback failed" in caplog.text


@pytest.mark.parametrize(
    ("reason", "has_solution", "expected"),
    [
        (mathopt.TerminationReason.FEASIBLE, True, SolverStatus.FEASIBLE),
        (mathopt.TerminationReason.IMPRECISE, True, SolverStatus.FEASIBLE),
        (mathopt.TerminationReason.NO_SOLUTION_FOUND, False, SolverStatus.UNKNOWN),
    ],
)
def test_mathopt_maps_backend_statuses(monkeypatch, reason, has_solution, expected):
    result = SimpleNamespace(
        termination=SimpleNamespace(reason=reason),
        has_primal_feasible_solution=lambda: has_solution,
    )
    monkeypatch.setattr("nurse_scheduling.solver_ortools_mathopt.mathopt.solve", lambda *_args, **_kwargs: result)
    solver = ORToolsMathOptSolver()

    assert solver.solve() == expected


@pytest.mark.parametrize("engine", ["gscip", "highs"])
def test_mathopt_rejects_stop_callback_for_non_interruptible_engines(engine: str):
    solver = ORToolsMathOptSolver(engine=engine)
    x = solver.new_bool_var("x")
    solver.set_objective(x)

    with pytest.raises(ValueError, match="does not support cooperative interruption"):
        solver.solve(should_stop=lambda: False)


def test_mathopt_model_validation():
    solver = ORToolsMathOptSolver()

    assert "No objective function set" in solver.validate_model()
    assert "No constraints defined" in solver.validate_model()

    x = solver.new_bool_var("x")
    solver.add_constraint(x >= 0)
    solver.set_objective(x)

    assert solver.validate_model() == "Model appears valid"


def test_mathopt_unsolved_value_objective_and_statistics_accessors():
    solver = ORToolsMathOptSolver(engine="highs")

    with pytest.raises(ValueError, match="No feasible MathOpt solution"):
        solver.get_value(0)
    assert solver.get_objective_value() == 0
    assert solver.get_statistics() == {
        "status": "NOT_SOLVED",
        "wall_time": 0.0,
        "engine": "highs",
        "solver": "MathOpt/highs",
    }

    solver._has_objective = True
    with pytest.raises(ValueError, match="No feasible MathOpt solution"):
        solver.get_objective_value()


def test_mathopt_rejects_missing_expression_and_fractional_objective_values(monkeypatch):
    result = SimpleNamespace(
        has_primal_feasible_solution=lambda: True,
        variable_values=lambda: {},
        objective_value=lambda: 1.25,
    )
    solver = ORToolsMathOptSolver()
    solver.result = result
    monkeypatch.setattr("nurse_scheduling.solver_ortools_mathopt.mathopt.evaluate_expression", lambda *_args: 0)
    monkeypatch.setattr(solver, "_normalize_numeric_value", lambda _value: None)

    with pytest.raises(ValueError, match="returned no value"):
        solver.get_value(0)

    monkeypatch.setattr(solver, "_normalize_numeric_value", ORToolsMathOptSolver._normalize_numeric_value)
    solver._has_objective = True
    with pytest.raises(ValueError, match="should be an integer"):
        solver.get_objective_value()


def test_mathopt_rejects_invalid_square_constants():
    solver = ORToolsMathOptSolver()
    target = solver.new_int_var(0, 100, "target")

    with pytest.raises(ValueError, match="finite integer"):
        solver.add_squared_equality(target, 1.5, (0, 2))
    with pytest.raises(ValueError, match="outside declared range"):
        solver.add_squared_equality(target, 6, (0, 5))


def test_mathopt_squared_equality_constant_source():
    solver = ORToolsMathOptSolver()
    target = solver.new_int_var(0, 16, "constant_squared")
    solver.add_squared_equality(target, 3, (0, 4))
    solver.set_objective(target)

    assert solver.solve() == SolverStatus.OPTIMAL
    assert solver.get_value(target) == 9


def test_mathopt_squared_equality_variable_validation_errors():
    solver = ORToolsMathOptSolver()
    target = solver.new_int_var(0, 100, "target")
    bounded = solver.new_int_var(0, 5, "bounded")
    large = solver.new_int_var(0, 200, "large")

    with pytest.raises(NotImplementedError, match="bounded variable or constant"):
        solver.add_squared_equality(target, "bad-source", (0, 1))
    with pytest.raises(ValueError, match="Invalid source variable bounds"):
        solver.add_squared_equality(target, bounded, (5, 4))
    with pytest.raises(ValueError, match="Negative lower bound"):
        solver.add_squared_equality(target, bounded, (-1, 5))
    with pytest.raises(ValueError, match="exceed inferred bounds"):
        solver.add_squared_equality(target, bounded, (0, 6))
    with pytest.raises(NotImplementedError, match="Domain too large"):
        solver.add_squared_equality(target, large, (0, 200))


@pytest.mark.parametrize(("constraint", "expected"), [(True, SolverStatus.OPTIMAL), (False, SolverStatus.INFEASIBLE)])
def test_mathopt_constant_boolean_constraints(constraint: bool, expected: SolverStatus):
    solver = ORToolsMathOptSolver()
    solver.add_constraint(constraint)
    solver.set_objective(0)

    assert solver.solve() == expected


def test_mathopt_minimize_and_unsupported_solution_callback():
    solver = ORToolsMathOptSolver()
    x = solver.new_bool_var("x")
    solver.set_objective(x, maximize=False)

    assert solver.maximize is False
    assert solver.create_solution_callback() is None

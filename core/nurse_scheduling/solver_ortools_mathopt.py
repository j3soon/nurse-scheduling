"""OR-Tools MathOpt MIP solver implementation."""

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

import logging
import threading
import time
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from ortools.math_opt.python import mathopt
from ortools.util.python import solve_interrupter

from .solver_interface import SolverInterface, SolverProgress, SolverStatus
from .solver_ortools_linear import ORToolsLinearSolver


ORTOOLS_MATHOPT_MIP_ENGINES: dict[str, mathopt.SolverType] = {
    "gscip": mathopt.SolverType.GSCIP,
    "cp-sat": mathopt.SolverType.CP_SAT,
    "highs": mathopt.SolverType.HIGHS,
}
ORTOOLS_MATHOPT_INTERRUPTIBLE_ENGINES = frozenset({"cp-sat"})
ORTOOLS_MATHOPT_LP_ONLY_ENGINES = frozenset({"glop", "pdlp", "osqp", "ecos", "scs"})


class ORToolsMathOptSolver(ORToolsLinearSolver):
    """MathOpt wrapper reusing the solver-independent OR-Tools linear encodings."""

    def __init__(self, engine: str = "gscip"):
        """Initialize an OR-Tools MathOpt model for a bundled MIP engine."""
        SolverInterface.__init__(self)
        self.engine = engine.lower()
        self.solver_selector = f"ortools/mathopt/{self.engine}"
        if self.engine in ORTOOLS_MATHOPT_LP_ONLY_ENGINES:
            raise ValueError(
                f"OR-Tools MathOpt/{self.engine} is an LP-only engine and cannot preserve integer nurse assignments."
            )
        if self.engine not in ORTOOLS_MATHOPT_MIP_ENGINES:
            raise ValueError(f"Unsupported OR-Tools MathOpt engine: {engine!r}")

        self.solver_type = ORTOOLS_MATHOPT_MIP_ENGINES[self.engine]
        self.model = mathopt.Model(name="nurse_scheduling")
        self.result: mathopt.SolveResult | None = None
        self.status: mathopt.TerminationReason | None = None
        self.solver_status = SolverStatus.UNKNOWN
        self.solve_time = 0.0
        self.variables: dict[str, mathopt.Variable] = {}
        self._constraint_names: set[str] = set()
        self._name_counter = 0
        self._has_objective = False

    def unique_constraint_name(self, base: str) -> str:
        """Return a generated constraint name using the current constraint count."""
        return f"{base}_{self.model.get_num_linear_constraints()}"

    def _infer_expr_bounds(self, expr: Any) -> tuple[int, int]:
        """Infer integer lower/upper bounds for a MathOpt linear expression."""
        try:
            flat_expr = mathopt.as_flat_linear_expression(expr)
        except TypeError as exc:
            raise TypeError(f"Unsupported expression type for bound inference: {type(expr)}") from exc

        offset = self._finite_int_bound(flat_expr.offset, "expression offset")
        lb = offset
        ub = offset
        for var, coeff in flat_expr.terms.items():
            coeff_i = self._finite_int_bound(coeff, f"coefficient for {var.name}")
            var_lb = self._finite_int_bound(var.lower_bound, var.name)
            var_ub = self._finite_int_bound(var.upper_bound, var.name)
            if coeff_i >= 0:
                lb += coeff_i * var_lb
                ub += coeff_i * var_ub
            else:
                lb += coeff_i * var_ub
                ub += coeff_i * var_lb
        return lb, ub

    def new_bool_var(self, name: str) -> mathopt.Variable:
        """Create a new binary variable."""
        unique_name = self._unique_name(name)
        var = self.model.add_binary_variable(name=unique_name)
        self.variables[unique_name] = var
        return var

    def new_int_var(self, lb: int, ub: int, name: str) -> mathopt.Variable:
        """Create a new integer variable."""
        unique_name = self._unique_name(name)
        var = self.model.add_integer_variable(lb=lb, ub=ub, name=unique_name)
        self.variables[unique_name] = var
        return var

    def add_constraint(self, constraint, name: str = None) -> None:
        """Add a linear constraint to the model."""
        if name is None:
            name = self.unique_constraint_name("constraint")
        name = self._unique_name(name)
        if isinstance(constraint, bool):
            # Python evaluates constant comparisons before MathOpt sees them.
            # Preserve the redundant/infeasible constraint explicitly.
            if constraint:
                self.model.add_linear_constraint(expr=0, lb=0, ub=0, name=name)
            else:
                infeasibility_witness = self.new_bool_var(f"{name}_false")
                self.model.add_linear_constraint(infeasibility_witness <= -1, name=name)
        else:
            self.model.add_linear_constraint(constraint, name=name)
        self._constraint_names.add(name)

    def set_objective(self, expression, maximize: bool = True) -> None:
        """Set the objective function."""
        self.objective_expr = expression
        self.maximize = maximize
        self._has_objective = True
        if maximize:
            self.model.maximize(expression)
        else:
            self.model.minimize(expression)

    def solve(
        self,
        timeout: int | None = None,
        deterministic: bool = False,
        solution_callback: Callable[[Any], None] | None = None,
        progress_callback: Callable[[SolverProgress], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> SolverStatus:
        """Solve the model using the selected MathOpt engine."""
        start_time = time.monotonic()
        # Schedule scores are integral, so require proof of a zero objective gap.
        # In particular, HiGHS otherwise uses a relative MIP gap that can accept
        # a visibly worse schedule when objective coefficients are large.
        params = mathopt.SolveParameters(absolute_gap_tolerance=0.0, relative_gap_tolerance=0.0)

        if timeout is not None:
            params.time_limit = timedelta(seconds=timeout)
            logging.info("Solver time limit set to %s seconds", timeout)

        if deterministic:
            logging.info("Configuring deterministic mode for OR-Tools MathOpt/%s", self.engine)
            params.random_seed = 0
            if self.engine == "highs":
                # The MathOpt HiGHS adapter does not support the generic threads
                # parameter, and changing its global thread count after a solve
                # can fail. Disabling parallelism avoids that global-state issue.
                params.highs.string_options["parallel"] = "off"
            else:
                params.threads = 1

        if solution_callback is not None:
            logging.warning("Solution callbacks are not exposed by the OR-Tools MathOpt wrapper")

        if should_stop is not None and self.engine not in ORTOOLS_MATHOPT_INTERRUPTIBLE_ENGINES:
            raise ValueError(f"{self.solver_selector} does not support cooperative interruption")

        interrupter = solve_interrupter.SolveInterrupter() if should_stop is not None else None
        stop_watcher_done = threading.Event()
        stop_watcher = None
        if should_stop is not None:

            def watch_stop_request() -> None:
                while not stop_watcher_done.wait(0.2):
                    try:
                        stop_requested = should_stop()
                    except Exception:
                        logging.exception("Stop callback failed")
                        return
                    if stop_requested:
                        assert interrupter is not None
                        interrupter.interrupt()
                        return

            stop_watcher = threading.Thread(
                target=watch_stop_request,
                name=f"ortools-mathopt-{self.engine}-stop-watcher",
                daemon=True,
            )
            stop_watcher.start()

        try:
            self.result = mathopt.solve(
                self.model,
                self.solver_type,
                params=params,
                interrupter=interrupter,
            )
            self.status = self.result.termination.reason
            self.solve_time = time.monotonic() - start_time
        finally:
            stop_watcher_done.set()
            if stop_watcher is not None:
                stop_watcher.join(timeout=1)

        if self.status == mathopt.TerminationReason.OPTIMAL:
            self.solver_status = SolverStatus.OPTIMAL
        elif self.status == mathopt.TerminationReason.FEASIBLE:
            self.solver_status = SolverStatus.FEASIBLE
        elif self.status == mathopt.TerminationReason.INFEASIBLE:
            self.solver_status = SolverStatus.INFEASIBLE
        elif self.status == mathopt.TerminationReason.IMPRECISE and self.result.has_primal_feasible_solution():
            self.solver_status = SolverStatus.FEASIBLE
        else:
            self.solver_status = SolverStatus.UNKNOWN

        if self.solver_status in {SolverStatus.OPTIMAL, SolverStatus.FEASIBLE}:
            self._emit_progress(
                progress_callback,
                SolverProgress(
                    source=f"{self.solver_selector}:final-result",
                    currentBestScore=self.get_objective_value(),
                    elapsedSeconds=round(self.solve_time, 3),
                ),
            )

        return self.solver_status

    def get_value(self, var: Any) -> int | float:
        """Get the value of a variable or linear expression in the solution."""
        if self.result is None or not self.result.has_primal_feasible_solution():
            raise ValueError("No feasible MathOpt solution is available")
        value = mathopt.evaluate_expression(var, self.result.variable_values())
        normalized = self._normalize_numeric_value(value)
        if normalized is None:
            raise ValueError("MathOpt returned no value for the expression")
        return normalized

    def get_objective_value(self) -> int:
        """Get the integral objective value of the solution."""
        if not self._has_objective:
            return 0
        if self.result is None or not self.result.has_primal_feasible_solution():
            raise ValueError("No feasible MathOpt solution is available")
        value = self._normalize_numeric_value(self.result.objective_value())
        if not isinstance(value, int):
            raise ValueError(f"Objective value should be an integer, but got {value}.")
        return value

    def get_statistics(self) -> dict[str, Any]:
        """Get MathOpt termination and solve statistics."""
        if self.result is None:
            return {
                "status": "NOT_SOLVED",
                "wall_time": self.solve_time,
                "engine": self.engine,
                "solver": f"MathOpt/{self.engine}",
            }
        solve_stats = self.result.solve_stats
        return {
            "status": self.result.termination.reason.name,
            "termination_detail": self.result.termination.detail,
            "wall_time": self.solve_time,
            "solver_time": solve_stats.solve_time.total_seconds(),
            "engine": self.engine,
            "solver": f"MathOpt/{self.engine}",
            "simplex_iterations": solve_stats.simplex_iterations,
            "barrier_iterations": solve_stats.barrier_iterations,
            "first_order_iterations": solve_stats.first_order_iterations,
            "nodes": solve_stats.node_count,
        }

    def validate_model(self) -> str:
        """Perform basic validation before MathOpt's solve-time validation."""
        issues = []
        if not self._has_objective:
            issues.append("No objective function set")
        if self.model.get_num_linear_constraints() == 0:
            issues.append("No constraints defined")
        if issues:
            return "Validation issues:\n" + "\n".join(f"  - {issue}" for issue in issues)
        return "Model appears valid"

    def add_squared_equality(self, target_var: Any, source_var: Any, source_var_range: tuple[int, int]) -> None:
        """Add an exact linearization of target_var = source_var^2."""
        if isinstance(source_var, (int, float)):
            self.add_constraint(
                target_var == int(source_var) * int(source_var),
                name=self.unique_constraint_name("square_const"),
            )
            return
        if not isinstance(source_var, mathopt.Variable):
            raise NotImplementedError(
                f"OR-Tools linear squared equality expects a bounded variable or constant, got {type(source_var)}."
            )

        inferred_lb = self._finite_int_bound(source_var.lower_bound, source_var.name)
        inferred_ub = self._finite_int_bound(source_var.upper_bound, source_var.name)
        lb, ub = source_var_range
        lb = int(lb)
        ub = int(ub)
        if lb > ub:
            raise ValueError(f"Invalid source variable bounds for square: [{lb}, {ub}]")
        if lb < 0:
            raise ValueError(f"Negative lower bound {lb} is not supported for square linearization.")
        if lb < inferred_lb or ub > inferred_ub:
            raise ValueError(
                f"Provided source variable bounds [{lb}, {ub}] exceed inferred bounds [{inferred_lb}, {inferred_ub}] for square."
            )
        domain_size = ub - lb + 1
        if domain_size > 128:
            raise NotImplementedError(
                f"Domain too large for exact square linearization: {domain_size}. Consider tightening variable bounds."
            )

        selectors = [self.new_bool_var(f"square_{source_var.name}_{value}") for value in range(lb, ub + 1)]
        self.add_constraint(sum(selectors) == 1, name=self.unique_constraint_name("square_sel_onehot"))
        self.add_constraint(
            source_var == sum((lb + i) * selectors[i] for i in range(domain_size)),
            name=self.unique_constraint_name("square_sel_bind_x"),
        )
        self.add_constraint(
            target_var == sum(((lb + i) ** 2) * selectors[i] for i in range(domain_size)),
            name=self.unique_constraint_name("square_bind_target"),
        )

    def create_solution_callback(
        self,
        objective_var: Any = None,
        solution_callback: Callable[[Any], None] | None = None,
        progress_callback: Callable[[SolverProgress], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> Any:
        """Return None because this wrapper currently reports only the final result."""
        logging.info("Solution callbacks are not exposed by the OR-Tools MathOpt wrapper")
        return None

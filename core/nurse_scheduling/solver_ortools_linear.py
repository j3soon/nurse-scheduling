"""OR-Tools linear MIP solver implementation."""

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
import math
import threading
import time
from collections.abc import Callable
from typing import Any

from ortools.linear_solver import pywraplp
from ortools.linear_solver.python import linear_solver_natural_api

from .constants import Operator
from .solver_interface import SolverInterface, SolverProgress, SolverStatus


ORTOOLS_MPSOLVER_MIP_ENGINES: dict[str, str] = {
    "cbc": "CBC",
    "scip": "SCIP",
    "cp-sat": "SAT",
    "bop": "BOP",
}
ORTOOLS_MPSOLVER_LP_ONLY_ENGINES = frozenset({"glop", "pdlp", "clp"})


class ORToolsLinearSolver(SolverInterface):
    """OR-Tools MPSolver wrapper for integer linear solver engines."""

    _STATUS_NAMES = {
        pywraplp.Solver.OPTIMAL: "OPTIMAL",
        pywraplp.Solver.FEASIBLE: "FEASIBLE",
        pywraplp.Solver.INFEASIBLE: "INFEASIBLE",
        pywraplp.Solver.UNBOUNDED: "UNBOUNDED",
        pywraplp.Solver.ABNORMAL: "ABNORMAL",
        pywraplp.Solver.MODEL_INVALID: "MODEL_INVALID",
        pywraplp.Solver.NOT_SOLVED: "NOT_SOLVED",
    }

    def __init__(self, engine: str = "cbc"):
        """Initialize an OR-Tools linear MIP solver for a specific engine."""
        super().__init__()
        self.engine = engine.lower()
        self.solver_selector = f"ortools/mpsolver/{self.engine}"
        if self.engine in ORTOOLS_MPSOLVER_LP_ONLY_ENGINES:
            raise ValueError(
                f"OR-Tools MPSolver/{self.engine} is an LP-only engine and cannot preserve integer nurse assignments."
            )
        if self.engine not in ORTOOLS_MPSOLVER_MIP_ENGINES:
            raise ValueError(f"Unsupported OR-Tools MPSolver engine: {engine!r}")

        solver_name = ORTOOLS_MPSOLVER_MIP_ENGINES[self.engine]
        self.model = pywraplp.Solver.CreateSolver(solver_name)
        if self.model is None:
            raise RuntimeError(f"{self.solver_selector} backend is not available in this environment.")

        self.status: int | None = None
        self.solver_status = SolverStatus.UNKNOWN
        self.solve_time = 0.0
        # Track variables for solution retrieval
        self.variables: dict[str, pywraplp.Variable] = {}
        self._constraint_names: set[str] = set()
        self._name_counter = 0
        self._has_objective = False

    @staticmethod
    def _normalize_numeric_value(value: Any, *, integer_tolerance: float = 1e-6) -> int | float | None:
        """Normalize solver numeric output, snapping near-integers back to ints."""
        if value is None:
            return None
        value_f = float(value)
        rounded = round(value_f)
        if abs(value_f - rounded) <= integer_tolerance:
            return int(rounded)
        return value_f

    def _emit_progress(
        self,
        progress_callback: Callable[[SolverProgress], None] | None,
        payload: SolverProgress,
    ) -> None:
        """Call the progress callback without letting callback failures break solving."""
        if progress_callback is None:
            return
        try:
            progress_callback(payload)
        except Exception:
            logging.exception("Progress callback failed")

    @staticmethod
    def _finite_int_bound(value: float, name: str) -> int:
        """Return a finite integer bound from an OR-Tools variable bound."""
        value_f = float(value)
        if not math.isfinite(value_f):
            raise ValueError(f"Cannot infer bounds for unbounded variable: {name}")
        rounded = round(value_f)
        if abs(value_f - rounded) > 1e-9:
            raise ValueError(f"Non-integer bound is not supported for bound inference: {value}")
        return int(rounded)

    def _unique_name(self, base: str) -> str:
        """Return a model-unique name for variables/constraints."""
        if base not in self.variables and base not in self._constraint_names:
            return base
        while True:
            self._name_counter += 1
            candidate = f"{base}__{self._name_counter}"
            if candidate not in self.variables and candidate not in self._constraint_names:
                return candidate

    def unique_constraint_name(self, base: str) -> str:
        """Return a generated constraint name using the current number of model constraints."""
        return f"{base}_{self.model.NumConstraints()}"

    def _infer_expr_bounds(self, expr: Any) -> tuple[int, int]:
        """Infer integer lower/upper bounds for a linear expression."""
        # We require the expression to work on integer domains here.
        if isinstance(expr, (int, float)):
            value_f = float(expr)
            if not value_f.is_integer():
                raise ValueError(f"Non-integer constant is not supported for bound inference: {expr}")
            value = int(value_f)
            return value, value

        if isinstance(expr, pywraplp.Variable):
            return self._finite_int_bound(expr.lb(), expr.name()), self._finite_int_bound(expr.ub(), expr.name())

        if not hasattr(expr, "GetCoeffs"):
            raise TypeError(f"Unsupported expression type for bound inference: {type(expr)}")

        lb = 0
        ub = 0
        for var, coeff in expr.GetCoeffs().items():
            coeff_f = float(coeff)
            if not coeff_f.is_integer():
                raise ValueError(f"Non-integer coefficient is not supported for bound inference: {coeff}")
            coeff_i = int(coeff_f)
            if var is linear_solver_natural_api.OFFSET_KEY:
                lb += coeff_i
                ub += coeff_i
                continue

            var_lb = self._finite_int_bound(var.lb(), var.name())
            var_ub = self._finite_int_bound(var.ub(), var.name())
            if coeff_i >= 0:
                lb += coeff_i * var_lb
                ub += coeff_i * var_ub
            else:
                lb += coeff_i * var_ub
                ub += coeff_i * var_lb
        return lb, ub

    def new_bool_var(self, name: str) -> pywraplp.Variable:
        """Create a new boolean variable."""
        unique_name = self._unique_name(name)
        var = self.model.BoolVar(unique_name)
        self.variables[unique_name] = var
        return var

    def new_int_var(self, lb: int, ub: int, name: str) -> pywraplp.Variable:
        """Create a new integer variable."""
        unique_name = self._unique_name(name)
        var = self.model.IntVar(lb, ub, unique_name)
        self.variables[unique_name] = var
        return var

    def add_constraint(self, constraint, name: str = None) -> None:
        """Add a constraint to the model."""
        if name is None:
            name = self.unique_constraint_name("constraint")
        name = self._unique_name(name)
        self.model.Add(constraint, name)
        self._constraint_names.add(name)

    def add_bool_or(self, literals: list[Any]) -> None:
        """
        Add a boolean OR constraint (at least one literal must be true).

        Convert OR(x1, x2, ..., xn) to sum(x1, x2, ..., xn) >= 1.
        Affine negations are represented as (1 - xi).
        """
        self.add_constraint(sum(literals) >= 1, name=self.unique_constraint_name("bool_or"))

    def create_bool_and_var(self, name: str, literals: list[Any]) -> Any:
        """Create a boolean variable equivalent to the AND of the literals."""
        var = self.new_bool_var(name)
        if not literals:
            self.add_constraint(var == 1, name=self.unique_constraint_name("bool_and_empty"))
            return var
        # Encode both directions of:
        #   var <=> AND(literals)
        #
        # Each upper bound provides:
        #   var <= literal_i
        # so var can be 1 only if every literal is 1.
        #
        # The lower bound provides the reverse direction:
        #   var >= sum(literals) - n + 1
        # Its right-hand side is 1 only when every literal is 1, forcing var
        # to 1 in that case. If any literal is 0, the upper bounds force var
        # to 0. This also works with affine negations such as (1 - off_var).
        for literal in literals:
            self.add_constraint(var <= literal, name=self.unique_constraint_name("bool_and_imp"))
        self.add_constraint(
            var >= sum(literals) - len(literals) + 1,
            name=self.unique_constraint_name("bool_and_reverse"),
        )
        return var

    def should_use_bool_and_var(self, n_literals: int) -> bool:
        """Return True only while the linear AND encoding stays compact."""
        return n_literals <= 3

    def set_objective(self, expression, maximize: bool = True) -> None:
        """Set the objective function."""
        self.objective_expr = expression
        self.maximize = maximize
        self._has_objective = True
        if maximize:
            self.model.Maximize(expression)
        else:
            self.model.Minimize(expression)

    def solve(
        self,
        timeout: int | None = None,
        deterministic: bool = False,
        solution_callback: Callable[[Any], None] | None = None,
        progress_callback: Callable[[SolverProgress], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> SolverStatus:
        """Solve the model using OR-Tools MPSolver."""
        start_time = time.monotonic()

        # Note: MPSolver doesn't have built-in support for deterministic solving across all engines
        if deterministic:
            logging.info("Configuring deterministic mode for OR-Tools/%s where supported", self.engine)
            try:
                self.model.SetNumThreads(1)
            except Exception:
                logging.exception("Unable to force single-threaded solving for OR-Tools/%s", self.engine)

        if timeout is not None:
            self.model.SetTimeLimit(int(timeout * 1000))
            logging.info("Solver time limit set to %s seconds", timeout)

        # Note: MPSolver doesn't support solution callbacks in the same way as CP-SAT
        if solution_callback is not None:
            logging.warning("Solution callbacks are not supported with OR-Tools linear solvers")

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
                        interrupted = self.model.InterruptSolve()
                        if not interrupted:
                            logging.warning("OR-Tools/%s did not accept solve interruption", self.engine)
                        return

            stop_watcher = threading.Thread(
                target=watch_stop_request,
                name=f"ortools-{self.engine}-stop-watcher",
                daemon=True,
            )
            stop_watcher.start()

        # Solve the model.
        try:
            self.status = self.model.Solve()
            self.solve_time = time.monotonic() - start_time
        finally:
            stop_watcher_done.set()
            if stop_watcher is not None:
                stop_watcher.join(timeout=1)

        # Convert OR-Tools status to our enum
        if self.status == pywraplp.Solver.OPTIMAL:
            self.solver_status = SolverStatus.OPTIMAL
        elif self.status == pywraplp.Solver.FEASIBLE:
            self.solver_status = SolverStatus.FEASIBLE
        elif self.status == pywraplp.Solver.INFEASIBLE:
            self.solver_status = SolverStatus.INFEASIBLE
        elif self.status == pywraplp.Solver.MODEL_INVALID:
            self.solver_status = SolverStatus.MODEL_INVALID
        else:
            if self.status == pywraplp.Solver.UNBOUNDED:
                logging.warning("Model is unbounded")
            elif self.status == pywraplp.Solver.ABNORMAL:
                logging.warning("Solver returned abnormal status")
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
        if hasattr(var, "solution_value"):
            return self._normalize_numeric_value(var.solution_value())
        return self._normalize_numeric_value(var)

    def get_objective_value(self) -> int:
        """Get the objective value of the solution."""
        # We use int here to follow OR-Tools' CP-SAT solver behavior, but we could solve with float if needed.
        # However, most of the constraints used here assume integer domains.
        if not self._has_objective:
            return 0
        value = self._normalize_numeric_value(self.model.Objective().Value())
        if value is None:
            return 0
        if not isinstance(value, int):
            # This should not happen
            raise ValueError(f"Objective value should be an integer, but got {value}.")
        return value

    def get_statistics(self) -> dict[str, Any]:
        """Get solver statistics."""
        statistics = {
            "status": self._STATUS_NAMES.get(self.status, f"UNKNOWN_STATUS_{self.status}"),
            "wall_time": self.solve_time,
            "engine": self.engine,
            "solver": self.model.SolverVersion(),
        }
        # BOP reports these statistics as unavailable and emits error-level native logs when queried.
        if self.engine != "bop":
            statistics["iterations"] = self.model.iterations()
            statistics["nodes"] = self.model.nodes()
        return statistics

    def validate_model(self) -> str:
        """Validate the model."""
        # MPSolver doesn't have built-in validation like CP-SAT
        # We can check basic things
        issues = []
        if not self._has_objective:
            issues.append("No objective function set")
        if self.model.NumConstraints() == 0:
            issues.append("No constraints defined")

        if issues:
            return "Validation issues:\n" + "\n".join(f"  - {issue}" for issue in issues)
        return "Model appears valid"

    def negate(self, var: Any) -> Any:
        """Negate a boolean variable using a linear expression."""
        return 1 - var

    def create_bool_var_with_constraint(
        self, name: str, source_expr: Any, operator: Operator, target_value: int, source_expr_range: tuple[int, int]
    ) -> Any:
        """Create a boolean variable with a linear reified comparison encoding."""
        var = self.new_bool_var(name)
        m, M = int(source_expr_range[0]), int(source_expr_range[1])
        if m > M:
            raise ValueError(f"Invalid provided source expression bounds: [{m}, {M}]")
        # Use inferred bounds for sanity check to catch modeling errors.
        inferred_m, inferred_M = self._infer_expr_bounds(source_expr)
        if m < inferred_m or M > inferred_M:
            raise ValueError(
                f"Provided source expression bounds [{m}, {M}] exceed inferred bounds [{inferred_m}, {inferred_M}]"
            )
        K = int(target_value)

        def _fix_bool(value: int, suffix: str) -> Any:
            self.add_constraint(var == value, name=f"bool_var_with_constraint_{name}_{suffix}")
            return var

        if operator == Operator.EQ:
            # Compact exact reification for integer x in [m, M]:
            # (var = 1) <=> (x = K), where x := source_expr and K := target_value.
            #
            # Linearize the constraint with Big-M method.
            # Ref: https://en.wikipedia.org/wiki/Big_M_method
            # We model this with one auxiliary binary side_var and x_minus_k := x - K.
            #
            # Hint: One tip to understand this encoding is to note that
            # the term with m/M is designed to "turn off" the
            # corresponding constraint when being activated. This is
            # achieved by making the equation always satisfied (e.g.,
            # x >= m or x <= M), regardless of the value of x.
            #
            # Part A: (var = 1) => (x = K)
            #   A1: x - K <= (M - K) * (1 - var)
            #   A2: x - K >= (m - K) * (1 - var)
            # When var = 1, A1/A2 force x - K = 0.
            # (when var = 0, A1/A2 have no effect, since m <= x <= M is always satisfied)
            #
            # Part B: (var = 0) => (x <= K - 1 OR x >= K + 1)
            # side_var selects which side to allow:
            #   side_var = 0 enables the left side  (x <= K - 1)
            #   side_var = 1 enables the right side (x >= K + 1)
            # Constraints:
            #   B1: x - K <= -1 + (M - K + 1) * side_var + var
            #   B2: x - K >=  1 - (K - m + 1) * (1 - side_var) - var
            # When var = 0, B1/B2 force x != K for any side_var choice.
            # (when var = 1, B1/B2 have no effect, since x = K is allowed)
            if K < m or K > M:
                return _fix_bool(0, "fixed_zero")

            x_minus_k = source_expr - K
            side_var = self.new_bool_var(f"{name}_eq_side")
            # var = 1 => x == K
            self.add_constraint(
                x_minus_k <= (M - K) * (1 - var),
                name=f"bool_var_with_constraint_{name}_eq_imp_ub",
            )
            self.add_constraint(
                x_minus_k >= (m - K) * (1 - var),
                name=f"bool_var_with_constraint_{name}_eq_imp_lb",
            )
            # var = 0 => x <= K - 1 OR x >= K + 1 (selected by side_var).
            self.add_constraint(
                x_minus_k <= -1 + (M - K + 1) * side_var + var,
                name=f"bool_var_with_constraint_{name}_neq_left",
            )
            self.add_constraint(
                x_minus_k >= 1 - (K - m + 1) * (1 - side_var) - var,
                name=f"bool_var_with_constraint_{name}_neq_right",
            )
            return var

        if operator == Operator.NE:
            # x != K is the complement of x == K.
            eq_var = self.create_bool_var_with_constraint(
                f"{name}_eq_aux",
                source_expr,
                Operator.EQ,
                K,
                (m, M),
            )
            self.add_constraint(
                var + eq_var == 1,
                name=f"bool_var_with_constraint_{name}_ne_bind",
            )
            return var

        if operator in (Operator.GE, Operator.GT):
            # x > K is equivalent to x >= (K + 1) for integer x.
            threshold = K if operator == Operator.GE else K + 1
            if threshold <= m:
                return _fix_bool(1, "fixed_one")
            if threshold > M:
                return _fix_bool(0, "fixed_zero")
            # Part A: var = 1 => x >= threshold
            self.add_constraint(
                source_expr >= threshold - (threshold - m) * (1 - var),
                name=f"bool_var_with_constraint_{name}_ge_imp",
            )
            # Part B: var = 0 => x <= threshold - 1
            self.add_constraint(
                source_expr <= (threshold - 1) + (M - (threshold - 1)) * var,
                name=f"bool_var_with_constraint_{name}_ge_rev",
            )
            return var

        if operator in (Operator.LE, Operator.LT):
            # x < K is equivalent to x <= (K - 1) for integer x.
            threshold = K if operator == Operator.LE else K - 1
            if threshold < m:
                return _fix_bool(0, "fixed_zero")
            if threshold >= M:
                return _fix_bool(1, "fixed_one")
            # Part A: var = 1 => x <= threshold
            self.add_constraint(
                source_expr <= threshold + (M - threshold) * (1 - var),
                name=f"bool_var_with_constraint_{name}_le_imp",
            )
            # Part B: var = 0 => x >= threshold + 1
            self.add_constraint(
                source_expr >= (threshold + 1) - ((threshold + 1) - m) * var,
                name=f"bool_var_with_constraint_{name}_le_rev",
            )
            return var

        raise NotImplementedError(f"Operator {operator} not implemented for OR-Tools linear solver.")

    def add_abs_equality(self, target_var: Any, source_expr, source_expr_range: tuple[int, int]) -> None:
        """
        Add a constraint that target_var = |source_expr|.

        Linearize the absolute value with one binary branch variable and Big-M bounds.
        """
        inferred_lb, inferred_ub = self._infer_expr_bounds(source_expr)
        lb, ub = source_expr_range
        lb = int(lb)
        ub = int(ub)
        if lb > ub:
            raise ValueError(f"Invalid source expression bounds for abs: [{lb}, {ub}]")
        if lb < inferred_lb or ub > inferred_ub:
            raise ValueError(
                f"Provided source expression bounds [{lb}, {ub}] exceed inferred bounds [{inferred_lb}, {inferred_ub}] for abs."
            )
        big_m = max(abs(lb), abs(ub))
        sign_var = self.new_bool_var(self.unique_constraint_name("abs_sign"))
        # Let x := source_expr, t := target_var, and b := sign_var.
        # Goal: t = |x|.
        #
        # Part A: Lower bounds (always active)
        #   A1: t >= x
        #   A2: t >= -x
        # Together these imply t >= |x|.
        #
        # Part B: Upper bounds selected by b using Big-M
        #   B1: t <= x  + 2M * (1 - b)
        #   B2: t <= -x + 2M * b
        # where M := max(|lb|, |ub|) so x in [-M, M].
        #
        # If b = 1:
        #   B1 becomes t <= x
        #   B2 becomes t <= -x + 2M (relaxed)
        # Combined with A1, this forces t = x, which is valid when x >= 0.
        #
        # If b = 0:
        #   B1 becomes t <= x + 2M (relaxed)
        #   B2 becomes t <= -x
        # Combined with A2, this forces t = -x, which is valid when x <= 0.
        #
        # The solver chooses b consistently with x, yielding t = |x|.
        #
        # Hint: The 2M here is due to x might be positive/negative.
        self.add_constraint(target_var >= source_expr, name=self.unique_constraint_name("abs_pos_lb"))
        self.add_constraint(target_var >= -source_expr, name=self.unique_constraint_name("abs_neg_lb"))
        self.add_constraint(
            target_var <= source_expr + 2 * big_m * (1 - sign_var),
            name=self.unique_constraint_name("abs_pos_ub"),
        )
        self.add_constraint(
            target_var <= -source_expr + 2 * big_m * sign_var,
            name=self.unique_constraint_name("abs_neg_ub"),
        )

    def add_squared_equality(self, target_var: Any, source_var: Any, source_var_range: tuple[int, int]) -> None:
        """
        Add a constraint that target_var = source_var^2.

        Use an exact value-enumeration encoding on the bounded integer domain of source_var.
        """
        if isinstance(source_var, (int, float)):
            self.add_constraint(
                target_var == int(source_var) * int(source_var),
                name=self.unique_constraint_name("square_const"),
            )
            return
        if not isinstance(source_var, pywraplp.Variable):
            raise NotImplementedError(
                f"OR-Tools linear squared equality expects a bounded variable or constant, got {type(source_var)}."
            )

        inferred_lb = self._finite_int_bound(source_var.lb(), source_var.name())
        inferred_ub = self._finite_int_bound(source_var.ub(), source_var.name())
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
            # The check here is arbitrary, but in practice it hardly exceeds 32 for our case.
            raise NotImplementedError(
                f"Domain too large for exact square linearization: {domain_size}. Consider tightening variable bounds."
            )

        # Let x := source_var, t := target_var, and b_i be one-hot selectors over x's domain.
        #   sum_i b_i = 1
        #   x = sum_i value_i * b_i
        #   t = sum_i (value_i^2) * b_i
        # Since exactly one selector is active, t = x^2 exactly.
        selectors = [self.new_bool_var(f"square_{source_var.name()}_{value}") for value in range(lb, ub + 1)]
        self.add_constraint(sum(selectors) == 1, name=self.unique_constraint_name("square_sel_onehot"))
        self.add_constraint(
            source_var == sum((lb + i) * selectors[i] for i in range(domain_size)),
            name=self.unique_constraint_name("square_sel_bind_x"),
        )
        self.add_constraint(
            target_var == sum(((lb + i) ** 2) * selectors[i] for i in range(domain_size)),
            name=self.unique_constraint_name("square_bind_target"),
        )

    def get_status_name(self) -> str:
        """Get the generic solver status name."""
        return self.solver_status.value

    def create_solution_callback(
        self,
        objective_var: Any = None,
        solution_callback: Callable[[Any], None] | None = None,
        progress_callback: Callable[[SolverProgress], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> Any:
        """
        Create a solution callback for tracking intermediate solutions.

        Note: MPSolver does not expose solution callbacks through this wrapper.
        This method returns None.
        """
        logging.info("Solution callbacks are not supported by OR-Tools linear solvers")
        return None

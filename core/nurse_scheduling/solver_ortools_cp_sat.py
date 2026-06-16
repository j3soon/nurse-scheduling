"""OR-Tools CP-SAT solver implementation."""

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
from collections.abc import Callable
from _thread import LockType
from typing import Any
from ortools.sat.python import cp_model

from .constants import Operator
from .solver_interface import SolverInterface, SolverProgress, SolverStatus, assert_int_score


class ORToolsSolver(SolverInterface):
    """OR-Tools CP-SAT solver implementation."""

    def __init__(self):
        """Initialize OR-Tools solver."""
        super().__init__()
        self.model = cp_model.CpModel()
        self.solver: cp_model.CpSolver = cp_model.CpSolver()
        self.status = None
        self.solver_status = SolverStatus.UNKNOWN
        self._active_solution_callback = None

    def new_bool_var(self, name: str) -> cp_model.IntVar:
        """Create a new boolean variable."""
        return self.model.NewBoolVar(name)

    def new_int_var(self, lb: int, ub: int, name: str) -> cp_model.IntVar:
        """Create a new integer variable."""
        return self.model.NewIntVar(lb, ub, name)

    def add_constraint(self, constraint) -> None:
        """Add a constraint to the model."""
        self.model.Add(constraint)

    def add_bool_or(self, literals: list[Any]) -> None:
        """Add a boolean OR constraint."""
        self.model.AddBoolOr(literals)

    def create_bool_and_var(self, name: str, literals: list[Any]) -> Any:
        """Create a boolean variable equivalent to the AND of the literals."""
        var = self.new_bool_var(name)
        if not literals:
            self.add_constraint(var == 1)
            return var
        # Encode both directions of:
        #   var <=> AND(literals)
        #
        # The enforced AND below provides:
        #   var => AND(literals)
        #
        # It is not sufficient by itself: when every literal is true, var
        # could still remain false. The OR constraint adds the reverse:
        #   OR(NOT literal_1, ..., NOT literal_n, var)
        # which forces var to true when no literal is false.
        self.model.AddBoolAnd(literals).OnlyEnforceIf(var)
        self.model.AddBoolOr([self.negate(literal) for literal in literals] + [var])
        return var

    def should_use_bool_and_var(self, n_literals: int) -> bool:
        """Return True because OR-Tools has native Boolean AND constraints."""
        return True

    def set_objective(self, expression, maximize: bool = True) -> None:
        """Set the objective function."""
        self.objective_expr = expression
        self.maximize = maximize
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
        """Solve the model using OR-Tools."""
        if deterministic:
            logging.info("Configuring deterministic solver...")
            self.solver.parameters.random_seed = 0
            self.solver.parameters.num_workers = 1
            # Potentially related parameters are:
            # `random_seed`, `num_workers`, and `num_search_workers`
            # Ref: https://github.com/google/or-tools/blob/stable/ortools/sat/sat_parameters.proto
            # ctx.model.add_decision_strategy(list(ctx.shifts.values()), cp_model.CHOOSE_FIRST, cp_model.SELECT_MIN_VALUE)

        if timeout is not None:
            try:
                self.solver.parameters.max_time_in_seconds = float(timeout)
                logging.info(f"Solver time limit set to {timeout} seconds")
            except (ValueError, TypeError, AttributeError) as exc:
                logging.warning(
                    "Unable to set solver timeout parameter (%s); proceeding without time limit",
                    exc,
                )

        should_stop_lock = threading.Lock() if should_stop is not None else None
        internal_solution_callback = self.create_solution_callback(
            self.objective_expr,
            solution_callback=solution_callback,
            progress_callback=progress_callback,
            should_stop=should_stop,
            should_stop_lock=should_stop_lock,
        )
        stop_watcher_done = threading.Event()
        stop_watcher = None

        if should_stop is not None:

            def watch_stop_request():
                while not stop_watcher_done.wait(0.2):
                    try:
                        with should_stop_lock:
                            stop_requested = should_stop()
                    except Exception:
                        logging.exception("Stop callback failed")
                        return
                    if stop_requested:
                        self.solver.StopSearch()
                        return

            stop_watcher = threading.Thread(target=watch_stop_request, name="ortools-stop-watcher", daemon=True)
            stop_watcher.start()

        try:
            self.status = self.solver.Solve(self.model, internal_solution_callback)
        finally:
            stop_watcher_done.set()
            if stop_watcher is not None:
                stop_watcher.join(timeout=1)

        # Convert OR-Tools status to our enum
        if self.status == cp_model.OPTIMAL:
            self.solver_status = SolverStatus.OPTIMAL
        elif self.status == cp_model.FEASIBLE:
            self.solver_status = SolverStatus.FEASIBLE
        elif self.status == cp_model.INFEASIBLE:
            self.solver_status = SolverStatus.INFEASIBLE
        elif self.status == cp_model.MODEL_INVALID:
            self.solver_status = SolverStatus.MODEL_INVALID
        else:
            self.solver_status = SolverStatus.UNKNOWN

        return self.solver_status

    def get_value(self, var: Any) -> int | float:
        """Get the value of a variable in the solution."""
        if self._active_solution_callback is not None:
            # During CP-SAT solution callbacks, incumbent values are exposed
            # through the callback object rather than the final CpSolver.
            return self._active_solution_callback.Value(var)
        return self.solver.Value(var)

    def get_objective_value(self) -> int:
        """Get the objective value of the solution."""
        if self._active_solution_callback is not None:
            # Keep objective reads consistent with get_value() while exporting
            # intermediate incumbent solutions for progress reporting.
            return self._active_solution_callback.Value(self.objective_expr)
        return self.solver.Value(self.objective_expr)

    def get_statistics(self) -> dict[str, Any]:
        """Get solver statistics."""
        return {
            "conflicts": self.solver.NumConflicts(),
            "branches": self.solver.NumBranches(),
            "wall_time": self.solver.WallTime(),
        }

    def validate_model(self) -> str:
        """Validate the model."""
        return self.model.Validate()

    def negate(self, var: Any) -> Any:
        """Negate a boolean variable."""
        return var.Not()

    def create_bool_var_with_constraint(
        self, name: str, source_expr: Any, operator: Operator, target_value: int, source_expr_range: tuple[int, int]
    ) -> Any:
        """Create a boolean variable with a constraint."""
        # Ref: https://stackoverflow.com/a/70571397
        # Ref: https://github.com/google/or-tools/blob/master/ortools/sat/docs/channeling.md
        var = self.model.NewBoolVar(name)
        if operator == Operator.EQ:
            self.model.Add(source_expr == target_value).OnlyEnforceIf(var)
            self.model.Add(source_expr != target_value).OnlyEnforceIf(var.Not())
        elif operator == Operator.NE:
            self.model.Add(source_expr != target_value).OnlyEnforceIf(var)
            self.model.Add(source_expr == target_value).OnlyEnforceIf(var.Not())
        elif operator == Operator.GE:
            self.model.Add(source_expr >= target_value).OnlyEnforceIf(var)
            self.model.Add(source_expr < target_value).OnlyEnforceIf(var.Not())
        elif operator == Operator.GT:
            self.model.Add(source_expr > target_value).OnlyEnforceIf(var)
            self.model.Add(source_expr <= target_value).OnlyEnforceIf(var.Not())
        elif operator == Operator.LE:
            self.model.Add(source_expr <= target_value).OnlyEnforceIf(var)
            self.model.Add(source_expr > target_value).OnlyEnforceIf(var.Not())
        elif operator == Operator.LT:
            self.model.Add(source_expr < target_value).OnlyEnforceIf(var)
            self.model.Add(source_expr >= target_value).OnlyEnforceIf(var.Not())
        else:
            raise NotImplementedError(f"Operator {operator} not implemented for OR-Tools solver.")
        return var

    def add_abs_equality(self, target_var: Any, source_expr, source_expr_range: tuple[int, int]) -> None:
        """Add a constraint that target_var = |source_expr|."""
        self.model.AddAbsEquality(target_var, source_expr)

    def add_squared_equality(self, target_var: Any, source_var: Any, source_var_range: tuple[int, int]) -> None:
        """Add a constraint that target_var = source_var^2."""
        self.model.AddMultiplicationEquality(target_var, [source_var, source_var])

    def get_status_name(self) -> str:
        """Get the generic solver status name."""
        return self.solver_status.value

    def create_solution_callback(
        self,
        objective_var: Any = None,
        solution_callback: Callable[[Any], None] | None = None,
        progress_callback: Callable[[SolverProgress], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
        should_stop_lock: LockType | None = None,
    ) -> Any:
        """Create a solution callback for tracking intermediate solutions."""
        import time

        if should_stop is not None and should_stop_lock is None:
            should_stop_lock = threading.Lock()
        maximize = self.maximize
        solver = self

        class PartialSolutionPrinter(cp_model.CpSolverSolutionCallback):
            """Print intermediate solutions."""

            def __init__(self, objective_var, solution_callback, progress_callback, should_stop, should_stop_lock):
                cp_model.CpSolverSolutionCallback.__init__(self)
                self.n_solutions = 0
                self.best_score = float("-inf") if maximize else float("inf")
                self.start_time = time.monotonic()
                self.objective_var = objective_var
                self.solution_callback = solution_callback
                self.progress_callback = progress_callback
                self.should_stop = should_stop
                self.should_stop_lock = should_stop_lock
                self.solution_index = 0

            def on_solution_callback(self):
                # Make the current incumbent visible through SolverInterface
                # while progress callbacks inspect or export it.
                solver._active_solution_callback = self
                try:
                    self.solution_index += 1
                    if self.objective_var is not None and self.progress_callback is not None:
                        current_score = assert_int_score(
                            self.Value(self.objective_var),
                            label="OR-Tools progress score",
                        )
                        elapsed_time = time.monotonic() - self.start_time
                        self.n_solutions += 1
                        if (maximize and current_score > self.best_score) or (
                            not maximize and current_score < self.best_score
                        ):
                            self.best_score = current_score
                            self.n_solutions = 1
                        logging.info(f"# of (best) solutions found: {self.n_solutions}")
                        logging.info(f"current score: {current_score}")
                        logging.info(f"elapsed time: {elapsed_time:.2f}s")
                        try:
                            self.progress_callback(
                                SolverProgress(
                                    source="ortools/cp-sat:solution-callback",
                                    currentBestScore=current_score,
                                    elapsedSeconds=round(elapsed_time, 3),
                                    solutionIndex=self.solution_index,
                                )
                            )
                        except Exception:
                            logging.exception("Progress callback failed")
                    if self.solution_callback is not None:
                        try:
                            self.solution_callback(self)
                        except Exception:
                            logging.exception("Solution callback failed")
                    if self.should_stop is not None:
                        with self.should_stop_lock:
                            stop_requested = self.should_stop()
                        if stop_requested:
                            self.StopSearch()
                finally:
                    solver._active_solution_callback = None

        return PartialSolutionPrinter(
            objective_var, solution_callback, progress_callback, should_stop, should_stop_lock
        )

"""
This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.

Copyright (C) 2023-2026 Johnson Sun

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

"""OR-Tools CP-SAT solver implementation."""

import logging
from typing import Any, Dict, List, Tuple, Union
from ortools.sat.python import cp_model

from .constants import Operator
from .solver_interface import SolverInterface, SolverStatus


class ORToolsSolver(SolverInterface):
    """OR-Tools CP-SAT solver implementation."""
    
    def __init__(self):
        """Initialize OR-Tools solver."""
        super().__init__()
        self.model = cp_model.CpModel()
        self.solver: cp_model.CpSolver = cp_model.CpSolver()
        self.status = None
        self.solver_status = SolverStatus.UNKNOWN
        
    def new_bool_var(self, name: str) -> cp_model.IntVar:
        """Create a new boolean variable."""
        return self.model.NewBoolVar(name)
    
    def new_int_var(self, lb: int, ub: int, name: str) -> cp_model.IntVar:
        """Create a new integer variable."""
        return self.model.NewIntVar(lb, ub, name)
    
    def add_constraint(self, constraint) -> None:
        """Add a constraint to the model."""
        self.model.Add(constraint)
    
    def add_bool_or(self, literals: List[Any]) -> None:
        """Add a boolean OR constraint."""
        self.model.AddBoolOr(literals)
    
    def set_objective(self, expression, maximize: bool = True) -> None:
        """Set the objective function."""
        self.objective_expr = expression
        self.maximize = maximize
        if maximize:
            self.model.Maximize(expression)
        else:
            self.model.Minimize(expression)
    
    def solve(self, timeout: Union[int, None] = None, deterministic: bool = False,
              solution_callback=None) -> SolverStatus:
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
            except Exception:
                logging.warning("Unable to set solver timeout parameter; proceeding without time limit")
        
        # Solve with or without callback
        if solution_callback is not None:
            self.status = self.solver.Solve(self.model, solution_callback)
        else:
            self.status = self.solver.Solve(self.model)
        
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
    
    def get_value(self, var: Any) -> Union[int, float]:
        """Get the value of a variable in the solution."""
        return self.solver.Value(var)
    
    def get_objective_value(self) -> int:
        """Get the objective value of the solution."""
        return self.solver.Value(self.objective_expr)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get solver statistics."""
        return {
            'conflicts': self.solver.NumConflicts(),
            'branches': self.solver.NumBranches(),
            'wall_time': self.solver.WallTime(),
        }
    
    def validate_model(self) -> str:
        """Validate the model."""
        return self.model.Validate()
    
    def negate(self, var: Any) -> Any:
        """Negate a boolean variable."""
        return var.Not()
    
    def create_bool_var_with_constraint(self, name: str, source_expr: Any, operator: Operator, target_value: int, target_value_range: Tuple[int, int]) -> Any:
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
    
    def add_abs_equality(self, target_var: Any, source_expr, source_expr_range: Tuple[int, int]) -> None:
        """Add a constraint that target_var = |source_expr|."""
        self.model.AddAbsEquality(target_var, source_expr)
    
    def add_squared_equality(self, target_var: Any, source_var: Any, source_var_range: Tuple[int, int]) -> None:
        """Add a constraint that target_var = source_var^2."""
        self.model.AddMultiplicationEquality(target_var, [source_var, source_var])
    
    def get_status_name(self) -> str:
        """Get the generic solver status name."""
        return self.solver_status.value
    
    def create_solution_callback(self, objective_var: Any = None) -> Any:
        """Create a solution callback for tracking intermediate solutions."""
        import time
        
        class PartialSolutionPrinter(cp_model.CpSolverSolutionCallback):
            """Print intermediate solutions."""
            def __init__(self, objective_var):
                cp_model.CpSolverSolutionCallback.__init__(self)
                self.n_solutions = 0
                self.best_score = float("-inf")
                self.start_time = time.time()
                self.objective_var = objective_var

            def on_solution_callback(self):
                current_score = self.Value(self.objective_var)
                elapsed_time = time.time() - self.start_time
                self.n_solutions += 1
                if current_score > self.best_score:
                    self.best_score = current_score
                    self.n_solutions = 1
                logging.info(f"# of (best) solutions found: {self.n_solutions}")
                logging.info(f"current score: {current_score}")
                logging.info(f"elapsed time: {elapsed_time:.2f}s")
        
        return PartialSolutionPrinter(objective_var)

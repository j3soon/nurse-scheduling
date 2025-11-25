"""OR-Tools CP-SAT solver implementation."""

import logging
from typing import Any, Dict, List, Union
from ortools.sat.python import cp_model

from .solver_interface import SolverInterface, SolverStatus


class ORToolsSolver(SolverInterface):
    """OR-Tools CP-SAT solver implementation."""
    
    def __init__(self):
        """Initialize OR-Tools solver."""
        super().__init__()
        self.model = cp_model.CpModel()
        self.solver: cp_model.CpSolver = cp_model.CpSolver()
        self.status = None
        
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
            return SolverStatus.OPTIMAL
        elif self.status == cp_model.FEASIBLE:
            return SolverStatus.FEASIBLE
        elif self.status == cp_model.INFEASIBLE:
            return SolverStatus.INFEASIBLE
        elif self.status == cp_model.MODEL_INVALID:
            return SolverStatus.MODEL_INVALID
        else:
            return SolverStatus.UNKNOWN
    
    def get_value(self, var: Any) -> Union[int, float]:
        """Get the value of a variable in the solution."""
        return self.solver.Value(var)
    
    def get_objective_value(self) -> float:
        """Get the objective value of the solution."""
        if self.objective_expr is not None:
            return self.solver.Value(self.objective_expr)
        return 0.0
    
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
    
    def create_bool_var_from_expression(self, name: str, true_expr, false_expr) -> Any:
        """Create a boolean variable from expressions."""
        # Ref: https://stackoverflow.com/a/70571397
        # Ref: https://github.com/google/or-tools/blob/master/ortools/sat/docs/channeling.md
        var = self.model.NewBoolVar(name)
        self.model.Add(true_expr).OnlyEnforceIf(var)
        self.model.Add(false_expr).OnlyEnforceIf(var.Not())
        return var
    
    def add_abs_equality(self, target_var: Any, source_expr) -> None:
        """Add a constraint that target_var = |source_expr|."""
        self.model.AddAbsEquality(target_var, source_expr)
    
    def add_multiplication_equality(self, target_var: Any, var1: Any, var2: Any) -> None:
        """Add a constraint that target_var = var1 * var2."""
        self.model.AddMultiplicationEquality(target_var, var1, var2)
    
    def get_status_name(self) -> str:
        """Get the status name from OR-Tools."""
        if self.status is not None:
            return self.solver.StatusName(self.status)
        return "UNKNOWN"
    
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

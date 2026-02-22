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

"""PuLP solver implementation."""

import logging
import time
from typing import Any, Dict, List, Tuple, Union
import pulp

from .constants import Operator
from .solver_interface import SolverInterface, SolverStatus


class PuLPSolver(SolverInterface):
    """PuLP solver implementation."""
    
    def __init__(self):
        """Initialize PuLP solver."""
        super().__init__()
        self.model = pulp.LpProblem("NurseScheduling", pulp.LpMaximize)
        self.solver = None
        self.status = None
        self.solver_status = SolverStatus.UNKNOWN
        self.solve_time = 0
        # Track variables for solution retrieval
        self.variables = {}
        self._name_counter = 0

    def _unique_name(self, base: str) -> str:
        """Return a model-unique name for variables/constraints."""
        if base not in self.variables and base not in self.model.constraints:
            return base
        self._name_counter += 1
        # Keep a deterministic suffix fallback for robustness when callers accidentally reuse names.
        return f"{base}__{self._name_counter}"

    def unique_constraint_name(self, base: str) -> str:
        """Return a generated constraint name using the current number of model constraints."""
        return f"{base}_{len(self.model.constraints)}"

    def _infer_expr_bounds(self, expr: Any) -> Tuple[int, int]:
        """Infer integer lower/upper bounds for a linear expression."""
        # We require the expression to work on integer domains here.
        if isinstance(expr, (int, float)):
            val = int(expr)
            return val, val
        if isinstance(expr, pulp.LpVariable):
            if expr.lowBound is None or expr.upBound is None:
                raise ValueError(f"Cannot infer bounds for unbounded variable: {expr.name}")
            return int(expr.lowBound), int(expr.upBound)
        if isinstance(expr, pulp.LpAffineExpression):
            lb = int(expr.constant)
            ub = int(expr.constant)
            for var, coeff in expr.items():
                if var.lowBound is None or var.upBound is None:
                    raise ValueError(f"Cannot infer bounds for unbounded variable in expression: {var.name}")
                coeff_f = float(coeff)
                if not coeff_f.is_integer():
                    raise ValueError(f"Non-integer coefficient is not supported for bound inference: {coeff}")
                var_lb = int(var.lowBound)
                var_ub = int(var.upBound)
                coeff_i = int(coeff_f)
                if coeff_i >= 0:
                    lb += coeff_i * var_lb
                    ub += coeff_i * var_ub
                else:
                    lb += coeff_i * var_ub
                    ub += coeff_i * var_lb
            return lb, ub
        raise TypeError(f"Unsupported expression type for bound inference: {type(expr)}")

    def new_bool_var(self, name: str) -> pulp.LpVariable:
        """Create a new boolean variable."""
        unique_name = self._unique_name(name)
        var = pulp.LpVariable(unique_name, cat=pulp.LpBinary)
        self.variables[unique_name] = var
        return var
    
    def new_int_var(self, lb: int, ub: int, name: str) -> pulp.LpVariable:
        """Create a new integer variable."""
        unique_name = self._unique_name(name)
        var = pulp.LpVariable(unique_name, lowBound=lb, upBound=ub, cat=pulp.LpInteger)
        self.variables[unique_name] = var
        return var
    
    def add_constraint(self, constraint, name: str = None) -> None:
        """Add a constraint to the model."""
        if name is None:
            name = self.unique_constraint_name("constraint")
        name = self._unique_name(name)
        self.model += constraint, name
    
    def add_bool_or(self, literals: List[Any]) -> None:
        """
        Add a boolean OR constraint (at least one literal must be true).
        
        For PuLP, we convert OR(x1, x2, ..., xn) to sum(x1, x2, ..., xn) >= 1
        Handle negations by converting ~xi to (1 - xi)
        """
        expr_sum = 0
        for lit in literals:
            expr_sum += lit
        
        self.add_constraint(expr_sum >= 1, name=self.unique_constraint_name("bool_or"))
    
    def set_objective(self, expression, maximize: bool = True) -> None:
        """Set the objective function."""
        self.objective_expr = expression
        self.maximize = maximize
        
        # Handle plain numeric values (e.g., 0) by converting to PuLP expression
        if isinstance(expression, (int, float)):
            # Create a constant expression using PuLP
            expression = pulp.lpSum([expression])
        
        if maximize:
            self.model.sense = pulp.LpMaximize
            self.model.setObjective(expression)
        else:
            self.model.sense = pulp.LpMinimize
            self.model.setObjective(expression)
    
    def solve(self, timeout: Union[int, None] = None, deterministic: bool = False,
              solution_callback=None) -> SolverStatus:
        """Solve the model using PuLP."""
        start_time = time.time()
        
        # Use CBC solver (default open-source solver for PuLP)
        solver_options = []
        # Note: PuLP doesn't have built-in support for deterministic solving across all solvers
        if deterministic:
            logging.info("Deterministic mode requested (support varies by solver)")
            solver_options.append("randomS 0")  # Set random seed for CBC
            solver_options.append("threads 1")
        
        # Note: PuLP doesn't support solution callbacks in the same way as OR-Tools
        if solution_callback is not None:
            logging.warning("Solution callbacks are not fully supported with PuLP solver")
        
        # Solve the model
        # `msg=1` means verbose solve mode.
        if solver_options:
            self.solver = pulp.PULP_CBC_CMD(timeLimit=timeout, msg=1, options=solver_options)
        else:
            self.solver = pulp.PULP_CBC_CMD(msg=1)
        
        self.status = self.model.solve(self.solver)
        self.solve_time = time.time() - start_time
        
        # Convert PuLP status to our enum
        # Ref: https://www.coin-or.org/PuLP/constants.html
        if self.status == pulp.LpStatusOptimal:
            self.solver_status = SolverStatus.OPTIMAL
        elif self.status == pulp.LpStatusNotSolved:
            self.solver_status = SolverStatus.UNKNOWN
        elif self.status == pulp.LpStatusInfeasible:
            self.solver_status = SolverStatus.INFEASIBLE
        elif self.status == pulp.LpStatusUnbounded:
            logging.warning("Model is unbounded")
            self.solver_status = SolverStatus.UNKNOWN
        elif self.status == pulp.LpStatusUndefined:
            logging.warning("Solver returned undefined status")
            self.solver_status = SolverStatus.UNKNOWN
        else:
            self.solver_status = SolverStatus.UNKNOWN
        
        return self.solver_status

    
    def get_value(self, var: Any) -> Union[int, float]:
        """Get the value of a variable in the solution."""
        if isinstance(var, pulp.LpVariable):
            return pulp.value(var)
        else:
            # It might be an expression
            return pulp.value(var)
    
    def get_objective_value(self) -> int:
        """Get the objective value of the solution."""
        # We use int here to follow ortools' CP-SAT solver behavior, but we could solve with float if needed.
        # However, most of the constraints used here assume integer domains.
        if self.model.objective is not None:
            val = pulp.value(self.model.objective)
            if val is None:
                return 0
            val_f = float(val)
            if not val_f.is_integer():
                # This should not happen
                raise ValueError(f"Objective value should be an integer, but got {val}.")
            return int(round(val_f))
        return 0
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get solver statistics."""
        return {
            'status': pulp.LpStatus[self.status],
            'wall_time': self.solve_time,
            'solver': str(self.solver) if self.solver else 'None',
        }
    
    def validate_model(self) -> str:
        """Validate the model."""
        # PuLP doesn't have built-in validation like OR-Tools
        # We can check basic things
        issues = []
        if self.model.objective is None:
            issues.append("No objective function set")
        if len(self.model.constraints) == 0:
            issues.append("No constraints defined")
        
        if issues:
            return "Validation issues:\n" + "\n".join(f"  - {issue}" for issue in issues)
        return "Model appears valid"
    
    def negate(self, var: Any) -> Any:
        """
        Negate a boolean variable.
        
        For PuLP, negation is represented as linear expression (1 - var).
        """
        if isinstance(var, pulp.LpVariable):
            return 1 - var
        # Also allow affine expressions and numeric values.
        return 1 - var
    
    def create_bool_var_with_constraint(self, name: str, source_expr: Any, operator: Operator, target_value: int, target_value_range: Tuple[int, int]) -> Any:
        """Create a boolean variable with a constraint."""
        var = self.new_bool_var(name)
        m, M = int(target_value_range[0]), int(target_value_range[1])
        if m > M:
            raise ValueError(f"Invalid provided source expression bounds: [{m}, {M}]")
        # Use inferred bounds for sanity check to catch modeling errors.
        inferred_m, inferred_M = self._infer_expr_bounds(source_expr)
        if m < inferred_m or M > inferred_M:
            raise ValueError(
                f"Provided source expression bounds [{m}, {M}] exceed inferred bounds "
                f"[{inferred_m}, {inferred_M}]"
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

        raise NotImplementedError(f"Operator {operator} not implemented for PuLP solver.")
    
    def add_abs_equality(self, target_var: Any, source_expr, source_expr_range: Tuple[int, int]) -> None:
        """
        Add a constraint that target_var = |source_expr|.
        
        For PuLP, we linearize with one binary branch variable and Big-M bounds.
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
    
    def add_squared_equality(self, target_var: Any, source_var: Any, source_var_range: Tuple[int, int]) -> None:
        """
        Add a constraint that target_var = source_var^2.

        For PuLP, we use an exact value-enumeration encoding on the bounded integer domain of source_var.
        """
        if isinstance(source_var, (int, float)):
            self.add_constraint(
                target_var == int(source_var) * int(source_var),
                name=self.unique_constraint_name("square_const"),
            )
            return
        if not isinstance(source_var, pulp.LpVariable):
            raise NotImplementedError(
                f"PuLP squared equality expects a bounded variable or constant, got {type(source_var)}."
            )
        if source_var.lowBound is None or source_var.upBound is None:
            raise ValueError("Cannot linearize square for unbounded variable.")

        inferred_lb, inferred_ub = int(source_var.lowBound), int(source_var.upBound)
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
                f"Domain too large for exact square linearization: {domain_size}. "
                "Consider tightening variable bounds."
            )

        # Let x := source_var, t := target_var, and b_i be one-hot selectors over x's domain.
        #   sum_i b_i = 1
        #   x = sum_i value_i * b_i
        #   t = sum_i (value_i^2) * b_i
        # Since exactly one selector is active, t = x^2 exactly.
        selectors = [self.new_bool_var(f"square_{source_var.name}_{v}") for v in range(lb, ub + 1)]
        self.add_constraint(pulp.lpSum(selectors) == 1, name=self.unique_constraint_name("square_sel_onehot"))
        self.add_constraint(
            source_var == pulp.lpSum((lb + i) * selectors[i] for i in range(domain_size)),
            name=self.unique_constraint_name("square_sel_bind_x"),
        )
        self.add_constraint(
            target_var == pulp.lpSum(((lb + i) ** 2) * selectors[i] for i in range(domain_size)),
            name=self.unique_constraint_name("square_bind_target"),
        )
    
    def get_status_name(self) -> str:
        """Get the generic solver status name."""
        return self.solver_status.value
    
    def create_solution_callback(self, objective_var: Any = None) -> Any:
        """
        Create a solution callback for tracking intermediate solutions.
        
        Note: PuLP does not support solution callbacks in the same way as OR-Tools.
        This method returns None.
        """
        logging.info("Solution callbacks are not supported by PuLP solver")
        return None

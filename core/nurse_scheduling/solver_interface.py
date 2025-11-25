"""
Abstraction layer for constraint programming solvers.

This module provides a unified interface for different constraint programming solvers
(OR-Tools CP-SAT, PuLP, etc.) to enable easy switching between backends.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Union


# TODO: The current interface is based on ortools, can change it to be more general

class SolverStatus(Enum):
    """Enumeration of possible solver statuses."""
    OPTIMAL = "OPTIMAL"
    FEASIBLE = "FEASIBLE"
    INFEASIBLE = "INFEASIBLE"
    MODEL_INVALID = "MODEL_INVALID"
    UNKNOWN = "UNKNOWN"


class SolverInterface(ABC):
    """
    Abstract base class for constraint programming solver interface.
    
    This class defines the common interface that all solver implementations must follow.
    """
    
    def __init__(self):
        """Initialize the solver interface."""
        self.objective_expr = None
        self.maximize = True
        
    @abstractmethod
    def new_bool_var(self, name: str) -> Any:
        """
        Create a new boolean variable.
        
        Args:
            name: The name of the variable.
            
        Returns:
            A solver-specific boolean variable.
        """
        pass
    
    @abstractmethod
    def new_int_var(self, lb: int, ub: int, name: str) -> Any:
        """
        Create a new integer variable.
        
        Args:
            lb: Lower bound.
            ub: Upper bound.
            name: The name of the variable.
            
        Returns:
            A solver-specific integer variable.
        """
        pass
    
    @abstractmethod
    def add_constraint(self, constraint) -> None:
        """
        Add a constraint to the model.
        
        Args:
            constraint: A constraint expression.
        """
        pass
    
    @abstractmethod
    def add_bool_or(self, literals: List[Any]) -> None:
        """
        Add a boolean OR constraint (at least one literal must be true).
        
        Args:
            literals: List of boolean variables or their negations.
        """
        pass
    
    @abstractmethod
    def set_objective(self, expression, maximize: bool = True) -> None:
        """
        Set the objective function.
        
        Args:
            expression: The objective expression to optimize.
            maximize: If True, maximize; if False, minimize.
        """
        pass
    
    @abstractmethod
    def solve(self, timeout: Union[int, None] = None, deterministic: bool = False, 
              solution_callback=None) -> SolverStatus:
        """
        Solve the model.
        
        Args:
            timeout: Maximum time in seconds (None for no limit).
            deterministic: If True, use deterministic solving.
            solution_callback: Optional callback for intermediate solutions.
            
        Returns:
            The solver status.
        """
        pass
    
    @abstractmethod
    def get_value(self, var: Any) -> Union[int, float]:
        """
        Get the value of a variable in the solution.
        
        Args:
            var: The variable to query.
            
        Returns:
            The value of the variable in the solution.
        """
        pass
    
    @abstractmethod
    def get_objective_value(self) -> float:
        """
        Get the objective value of the solution.
        
        Returns:
            The objective value.
        """
        pass
    
    @abstractmethod
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get solver statistics.
        
        Returns:
            A dictionary containing solver statistics.
        """
        pass
    
    @abstractmethod
    def validate_model(self) -> str:
        """
        Validate the model.
        
        Returns:
            Validation information as a string.
        """
        pass
    
    @abstractmethod
    def negate(self, var: Any) -> Any:
        """
        Negate a boolean variable.
        
        Args:
            var: A boolean variable.
            
        Returns:
            The negation of the variable.
        """
        pass
    
    @abstractmethod
    def create_bool_var_from_expression(self, name: str, true_expr, false_expr) -> Any:
        """
        Create a boolean variable that is true when true_expr holds.
        
        Args:
            name: The name of the variable.
            true_expr: Expression that must hold when the variable is true.
            false_expr: Expression that must hold when the variable is false.
            
        Returns:
            A boolean variable.
        """
        pass
    
    @abstractmethod
    def add_abs_equality(self, target_var: Any, source_expr) -> None:
        """
        Add a constraint that target_var = |source_expr|.
        
        Args:
            target_var: The variable that will hold the absolute value.
            source_expr: The expression whose absolute value is computed.
        """
        pass
    
    @abstractmethod
    def add_multiplication_equality(self, target_var: Any, var1: Any, var2: Any) -> None:
        """
        Add a constraint that target_var = var1 * var2.
        
        Args:
            target_var: The variable that will hold the product.
            var1: The first multiplicand.
            var2: The second multiplicand.
        """
        pass
    
    @abstractmethod
    def create_solution_callback(self, objective_var: Any = None) -> Any:
        """
        Create a solution callback for tracking intermediate solutions during solving.
        
        Args:
            objective_var: The objective variable to track (optional, solver-specific).
            
        Returns:
            A solver-specific solution callback object, or None if not supported.
        """
        pass

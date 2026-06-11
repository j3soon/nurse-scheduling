"""Abstraction layer for constraint programming solvers."""

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

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from collections.abc import Callable
from typing import Any

from .constants import Operator


# TODO: The current interface is based on ortools, can change it to be more general


class SolverStatus(Enum):
    """Enumeration of possible solver statuses."""

    OPTIMAL = "OPTIMAL"
    FEASIBLE = "FEASIBLE"
    INFEASIBLE = "INFEASIBLE"
    MODEL_INVALID = "MODEL_INVALID"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class SolverProgress:
    """Normalized solver progress payload."""

    source: str
    currentBestScore: int
    elapsedSeconds: float
    solutionIndex: int | None = None
    df: Any | None = None
    cell_export_info: Any | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return the API payload for this progress update."""
        return serialize_solver_progress(self)


@dataclass(frozen=True)
class SchedulePhaseProgress:
    """Scheduler phase progress payload."""

    source: str
    code: str
    message: str
    elapsedSeconds: float

    def to_dict(self) -> dict[str, Any]:
        """Return the API payload for this progress update."""
        return serialize_schedule_phase_progress(self)


ScheduleProgress = SolverProgress | SchedulePhaseProgress


def count_export_comments(cell_export_info: Any) -> int | None:
    """Count reported export-rule notes from in-memory cell export metadata."""
    if not isinstance(cell_export_info, dict):
        return None
    comments = cell_export_info.get("comments")
    if not isinstance(comments, dict):
        return None
    return sum(len(notes) for notes in comments.values())


def serialize_solver_progress(
    payload: SolverProgress,
    *,
    include_export_summary: bool = False,
) -> dict[str, Any]:
    """Return the wire payload for a solver progress update."""
    progress_payload = {
        "source": payload.source,
        "currentBestScore": payload.currentBestScore,
        "elapsedSeconds": payload.elapsedSeconds,
        "solutionIndex": payload.solutionIndex,
    }
    if include_export_summary:
        progress_payload["commentCount"] = count_export_comments(payload.cell_export_info)
    return progress_payload


def serialize_schedule_phase_progress(payload: SchedulePhaseProgress) -> dict[str, Any]:
    """Return the wire payload for a scheduler phase progress update."""
    return {
        "source": payload.source,
        "code": payload.code,
        "message": payload.message,
        "elapsedSeconds": payload.elapsedSeconds,
    }


def assert_int_score(value: Any, *, label: str = "score", integer_tolerance: float = 1e-6) -> int:
    """Assert a solver score is integral and return it as an int."""
    value_f = float(value)
    rounded = round(value_f)
    assert abs(value_f - rounded) <= integer_tolerance, f"{label} should be an integer, but got {value}."
    return int(rounded)


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
    def add_bool_or(self, literals: list[Any]) -> None:
        """
        Add a boolean OR constraint (at least one literal must be true).

        Args:
            literals: List of boolean variables or their negations.
        """
        pass

    @abstractmethod
    def create_bool_and_var(self, name: str, literals: list[Any]) -> Any:
        """
        Create a boolean variable equivalent to the AND of the literals.

        Args:
            name: Variable name.
            literals: List of boolean variables or their negations.

        Returns:
            A solver-specific boolean variable.
        """
        pass

    @abstractmethod
    def should_use_bool_and_var(self, n_literals: int) -> bool:
        """
        Return True when create_bool_and_var is preferred for a literal-only AND of this size.

        This lets model-building code avoid backend-specific checks while still
        accounting for native Boolean backends versus linear encodings.
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
    def solve(
        self,
        timeout: int | None = None,
        deterministic: bool = False,
        solution_callback: Callable[[Any], None] | None = None,
        progress_callback: Callable[[SolverProgress], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> SolverStatus:
        """
        Solve the model.

        Args:
            timeout: Maximum time in seconds (None for no limit).
            deterministic: If True, use deterministic solving.
            solution_callback: Optional app-level callback receiving the registered
                solver-specific callback for each intermediate solution.
            progress_callback: Optional callback for normalized solver progress events.
            should_stop: Optional callback returning True when solving should stop early.

        Returns:
            The solver status.
        """
        pass

    @abstractmethod
    def get_status_name(self) -> str:
        """Get the generic solver status name."""
        pass

    @abstractmethod
    def get_value(self, var: Any) -> int | float:
        """
        Get the value of a variable in the solution.

        Args:
            var: The variable to query.

        Returns:
            The value of the variable in the solution.
        """
        pass

    @abstractmethod
    def get_objective_value(self) -> int:
        """
        Get the objective value of the solution.

        Returns:
            The objective value as an integer.
        """
        pass

    @abstractmethod
    def get_statistics(self) -> dict[str, Any]:
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
    def create_bool_var_with_constraint(
        self, name: str, source_expr: Any, operator: Operator, target_value: int, source_expr_range: tuple[int, int]
    ) -> Any:
        """
        Create a boolean variable that reifies a bounded integer comparison.

        The returned variable is 1 iff:
            source_expr <operator> target_value

        Args:
            name: Variable name.
            source_expr: Integer-valued source expression.
            operator: Comparison operator.
            target_value: Right-hand-side comparison value.
            source_expr_range: Lower/upper bound of source_expr.
        """
        pass

    @abstractmethod
    def add_abs_equality(self, target_var: Any, source_expr, source_expr_range: tuple[int, int]) -> None:
        """
        Add a constraint that target_var = |source_expr|.

        Args:
            target_var: The variable that will hold the absolute value.
            source_expr: The expression whose absolute value is computed.
            source_expr_range: Lower/upper bound of source_expr.
        """
        pass

    @abstractmethod
    def add_squared_equality(self, target_var: Any, source_var: Any, source_var_range: tuple[int, int]) -> None:
        """
        Add a constraint that target_var = source_var^2.

        Args:
            target_var: The variable that will hold the square.
            source_var: The variable or constant to square.
            source_var_range: Lower/upper bound of source_var.
        """
        pass

    @abstractmethod
    def create_solution_callback(
        self,
        objective_var: Any = None,
        solution_callback: Callable[[Any], None] | None = None,
        progress_callback: Callable[[SolverProgress], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> Any:
        """
        Create a solution callback for tracking intermediate solutions during solving.

        Args:
            objective_var: The objective variable to track (optional, solver-specific).
            solution_callback: Optional app-level callback receiving the registered
                solver-specific callback for each intermediate solution.
            progress_callback: Optional callback for normalized solver progress events.
            should_stop: Optional callback returning True when solving should stop early.

        Returns:
            A solver-specific solution callback object, or None if not supported.
        """
        pass

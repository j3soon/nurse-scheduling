"""Mutable runtime state shared while building and exporting schedules."""

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

from dataclasses import dataclass, field
from typing import Any

from .models import CompiledSchedule, NurseSchedulingData
from .report import Report
from .solver_interface import SolverInterface


@dataclass
class Context:
    """Validated scenario data and mutable state for one solver run."""

    scenario: NurseSchedulingData
    compiled_schedule: CompiledSchedule = field(init=False)

    # Computed fields
    n_days: int = field(init=False)
    n_shift_types: int = field(init=False)
    n_people: int = field(init=False)

    # Fields used by the solver (abstracted)
    solver: SolverInterface | None = None
    model_vars: dict[str, Any] = field(default_factory=dict)
    # `shifts[(d, s, p)]` is 1 exactly when person p works shift type s
    # on day d.
    shifts: dict[tuple[int, int, int], Any] = field(default_factory=dict)
    # `offs[(d, p)]` is 1 exactly when person p is off on day d.
    offs: dict[tuple[int, int], Any] = field(default_factory=dict)

    # Results and reporting
    reports: list[Report] = field(default_factory=list)
    solver_status: str | None = None

    # Maps (day, shift_type) to the preference index that defines it.
    shift_type_requirement_coverage: dict[tuple[int, int], int] = field(default_factory=dict)

    # Optimization objective (expression type varies by solver)
    objective: Any = 0

    def __post_init__(self) -> None:
        self.compiled_schedule = self.scenario.compiled_schedule
        self.n_days = len(self.compiled_schedule.dates)
        self.n_shift_types = len(self.scenario.shiftTypes.items)
        self.n_people = len(self.scenario.people.items)

    @classmethod
    def from_validated(cls, data: NurseSchedulingData) -> "Context":
        """Create runtime state without validating or resolving input twice."""
        # Keep generated dates in the compiled snapshot instead of mutating
        # the validated source model to populate its optional date items.
        return cls(scenario=data)

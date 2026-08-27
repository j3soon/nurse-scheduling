"""Runtime context object used while building and exporting schedules."""

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

from collections.abc import Mapping
from typing import Any

from pydantic import ConfigDict, Field

from .models import (
    NurseSchedulingData,
)
from .report import Report
from .solver_interface import SolverInterface


class Context(NurseSchedulingData):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Computed fields
    n_days: int = None
    n_shift_types: int = None
    n_people: int = None

    # Mapping fields
    map_sid_s: Mapping[str | int, tuple[int, ...]] = Field(
        default_factory=dict
    )  # Maps shift type ID to shift type indices
    map_pid_p: Mapping[str | int, tuple[int, ...]] = Field(
        default_factory=dict
    )  # Maps person/group ID to person indices
    map_did_d: Mapping[str, tuple[int, ...]] = Field(default_factory=dict)  # Maps date/group ID to date indices

    # Fields used by the solver (abstracted)
    solver: SolverInterface | None = None
    model_vars: dict[str, Any] = Field(default_factory=dict)
    shifts: dict[tuple[int, int, int], Any] = Field(default_factory=dict)
    """A set of indicator variables (shifts[(d, s, p)]) that are 1 if
    and only if a person (p) is assigned to a shift type (s) on day (d)."""
    offs: dict[tuple[int, int], Any] = Field(default_factory=dict)
    """A set of indicator variables (offs[(d, p)]) that are 1 if and
    only if a person (p) is off on day (d)."""

    # Results and reporting
    reports: list[Report] = Field(default_factory=list)
    solver_status: str | None = None

    # Lookup maps
    map_ds_p: dict[tuple[int, int], set[int]] = Field(default_factory=dict)  # Maps (day, shift_type) to set of people
    map_dp_s: dict[tuple[int, int], set[int]] = Field(default_factory=dict)  # Maps (day, person) to set of shift types
    map_d_sp: dict[int, set[tuple[int, int]]] = Field(
        default_factory=dict
    )  # Maps day to set of (shift_type, person) pairs
    map_s_dp: dict[int, set[tuple[int, int]]] = Field(
        default_factory=dict
    )  # Maps shift_type to set of (day, person) pairs
    map_p_ds: dict[int, set[tuple[int, int]]] = Field(
        default_factory=dict
    )  # Maps person to set of (day, shift_type) pairs
    shift_type_requirement_coverage: dict[tuple[int, int], int] = Field(
        default_factory=dict
    )  # Maps (day, shift_type) to the preference index that defines it

    # Optimization objective (expression type varies by solver)
    objective: Any = 0

    @classmethod
    def from_validated(cls, data: NurseSchedulingData) -> "Context":
        """Create runtime state without validating or resolving the input twice."""
        compiled = data.compiled_schedule
        # The source model and compiled snapshot were produced by the same
        # validation pass, so model_construct can safely skip a second pass.
        # Copy only the date container to expose generated items without
        # mutating the validated input model.
        ctx = cls.model_construct(
            appVersion=data.appVersion,
            apiVersion=data.apiVersion,
            description=data.description,
            dates=data.dates.model_copy(update={"items": list(compiled.dates)}),
            people=data.people,
            shiftTypes=data.shiftTypes,
            preferences=data.preferences,
            export=data.export,
            n_days=len(compiled.dates),
            n_shift_types=len(data.shiftTypes.items),
            n_people=len(data.people.items),
            map_sid_s=compiled.map_sid_s,
            map_pid_p=compiled.map_pid_p,
            map_did_d=compiled.map_did_d,
        )
        ctx._compiled_schedule = compiled
        return ctx

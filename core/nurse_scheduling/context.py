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

from ortools.sat.python import cp_model
from typing import Dict, List
from datetime import date
from pydantic import ConfigDict, Field

from .models import (
    NurseSchedulingData,
)
from .report import Report

class Context(NurseSchedulingData):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    # Computed fields
    n_days: int = None
    n_shift_types: int = None
    n_people: int = None
    
    # Mapping fields
    map_sid_s: Dict[str | int, List[int]] = Field(default_factory=dict)  # Maps shift type ID to list of shift type indices
    map_pid_p: Dict[str | int, List[int]] = Field(default_factory=dict)  # Maps person/group ID to list of person indices
    map_did_d: Dict[str, List[int]] = Field(default_factory=dict)  # Maps date/group ID to list of date indices
    
    # Fields used by the CP-SAT solver
    model: cp_model.CpModel = Field(default_factory=cp_model.CpModel)
    model_vars: Dict[str, cp_model.IntVar] = Field(default_factory=dict)
    shifts: Dict[tuple[int, int, int], cp_model.IntVar] = Field(default_factory=dict)
    """A set of indicator variables (shifts[(d, s, p)]) that are 1 if
    and only if a person (p) is assigned to a shift type (s) on day (d)."""
    offs: Dict[tuple[int, int], cp_model.IntVar] = Field(default_factory=dict)
    """A set of indicator variables (offs[(d, p)]) that are 1 if and
    only if a person (p) is off on day (d)."""

    # Results and reporting
    reports: List[Report] = Field(default_factory=list)
    solver_status: str | None = None
    
    # Lookup maps
    map_ds_p: Dict[tuple[int, int], set[int]] = Field(default_factory=dict)  # Maps (day, shift_type) to set of people
    map_dp_s: Dict[tuple[int, int], set[int]] = Field(default_factory=dict)  # Maps (day, person) to set of shift types
    map_d_sp: Dict[int, set[tuple[int, int]]] = Field(default_factory=dict)  # Maps day to set of (shift_type, person) pairs
    map_s_dp: Dict[int, set[tuple[int, int]]] = Field(default_factory=dict)  # Maps shift_type to set of (day, person) pairs
    map_p_ds: Dict[int, set[tuple[int, int]]] = Field(default_factory=dict)  # Maps person to set of (day, shift_type) pairs
    
    # Optimization objective
    objective: cp_model.LinearExpr = 0

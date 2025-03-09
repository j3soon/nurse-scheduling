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
    dates: List[date] = Field(default_factory=list)
    n_days: int = None
    n_shift_types: int = None
    n_people: int = None
    
    # Mapping fields
    map_sid_s: Dict[str | int, List[int]] = Field(default_factory=dict)  # Maps shift type ID to list of shift type indices
    map_pid_p: Dict[str | int, List[int]] = Field(default_factory=dict)  # Maps person/group ID to list of person indices
    
    # Fields used by the CP-SAT solver
    model: cp_model.CpModel = Field(default_factory=cp_model.CpModel)
    model_vars: Dict[str, cp_model.IntVar] = Field(default_factory=dict)
    shifts: Dict[tuple[int, int, int], cp_model.IntVar] = Field(default_factory=dict)
    """A set of indicator variables that are 1 if and only if
    a person (p) is assigned to a shift type (s) on day (d)."""

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

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
    n_requirements: int = None
    n_people: int = None
    
    # Mapping fields
    map_rid_r: Dict[str | int, List[int]] = Field(default_factory=dict)  # Maps requirement ID to list of requirement indices
    map_pid_p: Dict[str | int, List[int]] = Field(default_factory=dict)  # Maps person/group ID to list of person indices
    
    # Solver-related fields
    model: cp_model.CpModel = Field(default_factory=cp_model.CpModel)
    model_vars: Dict[str, cp_model.IntVar] = Field(default_factory=dict)
    shifts: Dict[tuple[int, int, int], cp_model.IntVar] = Field(default_factory=dict)
    """A set of indicator variables that are 1 if and only if
    a person (p) is assigned to a shift (d, r)."""
    reports: List[Report] = Field(default_factory=list)
    
    # Lookup maps
    map_dr_p: Dict[tuple[int, int], set[int]] = Field(default_factory=dict)  # Maps (day, requirement) to set of people
    map_dp_r: Dict[tuple[int, int], set[int]] = Field(default_factory=dict)  # Maps (day, person) to set of requirements
    map_d_rp: Dict[int, set[tuple[int, int]]] = Field(default_factory=dict)  # Maps day to set of (requirement, person) pairs
    map_r_dp: Dict[int, set[tuple[int, int]]] = Field(default_factory=dict)  # Maps requirement to set of (day, person) pairs
    map_p_dr: Dict[int, set[tuple[int, int]]] = Field(default_factory=dict)  # Maps person to set of (day, requirement) pairs
    
    # Optimization objective
    objective: cp_model.LinearExpr = 0

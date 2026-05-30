"""Low-level PuLP CuOpt solver encoding tests for comparison constraints."""

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
#
# This test is mostly AI generated.

import os
import sys

import pytest
import pulp

# Add the project root to the Python path so imports work when running directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nurse_scheduling.solver_interface import SolverStatus
from nurse_scheduling.solver_pulp_cuopt import PuLPCuOptSolver


def test_pulp_cuopt_solver_uses_cuopt_engine():
    solver = PuLPCuOptSolver()
    assert solver.engine == "cuopt"


def test_pulp_cuopt_solver_availability_handling():
    solver = PuLPCuOptSolver()
    x = solver.new_bool_var("x")
    solver.add_constraint(x == 1, name="fix_x")
    solver.set_objective(x, maximize=True)

    cuopt_available = hasattr(pulp, "CUOPT") and bool(pulp.CUOPT(msg=False).available())
    if not cuopt_available:
        with pytest.raises(RuntimeError, match="not available"):
            solver.solve()
        return

    status = solver.solve()
    assert status in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE)
    assert round(solver.get_value(x)) == 1

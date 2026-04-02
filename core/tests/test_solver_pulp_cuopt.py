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

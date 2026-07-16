"""Low-level tests for PuLP's HiGHS and SCIP Python-API backends."""

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

# This test is mostly AI generated.

import pulp
import pytest

import nurse_scheduling.solver_pulp as solver_pulp_module
from nurse_scheduling.solver_interface import SolverStatus
from nurse_scheduling.solver_pulp_python import PuLPHiGHSSolver, PuLPSCIPSolver


@pytest.mark.parametrize(
    ("solver_class", "engine", "pulp_solver_class"),
    [
        (PuLPHiGHSSolver, "highs", pulp.HiGHS),
        (PuLPSCIPSolver, "scip", pulp.SCIP_PY),
    ],
)
def test_pulp_python_api_backends_solve_integer_model(solver_class, engine, pulp_solver_class):
    solver = solver_class()
    x = solver.new_bool_var("x")
    solver.add_constraint(x == 1)
    solver.set_objective(x)
    events = []

    status = solver.solve(timeout=5, progress_callback=events.append)

    assert solver.engine == engine
    assert isinstance(solver.solver, pulp_solver_class)
    assert status == SolverStatus.OPTIMAL
    assert solver.get_value(x) == 1
    assert solver.get_objective_value() == 1
    assert events[-1].source == f"pulp/{engine}:final-result"
    assert events[-1].currentBestScore == 1


@pytest.mark.parametrize("solver_class", [PuLPHiGHSSolver, PuLPSCIPSolver])
def test_pulp_python_api_backends_support_deterministic_solve(solver_class):
    solver = solver_class()
    x = solver.new_bool_var("x")
    solver.set_objective(x)

    assert solver.solve(timeout=5, deterministic=True) == SolverStatus.OPTIMAL
    assert solver.get_value(x) == 1


@pytest.mark.parametrize(
    ("solver_class", "pulp_class_name"),
    [
        (PuLPHiGHSSolver, "HiGHS"),
        (PuLPSCIPSolver, "SCIP_PY"),
    ],
)
def test_pulp_python_api_backend_reports_unavailable_runtime(monkeypatch, solver_class, pulp_class_name):
    class UnavailableSolver:
        def __init__(self, **_kwargs):
            pass

        def available(self):
            return False

    monkeypatch.setattr(solver_pulp_module.pulp, pulp_class_name, UnavailableSolver)
    solver = solver_class()
    solver.set_objective(0)

    with pytest.raises(RuntimeError, match="not available in this environment"):
        solver.solve()

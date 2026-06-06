"""PuLP solver progress callback tests."""

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

import os
import sys
import time

import pulp
import pytest

# Add the project root to the Python path so imports work when running directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nurse_scheduling.solver_interface import SolverStatus
from nurse_scheduling.solver_pulp_cbc import PuLPSolver
from nurse_scheduling.solver_pulp_cuopt import PuLPCuOptSolver


@pytest.mark.parametrize(
    ("line", "source"),
    [
        (
            "Cbc0004I Integer solution of -21 found after 0 iterations and 0 nodes (0.00 seconds)",
            "integer-solution",
        ),
        (
            "Cbc0012I Integer solution of -21 found by feasibility pump after 0 iterations and 0 nodes (0.00 seconds)",
            "integer-solution",
        ),
        (
            "Cbc0016I Integer solution of -21 found by strong branching after 0 iterations and 0 nodes (0.00 seconds)",
            "integer-solution",
        ),
        (
            "Cbc0024I Integer solution of -21 found by subtree after 0 iterations and 0 nodes (0.00 seconds)",
            "integer-solution",
        ),
        (
            "Cbc0033I Integer solution of -21 found (by alternate solver) after 0 iterations and 0 nodes (0.00 seconds)",
            "integer-solution",
        ),
        (
            "Cbc0048I Final check on integer solution of -21 found after 0 iterations and 0 nodes (0.00 seconds)",
            "final-check-solution",
        ),
    ],
)
def test_pulp_cbc_progress_parser_converts_maximize_integer_solution_sign(line, source):
    solver = PuLPSolver()
    solver.set_objective(0, maximize=True)

    payload = solver._parse_solver_log_progress(line, start_time=time.monotonic())

    assert payload is not None
    assert payload.source == f"pulp/cbc:solver-log:{source}"
    assert payload.currentBestScore == 21
    assert payload.elapsedSeconds >= 0


def test_pulp_cbc_progress_parser_keeps_final_objective_sign():
    solver = PuLPSolver()
    solver.set_objective(0, maximize=True)

    payload = solver._parse_solver_log_progress(
        "Objective value:                21.00000000", start_time=time.monotonic()
    )

    assert payload is not None
    assert payload.source == "pulp/cbc:solver-log:final-objective"
    assert payload.currentBestScore == 21


@pytest.mark.parametrize(
    ("line", "source", "score"),
    [
        (
            "B       3        1       -2.700000e+01  -2.980000e+01      2   6.7e-01     10.4%      0.00",
            "branch-and-bound",
            -27,
        ),
        ("H +2.100000e+01 +2.100000e+01  0.00%      0.20", "heuristic", 21),
        ("New solution from primal heuristics. Objective +2.100000e+01. Time 0.20", "primal-heuristic", 21),
        (
            "New solution from early primal heuristics (CPUFJ). Objective +2.100000e+01. Time 0.05",
            "primal-heuristic",
            21,
        ),
        ("Optimal solution found at root node. Objective 2.1000000000000000e+01. Time 0.20.", "root-optimal", 21),
        (
            "Solution objective: 21.000000 , relative_mip_gap 0.000000 solution_bound 21.000000",
            "final-objective",
            21,
        ),
    ],
)
def test_pulp_cuopt_progress_parser_reads_documented_objective_lines(line, source, score):
    solver = PuLPCuOptSolver()
    solver.set_objective(0, maximize=True)

    payload = solver._parse_solver_log_progress(line, start_time=time.monotonic())

    assert payload is not None
    assert payload.source == f"pulp/cuopt:solver-log:{source}"
    assert payload.currentBestScore == score


def test_pulp_cbc_solve_replays_solver_output_and_emits_final_progress(capsys):
    solver = PuLPSolver()
    x = solver.new_bool_var("x")
    solver.add_constraint(x == 1, name="fix_x")
    solver.set_objective(x, maximize=True)
    events = []

    status = solver.solve(progress_callback=events.append)

    output = capsys.readouterr().out
    assert status == SolverStatus.OPTIMAL
    assert "Welcome to the CBC MILP Solver" in output
    assert any(event.source == "pulp/cbc:final-result" and event.currentBestScore == 1 for event in events)


def test_pulp_solve_rejects_should_stop():
    solver = PuLPSolver()
    x = solver.new_bool_var("x")
    solver.add_constraint(x == 1, name="fix_x")
    solver.set_objective(x, maximize=True)

    with pytest.raises(NotImplementedError, match="do not support cooperative stop callbacks"):
        solver.solve(should_stop=lambda: False)


def test_pulp_cuopt_solve_emits_final_progress(capsys):
    cuopt_available = hasattr(pulp, "CUOPT") and bool(pulp.CUOPT(msg=False).available())
    if not cuopt_available:
        pytest.skip("PuLP/cuOpt backend is not available")

    solver = PuLPCuOptSolver()
    x = solver.new_bool_var("x")
    solver.add_constraint(x == 1, name="fix_x")
    solver.set_objective(x, maximize=True)
    events = []

    status = solver.solve(progress_callback=events.append)

    output = capsys.readouterr().out
    assert status in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE)
    assert "CUOPT status=" in output
    assert any(event.source == "pulp/cuopt:final-result" and event.currentBestScore == 1 for event in events)

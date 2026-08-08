"""Configured solver selection and runtime availability checks."""

# This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
#
# Copyright (C) 2023-2026 Johnson Sun
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

from ..scheduler import ORTOOLS_CP_SAT_SOLVER, normalize_solver_selector
from .solver_capabilities import SOLVER_CAPABILITIES_BY_VALUE, get_solver_capabilities


def normalize_solver_option(value: str) -> str:
    """Return a canonical solver registered for server use."""
    capabilities = get_solver_capabilities(value)
    if capabilities is None:
        supported = ", ".join(SOLVER_CAPABILITIES_BY_VALUE)
        raise ValueError(f"Unsupported server solver {value!r}. Expected one of: {supported}")
    return capabilities.value


def solver_is_available(value: str) -> bool:
    """Return whether a configured solver runtime can be initialized."""
    selector = normalize_solver_selector(value)
    try:
        if selector.canonical == ORTOOLS_CP_SAT_SOLVER:
            from ortools.sat.python import cp_model

            cp_model.CpSolver()
            return True
        if selector.api == "mpsolver":
            from ortools.linear_solver import pywraplp

            from ..solver_ortools_linear import ORTOOLS_MPSOLVER_MIP_ENGINES

            return pywraplp.Solver.CreateSolver(ORTOOLS_MPSOLVER_MIP_ENGINES[selector.engine]) is not None
        if selector.api == "mathopt":
            from ortools.math_opt.python import mathopt

            from ..solver_ortools_mathopt import ORTOOLS_MATHOPT_MIP_ENGINES

            result = mathopt.solve(mathopt.Model(), ORTOOLS_MATHOPT_MIP_ENGINES[selector.engine])
            return result.termination.reason == mathopt.TerminationReason.OPTIMAL

        import pulp

        class_name = {
            "cbc": "PULP_CBC_CMD",
            "cuopt": "CUOPT",
            "glpk": "GLPK_CMD",
            "highs": "HiGHS",
            "scip": "SCIP_PY",
        }[selector.engine]
        solver_class = getattr(pulp, class_name, None)
        if solver_class is None:
            return False
        solver = solver_class(msg=False)
        if not solver.available():
            return False
        if selector.engine == "cuopt":
            problem = pulp.LpProblem("cuopt-availability", pulp.LpMinimize)
            variable = pulp.LpVariable("available", lowBound=0.0, upBound=1.0)
            problem += 1.0 * variable
            problem += 1.0 * variable == 1.0
            return problem.solve(solver) == pulp.LpStatusOptimal
        return True
    except (AttributeError, ImportError, KeyError, OSError, RuntimeError, TypeError, ValueError):
        return False


def validate_solver_availability(solver_ids: tuple[str, ...]) -> None:
    """Reject a deployment that advertises an unavailable solver."""
    for solver_id in solver_ids:
        if not solver_is_available(solver_id):
            raise ValueError(f"Configured solver is unavailable: {solver_id}")

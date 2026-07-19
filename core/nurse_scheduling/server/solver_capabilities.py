"""Canonical server-facing solver capability registry."""

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

from dataclasses import dataclass
from typing import Literal

from ..scheduler import CANONICAL_SOLVER_CHOICES


@dataclass(frozen=True)
class SolverCapabilities:
    """Stable traits used by the server and advertised to API clients."""

    value: str
    label: str
    compute: Literal["cpu", "gpu"]
    graceful_timeout: bool
    finish_now: bool
    intermediate_scores: bool


def _capabilities(
    value: str,
    label: str,
    *,
    compute: Literal["cpu", "gpu"] = "cpu",
    graceful_timeout: bool = False,
    finish_now: bool = False,
    intermediate_scores: bool = False,
) -> SolverCapabilities:
    return SolverCapabilities(
        value=value,
        label=label,
        compute=compute,
        graceful_timeout=graceful_timeout,
        finish_now=finish_now,
        intermediate_scores=intermediate_scores,
    )


SOLVER_CAPABILITIES = (
    _capabilities(
        "ortools/cp-sat",
        "OR-Tools | CP-SAT",
        graceful_timeout=True,
        finish_now=True,
        intermediate_scores=True,
    ),
    _capabilities("ortools/mpsolver/cbc", "OR-Tools | MPSolver | CBC"),
    _capabilities("ortools/mpsolver/scip", "OR-Tools | MPSolver | SCIP"),
    _capabilities("ortools/mpsolver/cp-sat", "OR-Tools | MPSolver | CP-SAT"),
    _capabilities("ortools/mpsolver/bop", "OR-Tools | MPSolver | BOP"),
    _capabilities("ortools/mathopt/gscip", "OR-Tools | MathOpt | GSCIP"),
    _capabilities("ortools/mathopt/cp-sat", "OR-Tools | MathOpt | CP-SAT"),
    _capabilities("ortools/mathopt/highs", "OR-Tools | MathOpt | HiGHS"),
    _capabilities("pulp/cbc", "PuLP | CBC", intermediate_scores=True),
    _capabilities(
        "pulp/cuopt",
        "PuLP | cuOpt",
        compute="gpu",
        graceful_timeout=True,
        intermediate_scores=True,
    ),
    _capabilities("pulp/glpk", "PuLP | GLPK"),
    _capabilities("pulp/highs", "PuLP | HiGHS"),
    _capabilities("pulp/scip", "PuLP | SCIP"),
)
"""Capabilities for every solver accepted by the scheduling layer."""

SOLVER_CAPABILITIES_BY_VALUE = {item.value: item for item in SOLVER_CAPABILITIES}

if tuple(SOLVER_CAPABILITIES_BY_VALUE) != CANONICAL_SOLVER_CHOICES:
    raise RuntimeError("Solver capability registry must match the canonical solver choices")


def get_solver_capabilities(solver: str) -> SolverCapabilities | None:
    """Return capabilities for a normalized selector, if it is registered."""
    return SOLVER_CAPABILITIES_BY_VALUE.get(solver.strip().lower())


def solver_supports_finish_now(solver: str) -> bool:
    """Return whether a running solver can return its current result."""
    capabilities = get_solver_capabilities(solver)
    return capabilities is not None and capabilities.finish_now

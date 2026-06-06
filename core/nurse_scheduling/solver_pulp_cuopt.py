"""PuLP/cuOpt solver wrapper."""

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

import re
import time

from .solver_interface import SolverProgress, assert_int_score
from .solver_pulp import BasePuLPSolver


class PuLPCuOptSolver(BasePuLPSolver):
    """PuLP solver configured to use NVIDIA cuOpt."""

    # cuOpt MILP progress references:
    # - https://github.com/NVIDIA/cuopt/blob/main/docs/cuopt/source/cuopt-cli/cli-examples.rst#mixed-integer-programming-example
    # - https://github.com/NVIDIA/cuopt/blob/main/docs/cuopt/source/cuopt-c/lp-qp-milp/milp-examples.rst#example-with-mps-file
    # - https://github.com/NVIDIA/cuopt/blob/dd11941df1822cdb22c892d0487fe196522d0424/cpp/src/branch_and_bound/branch_and_bound.cpp#L361-L400
    # Targets:
    # - B ... <objective> <bound> ...: incumbent branch-and-bound report row.
    # - H <objective> <bound> ...: incumbent heuristic report row.
    # - New solution from primal heuristics. Objective <objective>. ...
    # - New solution from early primal heuristics (<name>). Objective <objective>. ...
    # - Optimal solution found at root node. Objective <objective>. ...
    # - Solution objective: <objective> ...
    # TODO: May need to check for duplications
    _NUMBER_RE = r"([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)"
    _PROGRESS_PATTERNS = (
        ("branch-and-bound", re.compile(rf"^[A-Z]\s+\d+\s+\d+\s+{_NUMBER_RE}")),
        ("heuristic", re.compile(rf"^H\s+{_NUMBER_RE}")),
        (
            "primal-heuristic",
            re.compile(rf"New solution from (?:early )?primal heuristics(?: \([^)]+\))?\.\s+Objective\s+{_NUMBER_RE}"),
        ),
        ("root-optimal", re.compile(rf"Optimal solution found at root node\.\s+Objective\s+{_NUMBER_RE}")),
        ("final-objective", re.compile(rf"Solution objective:\s+{_NUMBER_RE}")),
    )

    def __init__(self):
        super().__init__(engine="cuopt")

    def _parse_solver_log_progress(self, line: str, start_time: float) -> SolverProgress | None:
        """Parse cuOpt log output into normalized progress events."""
        stripped_line = line.strip()
        match = None
        source = None
        for candidate_source, pattern in self._PROGRESS_PATTERNS:
            match = pattern.search(stripped_line)
            if match is not None:
                source = candidate_source
                break
        if match is None:
            return None

        raw_objective = float(match.group(1))
        return SolverProgress(
            source=f"pulp/cuopt:solver-log:{source}",
            currentBestScore=assert_int_score(raw_objective, label="PuLP/cuOpt progress score"),
            elapsedSeconds=round(time.monotonic() - start_time, 3),
        )

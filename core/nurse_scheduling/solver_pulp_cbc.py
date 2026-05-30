"""PuLP/CBC solver wrapper."""

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


class PuLPSolver(BasePuLPSolver):
    """PuLP solver configured to use CBC."""

    # CBC message references:
    # - https://raw.githubusercontent.com/coin-or/Cbc/refs/heads/gh-pages/messages.md
    # - https://raw.githubusercontent.com/coin-or/Cbc/master/src/CbcMessage.cpp
    # Targets:
    # - Cbc0004I: Integer solution of %g found after ...
    # - Cbc0012I: Integer solution of %.13g found by %s after ...
    # - Cbc0016I: Integer solution of %g found by strong branching after ...
    # - Cbc0024I: Integer solution of %g found by subtree after ...
    # - Cbc0033I: Integer solution of %g found (by alternate solver) after ...
    # - Cbc0048I: Final check on integer solution of %g found after ...
    _INTEGER_SOLUTION_RE = re.compile(r"Cbc\d{4}I Integer solution of\s+([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)")
    _FINAL_CHECK_SOLUTION_RE = re.compile(
        r"Cbc0048I Final check on integer solution of\s+([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)"
    )
    # CBC final solution summary line observed in CBC command-line output.
    _FINAL_OBJECTIVE_RE = re.compile(r"Objective value:\s+([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)")

    def __init__(self):
        super().__init__(engine="cbc")

    def _score_from_solver_log_objective(self, raw_objective: float, *, source: str) -> int:
        """Convert a CBC log objective to the model's objective direction."""
        score = raw_objective
        if source != "final-objective" and self.maximize:
            # CBC logs maximization incumbents from PuLP's generated MPS model as negated minimization values.
            score = -score
        return assert_int_score(score, label="PuLP/CBC progress score")

    def _parse_solver_log_progress(self, line: str, start_time: float) -> SolverProgress | None:
        """Parse CBC log output into normalized progress events."""
        stripped_line = line.strip()
        match = self._INTEGER_SOLUTION_RE.search(stripped_line)
        source = "integer-solution"
        if match is None:
            match = self._FINAL_CHECK_SOLUTION_RE.search(stripped_line)
            source = "final-check-solution"
        if match is None:
            match = self._FINAL_OBJECTIVE_RE.search(stripped_line)
            source = "final-objective"
        if match is None:
            return None

        raw_objective = float(match.group(1))
        return SolverProgress(
            source=f"pulp/cbc:solver-log:{source}",
            currentBestScore=self._score_from_solver_log_objective(raw_objective, source=source),
            elapsedSeconds=round(time.time() - start_time, 3),
        )

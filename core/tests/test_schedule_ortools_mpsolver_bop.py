"""Bounded schedule smoke test for the OR-Tools/MPSolver BOP backend."""

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

from pathlib import Path

import nurse_scheduling


TESTCASE = Path(__file__).parent / "testcases" / "basics" / "01_1nurse_1shift_1day.yaml"


def test_schedule_ortools_mpsolver_bop_smoke():
    df, _solution, score, status, _cell_export_info = nurse_scheduling.schedule(
        TESTCASE.read_bytes(),
        solver="ortools/mpsolver/bop",
        timeout=5,
    )

    assert df is not None
    assert score == 0
    assert status == "OPTIMAL"

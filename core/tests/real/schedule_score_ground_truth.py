"""Replay a real assignment and verify its canonical objective score."""

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

import json

import pytest

import nurse_scheduling

from .assignment_fixture import deserialize_assignment_fixture
from .schedule_real_helper import REAL_TESTCASE

ASSIGNMENT_FIXTURES = sorted(REAL_TESTCASE.parent.glob(f"{REAL_TESTCASE.stem}.assignment-*.json"))
REPLAY_TIMEOUT_SECONDS = 60


@pytest.mark.parametrize(
    "assignment_fixture",
    ASSIGNMENT_FIXTURES,
    ids=lambda path: path.stem.rpartition("assignment-")[2],
)
def test_real_schedule_assignment_has_expected_score(assignment_fixture):
    file_content = REAL_TESTCASE.read_bytes()
    fixture = json.loads(assignment_fixture.read_text(encoding="utf-8"))
    forced_solution, expected_score = deserialize_assignment_fixture(file_content, fixture)

    result = nurse_scheduling.schedule(
        file_content,
        forced_solution=forced_solution,
        solver="ortools/cp-sat",
        timeout=REPLAY_TIMEOUT_SECONDS,
    )

    assert result.solver_status == "OPTIMAL"
    assert result.solution == forced_solution
    assert result.score == expected_score

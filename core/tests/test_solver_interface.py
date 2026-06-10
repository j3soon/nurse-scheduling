"""Tests for public solver interface helper payloads."""

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

import pytest

from nurse_scheduling.solver_interface import (
    SchedulePhaseProgress,
    SolverProgress,
    assert_int_score,
    count_export_comments,
    serialize_solver_progress,
)


def test_solver_progress_to_dict_uses_wire_payload_shape():
    payload = SolverProgress(source="solver", currentBestScore=12, elapsedSeconds=1.5, solutionIndex=2)

    assert payload.to_dict() == {
        "source": "solver",
        "currentBestScore": 12,
        "elapsedSeconds": 1.5,
        "solutionIndex": 2,
    }


def test_solver_progress_export_summary_counts_comment_notes():
    payload = SolverProgress(
        source="solver",
        currentBestScore=12,
        elapsedSeconds=1.5,
        cell_export_info={
            "comments": {
                (0, 0): ["first", "second"],
                (1, 0): ["third"],
            }
        },
    )

    assert serialize_solver_progress(payload, include_export_summary=True)["commentCount"] == 3


@pytest.mark.parametrize("cell_export_info", [None, [], {"comments": []}])
def test_count_export_comments_returns_none_for_non_comment_metadata(cell_export_info):
    assert count_export_comments(cell_export_info) is None


def test_schedule_phase_progress_to_dict_uses_wire_payload_shape():
    payload = SchedulePhaseProgress(
        source="scheduler",
        code="create-model",
        message="Creating model",
        elapsedSeconds=0.25,
    )

    assert payload.to_dict() == {
        "source": "scheduler",
        "code": "create-model",
        "message": "Creating model",
        "elapsedSeconds": 0.25,
    }


def test_assert_int_score_accepts_near_integral_values():
    assert assert_int_score("4.0000001", label="objective", integer_tolerance=1e-5) == 4


def test_assert_int_score_rejects_fractional_values():
    with pytest.raises(AssertionError, match="objective should be an integer"):
        assert_int_score(4.25, label="objective")

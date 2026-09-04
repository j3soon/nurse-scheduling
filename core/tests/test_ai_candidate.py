"""Tests for trusted review of complete AI schedule candidates."""

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

from nurse_scheduling.ai.candidate import review_schedule_candidate

from .ai_test_helper import SCHEDULE_BYTE_LIMIT, schedule_yaml


def test_unchanged_candidate_creates_no_proposal():
    schedule = schedule_yaml()

    review = review_schedule_candidate(schedule, schedule, SCHEDULE_BYTE_LIMIT)

    assert review.outcome.ok
    assert review.proposal is None


def test_valid_candidate_creates_structural_proposal():
    base = schedule_yaml()
    candidate = base.replace(
        "  - id: P1\n    description: ''",
        "  - id: P1\n    description: Head",
        1,
    )

    review = review_schedule_candidate(base, candidate, SCHEDULE_BYTE_LIMIT)

    assert review.outcome.ok
    assert review.proposal is not None
    assert review.proposal.text == candidate
    assert "people.items[0].description" in review.proposal.diff.render()


def test_candidate_with_new_validation_problem_is_rejected():
    base = schedule_yaml()

    review = review_schedule_candidate(base, "not: [valid", SCHEDULE_BYTE_LIMIT)

    assert not review.outcome.ok
    assert "cannot become a proposal" in review.outcome.text
    assert "introduces problems" in review.outcome.text
    assert review.proposal is None

"""Trusted validation and proposal creation for AI schedule candidates."""

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

# This code is mostly AI generated.

from dataclasses import dataclass
from typing import Literal

from ruamel.yaml.error import YAMLError

from ..loader import _load_yaml
from .diff import ScheduleDiff, diff_schedules
from .validation import new_schedule_issues, validate_frontend_schedule_yaml

SCHEDULE_FILENAME = "schedule.yaml"


@dataclass(frozen=True)
class CandidateOutcome:
    """A bounded explanation of trusted candidate review."""

    text: str
    ok: bool


@dataclass(frozen=True)
class ScheduleProposal:
    """A validated schedule the user can approve, with what it changes."""

    text: str
    diff: ScheduleDiff


@dataclass(frozen=True)
class PendingProposal:
    """Session-owned YAML and rendered diff, with the run that proposed them."""

    schedule_yaml: str
    diff: str
    # Approval and rejection decisions are logged under the proposing run.
    run_id: str | None


@dataclass(frozen=True)
class ProposalApproval:
    """Approved YAML or a refused proposal, with its originating audit run."""

    schedule_yaml: str | None
    run_id: str | None

    @property
    def decision(self) -> Literal["approved", "invalid"]:
        return "approved" if self.schedule_yaml is not None else "invalid"


@dataclass(frozen=True)
class ScheduleCandidateReview:
    """Trusted validation and proposal result for one complete candidate."""

    outcome: CandidateOutcome
    proposal: ScheduleProposal | None


def review_schedule_candidate(base_text: str, candidate: str, max_bytes: int) -> ScheduleCandidateReview:
    """Validate and compare untrusted candidate text outside the sandbox."""
    if candidate == base_text:
        return ScheduleCandidateReview(CandidateOutcome(f"{SCHEDULE_FILENAME} is unchanged.", True), None)

    base_validation = validate_frontend_schedule_yaml(base_text, max_bytes)
    validation = validate_frontend_schedule_yaml(candidate, max_bytes)
    introduced = () if validation.valid else new_schedule_issues(base_validation, validation)
    if introduced:
        problems = "\n".join(f"- {issue.location}: {issue.message}" for issue in introduced)
        return ScheduleCandidateReview(
            CandidateOutcome(
                f"{SCHEDULE_FILENAME} introduces problems and cannot become a proposal.\n{problems}",
                False,
            ),
            None,
        )

    try:
        before = _load_yaml(base_text.encode("utf-8"))
        after = _load_yaml(candidate.encode("utf-8"))
    except (YAMLError, TypeError, ValueError) as error:
        return ScheduleCandidateReview(
            CandidateOutcome(f"The schedule could not be compared. {error}", False),
            None,
        )

    diff = diff_schedules(before, after)
    proposal = ScheduleProposal(text=candidate, diff=diff)
    if validation.valid:
        outcome = CandidateOutcome(f"{SCHEDULE_FILENAME} is valid. Changes so far:\n{diff.render()}", True)
    else:
        outcome = CandidateOutcome(
            f"{SCHEDULE_FILENAME} still has problems that were already there, and this edit added none.\n"
            f"{validation.render()}\nChanges so far:\n{diff.render()}",
            True,
        )
    return ScheduleCandidateReview(outcome, proposal)

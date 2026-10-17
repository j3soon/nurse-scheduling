"""Trusted validation and change review for AI schedule candidates."""

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
from io import StringIO

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from ..loader import _load_yaml
from ..models import AT_MOST_ONE_SHIFT_PER_DAY
from .diff import ScheduleDiff, diff_schedules
from .validation import ScheduleIssue, ScheduleValidationResult, new_schedule_issues, validate_frontend_schedule_yaml

SCHEDULE_FILENAME = "schedule.yaml"
REQUIRED_RULE_NOTICE = "The server restored the required 'at most one shift per day' rule."


@dataclass(frozen=True)
class CandidateOutcome:
    """A bounded explanation of trusted candidate review."""

    text: str
    ok: bool


@dataclass(frozen=True)
class ScheduleProposal:
    """A validated schedule change, applied when its run finishes, with what it changes."""

    text: str
    diff: ScheduleDiff


@dataclass(frozen=True)
class ScheduleCandidateReview:
    """Trusted validation and change result for one complete candidate."""

    outcome: CandidateOutcome
    proposal: ScheduleProposal | None


def validate_schedule_change(
    base_text: str, candidate: str, max_bytes: int
) -> tuple[ScheduleValidationResult, tuple[ScheduleIssue, ...]]:
    """Allow existing incomplete input while refusing problems introduced by an edit."""
    validation = validate_frontend_schedule_yaml(candidate, max_bytes)
    if validation.valid:
        return validation, ()
    base_validation = validate_frontend_schedule_yaml(base_text, max_bytes)
    return validation, new_schedule_issues(base_validation, validation)


def review_schedule_candidate(base_text: str, candidate: str, max_bytes: int) -> ScheduleCandidateReview:
    """Validate and compare untrusted candidate text outside the sandbox."""
    if candidate == base_text:
        return ScheduleCandidateReview(CandidateOutcome(f"{SCHEDULE_FILENAME} is unchanged.", True), None)

    validation, introduced = validate_schedule_change(base_text, candidate, max_bytes)
    notice = ""
    if not validation.valid:
        completed = _restore_required_rule(candidate, max_bytes)
        if completed != candidate:
            candidate = completed
            validation, introduced = validate_schedule_change(base_text, candidate, max_bytes)
            notice = REQUIRED_RULE_NOTICE + "\n"
    if introduced:
        problems = "\n".join(f"- {issue.location}: {issue.message}" for issue in introduced)
        return ScheduleCandidateReview(
            CandidateOutcome(
                f"{SCHEDULE_FILENAME} introduces problems and cannot be applied.\n{problems}",
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
        outcome = CandidateOutcome(f"{notice}{SCHEDULE_FILENAME} is valid. Changes so far:\n{diff.render()}", True)
    else:
        outcome = CandidateOutcome(
            f"{SCHEDULE_FILENAME} still has problems that were already there, and this edit added none.\n"
            f"{validation.render()}\nChanges so far:\n{diff.render()}",
            True,
        )
    return ScheduleCandidateReview(outcome, proposal)


def _restore_required_rule(candidate: str, max_bytes: int) -> str:
    """Complete the mandatory app rule only when the whole result validates."""
    content = candidate.encode("utf-8")
    if len(content) > max_bytes:
        return candidate
    try:
        data = _load_yaml(content, reject_aliases=True)
        preferences = data.get("preferences")
        if not isinstance(preferences, list) or any(
            not isinstance(pref, dict) or pref.get("type") == AT_MOST_ONE_SHIFT_PER_DAY for pref in preferences
        ):
            return candidate
        preferences.insert(0, {"type": AT_MOST_ONE_SHIFT_PER_DAY})
        output = StringIO()
        yaml = YAML(typ="safe")
        yaml.default_flow_style = False
        yaml.dump(data, output)
        completed = output.getvalue()
        return completed if validate_frontend_schedule_yaml(completed, max_bytes).valid else candidate
    except (YAMLError, TypeError, ValueError):
        return candidate

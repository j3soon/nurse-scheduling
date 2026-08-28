"""Web frontend schedule validation for the experimental AI service."""

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

from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import ValidationError
from ruamel.yaml.error import YAMLError

from ..frontend_validation import load_frontend_data

# The assistant is reachable only from the web frontend, so it validates the
# frontend subset alone. The canonical backend flavor accepts shapes the editor
# cannot represent, which would let the model produce unusable schedules.
MAX_VALIDATION_ISSUES = 20
MAX_ISSUE_MESSAGE_CHARS = 300
DOCUMENT_LOCATION = "(document)"


@dataclass(frozen=True)
class ScheduleIssue:
    """One validation problem and the schedule path that reported it."""

    location: str
    message: str


@dataclass(frozen=True)
class ScheduleValidationResult:
    """Bounded validation outcome safe to hand back to the model."""

    valid: bool
    issues: tuple[ScheduleIssue, ...] = ()
    omitted_issues: int = 0

    def render(self) -> str:
        """Describe the outcome as bounded text for prompts and tool results."""
        if self.valid:
            return "The schedule is valid for the web frontend editor."
        lines = [f"The schedule is invalid for the web frontend editor. Problems found: {len(self.issues)}."]
        lines.extend(f"- {issue.location}: {issue.message}" for issue in self.issues)
        if self.omitted_issues:
            lines.append(f"- {self.omitted_issues} further problems were not listed.")
        return "\n".join(lines)


def validate_frontend_schedule_yaml(schedule_yaml: str, max_bytes: int) -> ScheduleValidationResult:
    """Validate one schedule against the shapes the web frontend can edit.

    Parsing bounds live in the shared loader, which rejects aliases, deep
    nesting, and oversized node counts before any model is built.
    """
    content = schedule_yaml.encode("utf-8")
    if len(content) > max_bytes:
        return _invalid([ScheduleIssue(DOCUMENT_LOCATION, f"Schedule exceeds the limit of {max_bytes} bytes.")])
    try:
        load_frontend_data(content)
    except ValidationError as error:
        # ValidationError derives from ValueError, so it must be handled first.
        return _invalid([_issue_from_error(entry) for entry in error.errors()])
    except YAMLError as error:
        return _invalid([ScheduleIssue(DOCUMENT_LOCATION, f"Schedule is not readable YAML. {error}")])
    except (TypeError, ValueError) as error:
        return _invalid([ScheduleIssue(DOCUMENT_LOCATION, str(error))])
    return ScheduleValidationResult(valid=True)


def _invalid(issues: list[ScheduleIssue]) -> ScheduleValidationResult:
    """Bound the reported issues so one bad schedule cannot flood the prompt."""
    kept = issues[:MAX_VALIDATION_ISSUES]
    bounded = tuple(ScheduleIssue(issue.location, _bounded_message(issue.message)) for issue in kept)
    return ScheduleValidationResult(valid=False, issues=bounded, omitted_issues=len(issues) - len(kept))


def _issue_from_error(entry: dict) -> ScheduleIssue:
    """Convert one Pydantic error entry into a located schedule issue."""
    return ScheduleIssue(format_schedule_location(entry.get("loc", ())), str(entry.get("msg", "Invalid value.")))


def new_schedule_issues(
    before: ScheduleValidationResult,
    after: ScheduleValidationResult,
) -> tuple[ScheduleIssue, ...]:
    """Report the problems an edit introduced, ignoring those already present.

    Both results are bounded, so a schedule with more problems than the reported
    limit can hide one. That is acceptable, because the user still reviews the
    diff before anything is applied.
    """
    existing = {(issue.location, issue.message) for issue in before.issues}
    return tuple(issue for issue in after.issues if (issue.location, issue.message) not in existing)


def format_schedule_location(location: Sequence[object]) -> str:
    """Render a schedule path such as `people.items[0].id` from its parts."""
    parts: list[str] = []
    for entry in location:
        if isinstance(entry, int):
            parts.append(f"[{entry}]")
        else:
            parts.append(f".{entry}" if parts else str(entry))
    return "".join(parts) or DOCUMENT_LOCATION


def _bounded_message(message: str) -> str:
    """Keep one message short enough to stay readable in a bounded result."""
    collapsed = " ".join(message.split())
    if len(collapsed) <= MAX_ISSUE_MESSAGE_CHARS:
        return collapsed
    return collapsed[: MAX_ISSUE_MESSAGE_CHARS - 3] + "..."

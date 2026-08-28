"""A single-file editor over the schedule the assistant is working on."""

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

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ruamel.yaml.error import YAMLError

from ..loader import _load_yaml
from .diff import ScheduleDiff, diff_schedules
from .validation import validate_frontend_schedule_yaml

# The assistant edits one document, so the tools carry no path. Anything the
# model needs to know about the schedule it reads out of this file.
SCHEDULE_FILENAME = "schedule.yaml"
MAX_VIEW_CHARS = 12_000
DEFAULT_EDIT_BUDGET = 5

VIEW_TOOL = "view_schedule"
EDIT_TOOL = "edit_schedule"
WRITE_TOOL = "write_schedule"

_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class ScheduleProposal:
    """A validated schedule the user can approve, with what it changes."""

    text: str
    diff: ScheduleDiff


class ScheduleEditor:
    """The schedule one run edits, with its failed-edit budget.

    The working text starts as the schedule the browser sent and advances only
    when an edit produces a valid schedule, so a rejected edit never leaves a
    broken document behind and the pending proposal is always applicable.
    """

    def __init__(
        self,
        base_text: str,
        max_bytes: int,
        edit_budget: int = DEFAULT_EDIT_BUDGET,
        allow_edit: bool = True,
    ) -> None:
        self.base_text = base_text
        self.current_text = base_text
        self.max_bytes = max_bytes
        self.allow_edit = allow_edit
        self.edit_budget = edit_budget
        self.failed_edits = 0
        self.proposal: ScheduleProposal | None = None

    @property
    def edits_left(self) -> int:
        """Report how many further failed edits are allowed."""
        return max(0, self.edit_budget - self.failed_edits)


def tool_definitions(editor: ScheduleEditor) -> list[dict[str, Any]]:
    """Describe the editor tools this run may call, in OpenAI-compatible form."""
    definitions = [
        _function(
            VIEW_TOOL,
            f"Read {SCHEDULE_FILENAME}, the schedule the user is working on, with line numbers. "
            "Omit the range to read the whole file.",
            {
                "type": "object",
                "properties": {
                    "start_line": {"type": "integer", "minimum": 1},
                    "end_line": {"type": "integer", "minimum": 1},
                },
                "additionalProperties": False,
            },
        )
    ]
    if not editor.allow_edit:
        return definitions
    return [
        *definitions,
        _function(
            EDIT_TOOL,
            f"Replace one exact block of text in {SCHEDULE_FILENAME}. `old_str` must appear exactly once, "
            "so include surrounding lines when a short string would be ambiguous. The result is validated, "
            "and a valid result becomes the proposal the user can approve.",
            {
                "type": "object",
                "properties": {"old_str": {"type": "string"}, "new_str": {"type": "string"}},
                "required": ["old_str", "new_str"],
                "additionalProperties": False,
            },
        ),
        _function(
            WRITE_TOOL,
            f"Replace the whole of {SCHEDULE_FILENAME}. Prefer {EDIT_TOOL} for small changes, "
            "because rewriting the whole schedule risks dropping entries.",
            {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
                "additionalProperties": False,
            },
        ),
    ]


def execute_tool(editor: ScheduleEditor, name: str, arguments: str) -> str:
    """Run one editor tool call and return bounded text for the model.

    Every failure is reported as text rather than raised, because the model has
    to read the problem and try again.
    """
    handler = _HANDLERS.get(name)
    if handler is None or (name != VIEW_TOOL and not editor.allow_edit):
        available = ", ".join(definition["function"]["name"] for definition in tool_definitions(editor))
        return f"Unknown tool `{name}`. Available tools: {available}."
    try:
        parsed = json.loads(arguments) if arguments.strip() else {}
    except json.JSONDecodeError as error:
        return f"The arguments for `{name}` were not valid JSON. {error}"
    if not isinstance(parsed, dict):
        return f"The arguments for `{name}` must be a JSON object."
    return handler(editor, parsed)


def _view(editor: ScheduleEditor, arguments: dict[str, Any]) -> str:
    """Return the working schedule, or one line range of it, with line numbers."""
    lines = editor.current_text.splitlines()
    start = _read_line(arguments, "start_line", 1)
    if isinstance(start, str):
        return start
    end = _read_line(arguments, "end_line", len(lines))
    if isinstance(end, str):
        return end
    if start > len(lines):
        return f"{SCHEDULE_FILENAME} has {len(lines)} lines, so line {start} is past the end."
    if end < start:
        return "`end_line` must not be before `start_line`."

    numbered = "\n".join(f"{number}\t{lines[number - 1]}" for number in range(start, min(end, len(lines)) + 1))
    header = f"{SCHEDULE_FILENAME} lines {start} to {min(end, len(lines))} of {len(lines)}:"
    if len(numbered) > MAX_VIEW_CHARS:
        numbered = numbered[:MAX_VIEW_CHARS] + "\n... truncated, request a smaller line range."
    return f"{header}\n{numbered}"


def _edit(editor: ScheduleEditor, arguments: dict[str, Any]) -> str:
    """Replace one unique block of text and validate the result."""
    old_str = arguments.get("old_str")
    new_str = arguments.get("new_str")
    if not isinstance(old_str, str) or not isinstance(new_str, str):
        return "`old_str` and `new_str` are required and must be strings."
    if not old_str:
        return f"`old_str` must not be empty. Use {WRITE_TOOL} to replace the whole file."
    if editor.edits_left == 0:
        return _exhausted(editor)

    occurrences = editor.current_text.count(old_str)
    if occurrences == 0:
        editor.failed_edits += 1
        hint = _near_match_hint(editor.current_text, old_str)
        return f"`old_str` was not found in {SCHEDULE_FILENAME}.{hint} {_budget_note(editor)}"
    if occurrences > 1:
        editor.failed_edits += 1
        return (
            f"`old_str` appears {occurrences} times in {SCHEDULE_FILENAME}. "
            f"Include surrounding lines so it matches once. {_budget_note(editor)}"
        )
    return _commit(editor, editor.current_text.replace(old_str, new_str, 1))


def _write(editor: ScheduleEditor, arguments: dict[str, Any]) -> str:
    """Replace the whole working schedule and validate the result."""
    text = arguments.get("text")
    if not isinstance(text, str):
        return "`text` is required and must be a string."
    if editor.edits_left == 0:
        return _exhausted(editor)
    return _commit(editor, text)


def _commit(editor: ScheduleEditor, candidate: str) -> str:
    """Validate one candidate schedule and keep it only when it is usable."""
    if candidate == editor.current_text:
        editor.failed_edits += 1
        return f"The edit leaves {SCHEDULE_FILENAME} unchanged. {_budget_note(editor)}"
    validation = validate_frontend_schedule_yaml(candidate, editor.max_bytes)
    if not validation.valid:
        editor.failed_edits += 1
        return (
            f"{SCHEDULE_FILENAME} was not changed, because the result is invalid.\n"
            f"{validation.render()}\n{_budget_note(editor)}"
        )

    diff = _diff_against_base(editor, candidate)
    if isinstance(diff, str):
        editor.failed_edits += 1
        return diff
    editor.current_text = candidate
    editor.proposal = ScheduleProposal(text=candidate, diff=diff)
    return f"{SCHEDULE_FILENAME} is valid. Changes so far:\n{diff.render()}"


def _diff_against_base(editor: ScheduleEditor, candidate: str) -> ScheduleDiff | str:
    """Compare the candidate with the schedule the browser sent."""
    try:
        base = _load_yaml(editor.base_text.encode("utf-8"))
        after = _load_yaml(candidate.encode("utf-8"))
    except (YAMLError, TypeError, ValueError) as error:
        return f"The schedule could not be compared. {error}"
    return diff_schedules(base, after)


def _near_match_hint(text: str, old_str: str) -> str:
    """Name whitespace as the cause when that is the only difference."""
    normalized = _WHITESPACE.sub(" ", old_str).strip()
    if not normalized or _WHITESPACE.sub(" ", text).count(normalized) != 1:
        return ""
    return f" A block matching except for whitespace exists, so copy it from {VIEW_TOOL} exactly."


def _budget_note(editor: ScheduleEditor) -> str:
    """State how many further attempts remain after a failed edit."""
    if editor.edits_left == 0:
        return "No further edits are allowed. Explain the problem to the user."
    return f"Remaining edit attempts: {editor.edits_left}."


def _exhausted(editor: ScheduleEditor) -> str:
    """Refuse further edits once the budget is gone."""
    return (
        f"The budget of {editor.edit_budget} failed edits is exhausted. "
        "Explain the problem to the user instead of editing again."
    )


def _read_line(arguments: dict[str, Any], name: str, default: int) -> int | str:
    """Read one line number argument, or describe why it is unusable."""
    value = arguments.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        return f"The `{name}` argument must be an integer."
    if value < 1:
        return f"The `{name}` argument must be at least 1."
    return value


def _function(name: str, description: str, parameters: dict[str, Any]) -> dict[str, Any]:
    """Wrap one tool in the OpenAI-compatible function shape."""
    return {"type": "function", "function": {"name": name, "description": description, "parameters": parameters}}


_HANDLERS: dict[str, Callable[[ScheduleEditor, dict[str, Any]], str]] = {
    VIEW_TOOL: _view,
    EDIT_TOOL: _edit,
    WRITE_TOOL: _write,
}

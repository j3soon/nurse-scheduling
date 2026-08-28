"""Tests for the single-file schedule editor in the AI service."""

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

from nurse_scheduling.ai.editor import (
    EDIT_TOOL,
    VIEW_TOOL,
    WRITE_TOOL,
    ScheduleEditor,
    describe_schedule,
    execute_tool,
    tool_definitions,
)

from .ai_test_helper import SCHEDULE_BYTE_LIMIT, base_schedule_payload, parse_schedule, schedule_yaml


def _editor(payload: dict | None = None, **kwargs) -> ScheduleEditor:
    return ScheduleEditor(schedule_yaml(payload), SCHEDULE_BYTE_LIMIT, **kwargs)


def _view(editor: ScheduleEditor, **arguments) -> str:
    return execute_tool(editor, VIEW_TOOL, json.dumps(arguments))


def _edit(editor: ScheduleEditor, old_str: str, new_str: str) -> str:
    return execute_tool(editor, EDIT_TOOL, json.dumps({"old_str": old_str, "new_str": new_str}))


def _write(editor: ScheduleEditor, text: str) -> str:
    return execute_tool(editor, WRITE_TOOL, json.dumps({"text": text}))


def test_view_returns_the_whole_file_with_line_numbers():
    editor = _editor()

    result = _view(editor)

    assert result.startswith("schedule.yaml lines 1 to ")
    assert "\n1\tappVersion: v0.0.0-test" in result


def test_view_returns_one_line_range():
    editor = _editor()

    result = _view(editor, start_line=2, end_line=3)

    assert "2\tapiVersion: alpha" in result
    assert "1\tappVersion" not in result


def test_view_reports_a_range_past_the_end():
    editor = _editor()

    assert "is past the end." in _view(editor, start_line=9_999)
    assert _view(editor, start_line=5, end_line=2) == "`end_line` must not be before `start_line`."


def test_edit_applies_a_unique_replacement_and_records_the_proposal():
    editor = _editor()

    result = _edit(editor, "  - id: P1\n    description: ''", "  - id: P1\n    description: Head nurse")

    assert result.startswith("schedule.yaml is valid.")
    assert "people.items[0].description" in result
    assert editor.proposal is not None
    assert parse_schedule(editor.current_text)["people"]["items"][0]["description"] == "Head nurse"
    assert editor.edits_left == editor.edit_budget


def test_edits_accumulate_against_the_schedule_the_browser_sent():
    editor = _editor()

    _edit(editor, "  - id: P1\n    description: ''", "  - id: P1\n    description: Head nurse")
    result = _edit(editor, "  - id: P2\n    description: ''", "  - id: P2\n    description: Night nurse")

    assert "people.items[0].description" in result
    assert "people.items[1].description" in result
    assert editor.proposal is not None
    assert editor.proposal.text == editor.current_text


def test_edit_reports_a_missing_match_and_spends_one_attempt():
    editor = _editor()

    result = _edit(editor, "id: P9", "id: P10")

    assert result.startswith("`old_str` was not found in schedule.yaml.")
    assert "Remaining edit attempts: 4." in result
    assert editor.current_text == editor.base_text


def test_edit_names_whitespace_when_that_is_the_only_difference():
    editor = _editor()

    result = _edit(editor, "- id:    P1", "- id: P3")

    assert "matching except for whitespace" in result
    assert editor.current_text == editor.base_text


def test_edit_reports_an_ambiguous_match_without_changing_anything():
    editor = _editor()

    result = _edit(editor, "description: ''", "description: Ward")

    occurrences = schedule_yaml().count("description: ''")
    assert f"appears {occurrences} times in schedule.yaml." in result
    assert editor.current_text == editor.base_text


def test_edit_that_breaks_the_schedule_is_not_applied():
    editor = _editor()

    result = _edit(editor, "  - id: P1\n", "  - id: []\n")

    assert result.startswith("schedule.yaml was not changed, because the edit introduces problems.")
    assert "people.items[0].id" in result
    assert editor.current_text == editor.base_text
    assert editor.proposal is None


def test_an_edit_that_changes_nothing_is_rejected():
    editor = _editor()

    result = _edit(editor, "apiVersion: alpha", "apiVersion: alpha")

    assert result.startswith("The edit leaves schedule.yaml unchanged.")
    assert editor.edits_left == editor.edit_budget - 1


def test_write_replaces_the_whole_schedule():
    editor = _editor()
    payload = base_schedule_payload()
    payload["description"] = "Ward A"

    result = _write(editor, schedule_yaml(payload))

    assert result.startswith("schedule.yaml is valid.")
    assert editor.proposal is not None
    assert parse_schedule(editor.current_text)["description"] == "Ward A"


def test_a_dropped_person_stays_visible_in_the_diff():
    editor = _editor()
    payload = base_schedule_payload()
    del payload["people"]["items"][1]
    payload["people"]["groups"][0]["members"] = ["P1"]

    result = _write(editor, schedule_yaml(payload))

    # Removing a person leaves a valid schedule, so review depends on the diff.
    assert result.startswith("schedule.yaml is valid.")
    assert "people.items[1]: removed" in result
    assert "P2" in result


def test_the_edit_budget_stops_further_edits():
    editor = _editor(edit_budget=1)

    _edit(editor, "id: P9", "id: P10")
    result = _edit(editor, "  - id: P1\n    description: ''", "  - id: P1\n    description: Head nurse")

    assert "budget of 1 failed edits is exhausted" in result
    assert editor.proposal is None


def test_read_only_runs_only_receive_the_view_tool():
    editor = _editor(allow_edit=False)

    names = [definition["function"]["name"] for definition in tool_definitions(editor)]

    assert names == [VIEW_TOOL]
    assert _edit(editor, "apiVersion: alpha", "apiVersion: beta").startswith(f"Unknown tool `{EDIT_TOOL}`.")
    assert _write(editor, "x").startswith(f"Unknown tool `{WRITE_TOOL}`.")
    assert _view(editor).startswith("schedule.yaml lines 1 to ")


def test_editing_runs_receive_three_tools():
    names = [definition["function"]["name"] for definition in tool_definitions(_editor())]

    assert names == [VIEW_TOOL, EDIT_TOOL, WRITE_TOOL]


def test_unknown_tools_and_unusable_arguments_are_reported_as_text():
    editor = _editor()

    assert execute_tool(editor, "bash", "{}").startswith("Unknown tool `bash`.")
    assert execute_tool(editor, VIEW_TOOL, "not json").startswith(f"The arguments for `{VIEW_TOOL}` were not")
    assert execute_tool(editor, VIEW_TOOL, "[]") == f"The arguments for `{VIEW_TOOL}` must be a JSON object."
    assert execute_tool(editor, EDIT_TOOL, "{}") == "`old_str` and `new_str` are required and must be strings."
    assert execute_tool(editor, WRITE_TOOL, "{}") == "`text` is required and must be a string."
    assert "must not be empty" in _edit(editor, "", "x")


def test_an_edit_is_judged_by_the_problems_it_introduces():
    payload = base_schedule_payload()
    # A user part way through building a schedule has not added this preference yet.
    payload["preferences"] = []
    editor = _editor(payload)

    result = _edit(editor, "  - id: P1\n    description: ''", "  - id: P1\n    description: Head")

    assert result.startswith("schedule.yaml still has problems that were already there")
    assert "at most one shift per day" in result
    assert editor.proposal is not None
    assert parse_schedule(editor.current_text)["people"]["items"][0]["description"] == "Head"


def test_an_edit_that_adds_a_problem_is_still_refused_on_an_invalid_schedule():
    payload = base_schedule_payload()
    payload["preferences"] = []
    editor = _editor(payload)

    result = _edit(editor, "  - id: P1\n", "  - id: []\n")

    assert result.startswith("schedule.yaml was not changed, because the edit introduces problems.")
    assert "at most one shift per day" not in result
    assert editor.proposal is None


def test_describe_schedule_reports_shape_without_contents():
    payload = base_schedule_payload()
    payload["people"]["groups"] = [{"id": f"G{index}", "description": "", "members": []} for index in range(25)]

    summary = describe_schedule(schedule_yaml(payload))

    assert "2 people, 2 shift types, 2 preferences" in summary
    assert "Dates run from 2026-01-01 to 2026-01-02" in summary
    assert "and 5 more" in summary
    assert "P1" not in summary


def test_describe_schedule_reports_a_file_that_does_not_parse():
    assert describe_schedule("people: [unclosed\n") == "schedule.yaml is 1 lines and does not currently parse."

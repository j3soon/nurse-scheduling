"""Tests for the bounded provider and tool loop in the AI service."""

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

import asyncio
import json
from collections.abc import AsyncIterator, Sequence

import pytest

from nurse_scheduling.ai.agent import AgentProposal, AgentReasoning, AgentText, AgentToolUse, run_agent
from nurse_scheduling.ai.editor import EDIT_TOOL, FIND_TOOL, VIEW_TOOL, ScheduleEditor
from nurse_scheduling.ai.provider import (
    ChatMessage,
    ProviderError,
    ReasoningDelta,
    TextDelta,
    ToolCall,
    ToolCallRequest,
)

from .ai_test_helper import SCHEDULE_BYTE_LIMIT, schedule_yaml

QUESTION: list[ChatMessage] = [{"role": "user", "content": "Who works on the first day?"}]
RENAME = json.dumps({"old_str": "  - id: P1\n    description: ''", "new_str": "  - id: P1\n    description: Head"})


class FakeProvider:
    """Replay scripted turns and record what each request offered."""

    def __init__(self, *turns) -> None:
        self._turns = list(turns)
        self.requests: list[tuple[list[ChatMessage], object]] = []

    async def stream_events(self, messages: Sequence[ChatMessage], tools=None) -> AsyncIterator:
        self.requests.append((list(messages), tools))
        turn = self._turns[min(len(self.requests) - 1, len(self._turns) - 1)]
        if isinstance(turn, Exception):
            raise turn
        for event in turn:
            yield event


def _text(*chunks: str) -> list:
    return [TextDelta(chunk) for chunk in chunks]


def _calls(*calls: tuple[str, str]) -> list:
    return [ToolCallRequest(tuple(ToolCall(f"call_{index}", name, args) for index, (name, args) in enumerate(calls)))]


def _editor(**kwargs) -> ScheduleEditor:
    return ScheduleEditor(schedule_yaml(), SCHEDULE_BYTE_LIMIT, **kwargs)


def _run(provider: FakeProvider, editor: ScheduleEditor, max_tool_calls: int = 4) -> list:
    async def collect() -> list:
        return [event async for event in run_agent(provider, editor, QUESTION, max_tool_calls)]

    return asyncio.run(collect())


def test_a_question_only_run_streams_text_and_proposes_nothing():
    provider = FakeProvider(_text("P1 ", "works."))
    editor = _editor()

    events = _run(provider, editor)

    assert events == [AgentText("P1 "), AgentText("works.")]
    assert editor.proposal is None
    assert len(provider.requests) == 1


def test_a_tool_call_is_executed_and_returned_to_the_provider():
    provider = FakeProvider(_calls((VIEW_TOOL, "{}")), _text("Two people."))
    editor = _editor()

    events = _run(provider, editor)

    assert isinstance(events[0], AgentToolUse)
    assert events[0].name == VIEW_TOOL
    assert events[0].ok
    assert events[0].arguments == "{}"
    assert events[0].result.startswith("schedule.yaml lines 1 to ")
    second_request = provider.requests[1][0]
    assert second_request[-2]["tool_calls"][0]["function"]["name"] == VIEW_TOOL
    assert second_request[-1] == {"role": "tool", "tool_call_id": "call_0", "content": events[0].result}


def test_an_edit_run_ends_with_a_proposal():
    provider = FakeProvider(_calls((EDIT_TOOL, RENAME)), _text("Renamed P1."))
    editor = _editor()

    events = _run(provider, editor)

    assert isinstance(events[-1], AgentProposal)
    assert "people.items[0].description" in events[-1].diff
    assert "description: Head" in events[-1].text
    assert editor.proposal is not None


def test_text_sent_alongside_a_tool_call_is_kept_in_the_conversation():
    provider = FakeProvider([TextDelta("Checking. "), *_calls((VIEW_TOOL, "{}"))], _text("Done."))
    editor = _editor()

    _run(provider, editor)

    assert provider.requests[1][0][-2]["content"] == "Checking. "


def test_parallel_tool_calls_each_receive_a_result():
    provider = FakeProvider(_calls((VIEW_TOOL, "{}"), (VIEW_TOOL, '{"start_line": 1, "end_line": 1}')), _text("Done."))
    editor = _editor()

    events = _run(provider, editor)

    assert [event.name for event in events if isinstance(event, AgentToolUse)] == [VIEW_TOOL, VIEW_TOOL]
    results = [message for message in provider.requests[1][0] if message.get("role") == "tool"]
    assert [message["tool_call_id"] for message in results] == ["call_0", "call_1"]


def test_an_excess_tool_call_gets_an_error_before_tool_free_finalization():
    provider = FakeProvider(_calls((VIEW_TOOL, "{}")), _calls((VIEW_TOOL, "{}")), _text("I need more input."))
    editor = _editor()

    events = _run(provider, editor, max_tool_calls=1)

    assert len(provider.requests) == 3
    assert [tools is None for _, tools in provider.requests] == [False, False, True]
    tool_events = [event for event in events if isinstance(event, AgentToolUse)]
    assert tool_events[0].ok
    assert not tool_events[1].ok
    assert tool_events[0].executed
    assert not tool_events[1].executed
    assert "1 of 1 calls have already been executed" in tool_events[1].result
    assert provider.requests[2][0][-1] == {
        "role": "tool",
        "tool_call_id": "call_0",
        "content": tool_events[1].result,
    }
    assert events[-1] == AgentText("I need more input.")


def test_parallel_calls_past_the_budget_are_rejected_without_execution():
    provider = FakeProvider(
        _calls((VIEW_TOOL, "{}"), (VIEW_TOOL, '{"start_line": 1, "end_line": 1}')),
        _text("Done."),
    )
    editor = _editor()

    events = _run(provider, editor, max_tool_calls=1)

    tool_events = [event for event in events if isinstance(event, AgentToolUse)]
    assert [event.ok for event in tool_events] == [True, False]
    assert [event.executed for event in tool_events] == [True, False]
    assert tool_events[0].result.startswith("schedule.yaml lines 1 to ")
    assert "This call was not executed" in tool_events[1].result
    assert [tools is None for _, tools in provider.requests] == [False, True]


def test_raw_tool_markup_in_budget_finalization_is_not_shown():
    provider = FakeProvider(
        _calls((VIEW_TOOL, "{}")),
        _text("I still need the schedule.\n\n<tool_call>view_schedule</tool_call>"),
    )
    editor = _editor()

    events = _run(provider, editor, max_tool_calls=0)

    answer = "".join(event.text for event in events if isinstance(event, AgentText))
    assert "<tool_call>" not in answer
    assert answer.startswith("I still need the schedule.")
    assert "within the available tool-call budget" in answer


def test_a_tool_call_during_budget_finalization_stops_without_another_turn():
    provider = FakeProvider(_calls((VIEW_TOOL, "{}")), _calls((VIEW_TOOL, "{}")))

    events = _run(provider, _editor(), max_tool_calls=0)

    answer = "".join(event.text for event in events if isinstance(event, AgentText))
    assert len(provider.requests) == 2
    assert [tools is None for _, tools in provider.requests] == [False, True]
    assert answer == (
        "I could not complete this request within the available tool-call budget. "
        "Please ask me to continue or narrow the request."
    )


def test_a_negative_tool_budget_is_rejected():
    provider = FakeProvider(_text("Unused."))

    with pytest.raises(ValueError, match="max_tool_calls must be non-negative"):
        _run(provider, _editor(), max_tool_calls=-1)

    assert provider.requests == []


def test_a_failed_run_leaves_no_proposal():
    provider = FakeProvider(_calls((EDIT_TOOL, RENAME)), ProviderError("The AI provider is unavailable."))
    editor = _editor()

    with pytest.raises(ProviderError):
        _run(provider, editor)

    assert editor.proposal is None


def test_an_abandoned_run_leaves_no_proposal():
    provider = FakeProvider(_calls((EDIT_TOOL, RENAME)), _text("Renamed P1."))
    editor = _editor()

    async def abandon() -> None:
        stream = run_agent(provider, editor, QUESTION, 4)
        async for event in stream:
            if isinstance(event, AgentToolUse):
                break
        await stream.aclose()

    asyncio.run(abandon())

    assert editor.proposal is None


def test_a_read_only_run_is_offered_both_read_tools():
    provider = FakeProvider(_text("Two people."))
    editor = _editor(allow_edit=False)

    _run(provider, editor)

    offered = [tool["function"]["name"] for tool in provider.requests[0][1]]
    assert offered == [VIEW_TOOL, FIND_TOOL]


def test_reasoning_is_reported_without_entering_the_answer():
    provider = FakeProvider([ReasoningDelta("Counting people. "), TextDelta("Two people.")])
    editor = _editor()

    events = _run(provider, editor)

    assert events == [AgentReasoning("Counting people. "), AgentText("Two people.")]


def test_a_failed_tool_call_is_reported_as_such():
    provider = FakeProvider(_calls((EDIT_TOOL, json.dumps({"old_str": "missing", "new_str": "x"}))), _text("Sorry."))
    editor = _editor()

    events = _run(provider, editor)

    assert isinstance(events[0], AgentToolUse)
    assert not events[0].ok
    assert "was not found" in events[0].result

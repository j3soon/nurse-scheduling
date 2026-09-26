"""Tests for the provider and tool loop in the AI service."""

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
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from functools import partial

import pytest

from nurse_scheduling.ai.agent_loop import TRUNCATED_TOOL_CALL_RESULT, agent_loop
from nurse_scheduling.ai.agent_types import (
    AgentSteering,
    AgentTool,
    AgentToolResult,
    MessageEnd,
    MessageReasoningDelta,
    MessageTextDelta,
    ToolExecutionEnd,
    ToolExecutionStart,
)
from nurse_scheduling.ai.pi.bash import BASH_TOOL
from nurse_scheduling.ai.pi.read import READ_TOOL
from nurse_scheduling.ai.provider import (
    ChatMessage,
    ReasoningDelta,
    ResponseEnd,
    TextDelta,
    ToolCallRequest,
    ToolResultImage,
)
from nurse_scheduling.ai.transcript import AssistantMessage, ToolCall

QUESTION: list[ChatMessage] = [{"role": "user", "content": "Who works on the first day?"}]
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": BASH_TOOL,
            "description": "Run Bash.",
            "parameters": {"type": "object"},
        },
    }
]


def _tools(execute, read_only=frozenset(), *, include_read=False):
    definitions = list(TOOLS)
    if include_read:
        definitions.append({"type": "function", "function": {"name": READ_TOOL, "parameters": {"type": "object"}}})
    return [
        AgentTool(
            definition, partial(execute, definition["function"]["name"]), definition["function"]["name"] in read_only
        )
        for definition in definitions
    ]


class FakeProvider:
    """Replay scripted turns and record what each request offered."""

    def __init__(self, *turns) -> None:
        self._turns = list(turns)
        self.requests: list[tuple[list[ChatMessage], object]] = []

    async def stream_events(self, messages: Sequence[ChatMessage], tools=None) -> AsyncIterator:
        self.requests.append((list(messages), tools))
        turn = self._turns[min(len(self.requests) - 1, len(self._turns) - 1)]
        for event in turn:
            yield event


def _text(*chunks: str) -> list:
    return [TextDelta(chunk) for chunk in chunks]


def _calls(count: int = 1) -> list:
    calls = tuple(ToolCall(f"call_{index}", BASH_TOOL, '{"command":"rg people"}') for index in range(count))
    return [ToolCallRequest(calls)]


def _run(provider: FakeProvider, *, tool_ok: bool = True, message_ends: bool = False, **limits: int) -> list:
    """Collect loop events, leaving out per-response MessageEnd records unless requested."""

    async def execute(_name: str, _arguments: str) -> AgentToolResult:
        return AgentToolResult("command result", tool_ok)

    async def collect() -> list:
        return [
            event
            async for event in agent_loop(provider, QUESTION, _tools(execute), **limits)
            if message_ends or not isinstance(event, MessageEnd)
        ]

    return asyncio.run(collect())


def test_a_question_only_run_streams_text():
    provider = FakeProvider(_text("P1 ", "works."))

    assert _run(provider, message_ends=True) == [
        MessageTextDelta("P1 "),
        MessageTextDelta("works."),
        MessageEnd(AssistantMessage("P1 works.")),
    ]
    assert len(provider.requests) == 1


def test_a_tool_call_is_executed_and_returned_to_the_provider():
    provider = FakeProvider(_calls(), _text("Two people."))

    events = _run(provider)

    assert events[:2] == [
        ToolExecutionStart(BASH_TOOL, '{"command":"rg people"}', "call_0"),
        ToolExecutionEnd(BASH_TOOL, '{"command":"rg people"}', "command result", True, "call_0"),
    ]
    second_request = provider.requests[1][0]
    assert second_request[-2]["tool_calls"][0]["function"]["name"] == BASH_TOOL
    assert second_request[-1] == {
        "role": "tool",
        "tool_call_id": "call_0",
        "content": "command result",
    }


def test_an_image_tool_result_is_returned_as_multimodal_content():
    provider = FakeProvider(_calls(), _text("I inspected the image."))
    image = b"\x89PNG\r\n\x1a\nimage"

    async def execute(_name: str, _arguments: str) -> AgentToolResult:
        return AgentToolResult("Read image.", True, ToolResultImage("image/png", image))

    async def collect() -> None:
        async for _event in agent_loop(provider, QUESTION, _tools(execute)):
            pass

    asyncio.run(collect())

    assert provider.requests[1][0][-2] == {
        "role": "tool",
        "tool_call_id": "call_0",
        "content": "Read image.",
    }
    assert provider.requests[1][0][-1] == {
        "role": "user",
        "content": [
            {"type": "text", "text": "Image returned by tool call call_0."},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBORw0KGgppbWFnZQ=="}},
        ],
    }


def test_image_tool_results_follow_all_tool_replies():
    provider = FakeProvider(_calls(2), _text("Done."))

    async def execute(_name: str, _arguments: str) -> AgentToolResult:
        return AgentToolResult("Read image.", True, ToolResultImage("image/png", b"image"))

    async def collect() -> None:
        async for _event in agent_loop(provider, QUESTION, _tools(execute)):
            pass

    asyncio.run(collect())

    replies = provider.requests[1][0][-4:]
    assert [reply["role"] for reply in replies] == ["tool", "tool", "user", "user"]
    assert [reply["tool_call_id"] for reply in replies[:2]] == ["call_0", "call_1"]
    assert all(reply["content"][1]["type"] == "image_url" for reply in replies[2:])


def test_all_queued_steering_is_injected_after_the_next_tool_batch():
    provider = FakeProvider(_calls(), _text("Steered answer."))
    queued = [
        ("message-2", "Focus on P2 instead."),
        ("message-3", "Also compare P3."),
    ]
    close_checks: list[bool] = []

    async def execute(_name: str, _arguments: str) -> AgentToolResult:
        return AgentToolResult("command result", True)

    def take_steering(close_if_empty: bool) -> list[tuple[str, str]]:
        close_checks.append(close_if_empty)
        messages = list(queued)
        queued.clear()
        return messages

    async def collect() -> list:
        return [event async for event in agent_loop(provider, QUESTION, _tools(execute), take_steering=take_steering)]

    events = asyncio.run(collect())

    assert AgentSteering("message-2", "Focus on P2 instead.") in events
    assert AgentSteering("message-3", "Also compare P3.") in events
    assert provider.requests[1][0][-2:] == [
        {"role": "user", "content": "Focus on P2 instead."},
        {"role": "user", "content": "Also compare P3."},
    ]
    assert close_checks == [False, True]


def test_text_sent_alongside_a_tool_call_is_kept_in_the_conversation():
    provider = FakeProvider([TextDelta("Checking. "), *_calls()], _text("Done."))

    _run(provider)

    assert provider.requests[1][0][-2]["content"] == "Checking. "


def test_parallel_tool_calls_each_receive_a_result():
    provider = FakeProvider(_calls(2), _text("Done."))

    events = _run(provider)

    assert [event.name for event in events if isinstance(event, ToolExecutionEnd)] == [BASH_TOOL, BASH_TOOL]
    results = [message for message in provider.requests[1][0] if message.get("role") == "tool"]
    assert [message["tool_call_id"] for message in results] == ["call_0", "call_1"]


def test_allowed_tool_batch_executes_concurrently_and_reports_in_call_order():
    calls = (
        ToolCall("call_0", BASH_TOOL, '{"command":"first"}'),
        ToolCall("call_1", BASH_TOOL, '{"command":"second"}'),
    )
    provider = FakeProvider([ToolCallRequest(calls)], _text("Done."))
    active = 0
    max_active = 0
    both_started = asyncio.Event()

    async def execute(_name: str, arguments: str) -> AgentToolResult:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        if active == 2:
            both_started.set()
        await both_started.wait()
        active -= 1
        return AgentToolResult(arguments, True)

    async def collect() -> list:
        return [event async for event in agent_loop(provider, QUESTION, _tools(execute, frozenset({BASH_TOOL})))]

    events = asyncio.run(collect())
    uses = [event for event in events if isinstance(event, ToolExecutionEnd)]

    assert max_active == 2
    assert [event.result for event in uses] == ['{"command":"first"}', '{"command":"second"}']
    assert isinstance(events[0], MessageEnd)
    assert all(isinstance(event, ToolExecutionStart) for event in events[1:3])


def test_parallel_tool_failure_cancels_siblings_without_wrapping_the_error():
    calls = (
        ToolCall("call_0", BASH_TOOL, '{"command":"fail"}'),
        ToolCall("call_1", BASH_TOOL, '{"command":"wait"}'),
    )
    provider = FakeProvider([ToolCallRequest(calls)])
    sibling_started = asyncio.Event()
    sibling_cancelled = asyncio.Event()

    async def execute(_name: str, arguments: str) -> AgentToolResult:
        if "fail" in arguments:
            await sibling_started.wait()
            raise ValueError("tool failed")
        sibling_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            sibling_cancelled.set()
            raise

    async def collect() -> None:
        async for _event in agent_loop(provider, QUESTION, _tools(execute, frozenset({BASH_TOOL}))):
            pass

    with pytest.raises(ValueError, match="tool failed"):
        asyncio.run(collect())
    assert sibling_cancelled.is_set()


def test_mixed_tool_batch_remains_sequential():
    calls = (
        ToolCall("call_0", READ_TOOL, '{"path":"schedule.yaml"}'),
        ToolCall("call_1", BASH_TOOL, '{"command":"rg people"}'),
    )
    provider = FakeProvider([ToolCallRequest(calls)], _text("Done."))
    active = 0
    max_active = 0

    async def execute(_name: str, _arguments: str) -> AgentToolResult:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return AgentToolResult("result", True)

    async def collect() -> None:
        async for _event in agent_loop(provider, QUESTION, _tools(execute, frozenset({READ_TOOL}), include_read=True)):
            pass

    asyncio.run(collect())

    assert max_active == 1


def test_one_activity_batch_contains_all_calls_from_a_model_response():
    provider = FakeProvider(_calls(2), _text("Done."))
    activity: list[str] = []
    executed = 0

    @asynccontextmanager
    async def activity_batch():
        activity.append("enter")
        try:
            yield
        finally:
            activity.append("exit")

    async def execute(_name: str, _arguments: str) -> AgentToolResult:
        nonlocal executed
        assert activity == ["enter"]
        executed += 1
        return AgentToolResult("command result", True)

    async def collect() -> None:
        async for _event in agent_loop(provider, QUESTION, _tools(execute), activity_batch=activity_batch):
            pass

    asyncio.run(collect())

    assert activity == ["enter", "exit"]
    assert executed == 2


def test_tool_calls_continue_until_the_model_finishes():
    provider = FakeProvider(*[_calls() for _ in range(6)], _text("Done."))

    events = _run(provider)

    assert len([event for event in events if isinstance(event, ToolExecutionEnd)]) == 6
    assert len(provider.requests) == 7
    assert events[-1] == MessageTextDelta("Done.")


def test_tool_round_budget_returns_one_final_answer_without_executing_more_calls():
    provider = FakeProvider(_calls(), _calls(), _text("I could not finish."))

    events = _run(provider, max_tool_rounds=1, max_tool_calls=10)

    uses = [event for event in events if isinstance(event, ToolExecutionEnd)]
    assert [event.ok for event in uses] == [True, False]
    assert "budget is exhausted" in uses[-1].result
    assert provider.requests[-1][1] == []
    assert events[-1] == MessageTextDelta("I could not finish.")


def test_tool_call_budget_rejects_a_batch_that_would_partially_execute():
    provider = FakeProvider(_calls(2), _text("Please narrow the task."))

    events = _run(provider, max_tool_rounds=10, max_tool_calls=1)

    uses = [event for event in events if isinstance(event, ToolExecutionEnd)]
    assert len(uses) == 2
    assert all(not event.ok for event in uses)
    assert events[-1] == MessageTextDelta("Please narrow the task.")


def test_reasoning_is_reported_without_entering_the_answer():
    provider = FakeProvider([ReasoningDelta("Counting people. "), TextDelta("Two people.")])

    assert _run(provider) == [MessageReasoningDelta("Counting people. "), MessageTextDelta("Two people.")]


def test_a_failed_tool_call_is_reported_as_such():
    provider = FakeProvider(_calls(), _text("Sorry."))

    events = _run(provider, tool_ok=False)

    assert events[:2] == [
        ToolExecutionStart(BASH_TOOL, '{"command":"rg people"}', "call_0"),
        ToolExecutionEnd(BASH_TOOL, '{"command":"rg people"}', "command result", False, "call_0"),
    ]


def test_stateful_agent_tracks_tools_and_consumes_steering_at_the_boundary():
    from nurse_scheduling.ai.agent import Agent
    from nurse_scheduling.ai.agent_types import AgentTool

    async def scenario():
        agent = Agent()
        agent.open_steering(True)
        provider = FakeProvider(_calls(), _text("Finished."))

        async def execute(_arguments):
            assert agent.state.pending_tool_calls == {"call_0"}
            agent.steer("next", "Check the next day too.")
            agent.steer("next", "Duplicate delivery.")
            return AgentToolResult("result", True)

        events = []
        async for event in agent.prompt(provider, QUESTION, [AgentTool(TOOLS[0], execute)]):
            assert agent.state.is_streaming
            events.append(event)
        assert [event.text for event in events if isinstance(event, AgentSteering)] == ["Check the next day too."]
        assert provider.requests[1][0][-1] == {"role": "user", "content": "Check the next day too."}
        assert not agent.state.is_streaming
        assert not agent.state.pending_tool_calls
        assert not agent.accepting_steering

    asyncio.run(scenario())


def test_cancelling_the_agent_consumer_joins_tool_cleanup_and_resets_execution_state():
    from nurse_scheduling.ai.agent import Agent
    from nurse_scheduling.ai.agent_types import AgentTool

    async def scenario():
        agent = Agent()
        started = asyncio.Event()
        cleaned = asyncio.Event()

        async def execute(_arguments):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()

        async def consume():
            async for _event in agent.prompt(FakeProvider(_calls()), QUESTION, [AgentTool(TOOLS[0], execute)]):
                pass

        task = asyncio.create_task(consume())
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cleaned.is_set()
        assert not agent.state.is_streaming
        assert not agent.state.pending_tool_calls

    asyncio.run(scenario())


def test_closing_agent_stream_resets_state_before_another_prompt():
    from nurse_scheduling.ai.agent import Agent

    async def scenario():
        agent = Agent()
        events = agent.prompt(FakeProvider(_text("partial", "answer")), QUESTION, [])
        assert await anext(events) == MessageTextDelta("partial")
        concurrent = agent.prompt(FakeProvider(_text("conflict")), QUESTION, [])
        with pytest.raises(RuntimeError, match="already running"):
            await anext(concurrent)
        await events.aclose()
        assert not agent.state.is_streaming
        assert [event async for event in agent.prompt(FakeProvider(_text("new")), QUESTION, [])] == [
            MessageTextDelta("new"),
            MessageEnd(AssistantMessage("new")),
        ]

    asyncio.run(scenario())


def test_unknown_tool_returns_correlated_failure_without_executing_a_tool():
    provider = FakeProvider([ToolCallRequest((ToolCall("unknown-call", "missing", "{}"),))], _text("Recovered."))

    async def execute(_name, _arguments):
        pytest.fail("An unknown tool must not execute a registered tool")

    async def collect():
        return [event async for event in agent_loop(provider, QUESTION, _tools(execute))]

    events = asyncio.run(collect())
    result = next(event for event in events if isinstance(event, ToolExecutionEnd))
    assert result.tool_call_id == "unknown-call"
    assert not result.ok
    assert "Unknown tool `missing`" in result.result
    assert provider.requests[1][0][-1]["tool_call_id"] == "unknown-call"
    assert provider.requests[1][0][-1]["content"] == result.result
    assert events[-2:] == [MessageTextDelta("Recovered."), MessageEnd(AssistantMessage("Recovered."))]


def test_tool_calls_cut_off_by_the_output_limit_are_refused_and_reported_to_the_model():
    executed = []
    # The cut-off arguments still parse, so only the finish reason shows they are incomplete.
    truncated = ToolCall("call_0", BASH_TOOL, '{"command":"rm -r"}')
    provider = FakeProvider(
        [TextDelta("Cleaning up."), ToolCallRequest((truncated,)), ResponseEnd("length")],
        [*_calls(), ResponseEnd("tool_calls")],
        [*_text("Done."), ResponseEnd("stop")],
    )

    async def execute(_name: str, arguments: str) -> AgentToolResult:
        executed.append(arguments)
        return AgentToolResult("ok", True)

    async def collect() -> list:
        return [event async for event in agent_loop(provider, QUESTION, _tools(execute))]

    events = asyncio.run(collect())

    assert executed == ['{"command":"rg people"}']
    assert ToolExecutionEnd(BASH_TOOL, '{"command":"rm -r"}', TRUNCATED_TOOL_CALL_RESULT, False, "call_0") in events
    assert MessageEnd(AssistantMessage("Cleaning up.", "length", tool_calls=(truncated,))) in events
    replayed_call, refusal = provider.requests[1][0][-2:]
    assert replayed_call["tool_calls"][0]["function"]["arguments"] == "{}"
    assert refusal == {"role": "tool", "tool_call_id": "call_0", "content": TRUNCATED_TOOL_CALL_RESULT}


def test_repeated_tool_call_truncation_spends_the_round_budget():
    truncated = [ToolCallRequest((ToolCall("call_0", BASH_TOOL, '{"comm'),)), ResponseEnd("length")]
    provider = FakeProvider(truncated, truncated, [*_text("Stopping."), ResponseEnd("stop")])

    events = _run(provider, max_tool_rounds=2)

    assert len(provider.requests) == 3
    assert provider.requests[2][1] == []
    assert events[-1] == MessageTextDelta("Stopping.")


def test_an_answer_cut_off_by_the_output_limit_is_marked_truncated():
    provider = FakeProvider([*_text("The first half"), ResponseEnd("length")])

    assert _run(provider, message_ends=True) == [
        MessageTextDelta("The first half"),
        MessageEnd(AssistantMessage("The first half", "length")),
    ]


def test_each_request_is_prepared_from_the_unchanged_run_conversation():
    marker: ChatMessage = {"role": "system", "content": "Prepared."}
    seen: list[int] = []

    def prepare(conversation):
        seen.append(len(conversation))
        return [*conversation, marker]

    provider = FakeProvider(_calls(), _text("Done."))

    async def execute(_name: str, _arguments: str) -> AgentToolResult:
        return AgentToolResult("result", True)

    async def collect() -> list:
        return [event async for event in agent_loop(provider, QUESTION, _tools(execute), prepare_request=prepare)]

    asyncio.run(collect())

    assert seen == [1, 3]
    # A marker added for one request never becomes part of the next one's record.
    assert [request.count(marker) for request, _tools in provider.requests] == [1, 1]
    assert provider.requests[1][0][2]["role"] == "tool"

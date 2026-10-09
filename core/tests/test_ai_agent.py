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

import pytest

from nurse_scheduling.ai.agent import Agent
from nurse_scheduling.ai.agent_loop import agent_loop
from nurse_scheduling.ai.agent_types import (
    AgentMessageEnd,
    AgentReasoning,
    AgentSteering,
    AgentText,
    AgentToolOutcome,
    AgentToolStart,
    AgentToolUse,
)
from nurse_scheduling.ai.pi.bash import BASH_TOOL
from nurse_scheduling.ai.pi.read import READ_TOOL
from nurse_scheduling.ai.provider import (
    ChatMessage,
    ReasoningDelta,
    ResponseEnd,
    TextDelta,
    ToolCall,
    ToolCallRequest,
    ToolResultImage,
)
from nurse_scheduling.ai.transcript import AssistantMessage

from .ai_test_helper import bind_agent_tools

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


def _run(provider: FakeProvider, *, tool_ok: bool = True, **limits: int) -> list:
    async def execute(_name: str, _arguments: str) -> AgentToolOutcome:
        return AgentToolOutcome("command result", tool_ok)

    async def collect() -> list:
        return [
            event
            async for event in agent_loop(provider, QUESTION, bind_agent_tools(TOOLS, execute, frozenset()), **limits)
            if not isinstance(event, AgentMessageEnd)
        ]

    return asyncio.run(collect())


def test_a_question_only_run_streams_text():
    provider = FakeProvider(_text("P1 ", "works."))

    assert _run(provider) == [AgentText("P1 "), AgentText("works.")]
    assert len(provider.requests) == 1


def test_agent_closing_a_stream_releases_provider_before_reuse():
    async def exercise():
        closed = []

        class Provider:
            async def stream_events(self, _messages, tools=None):
                try:
                    yield TextDelta("First fragment")
                    await asyncio.Event().wait()
                finally:
                    closed.append(True)

        agent = Agent()
        first = agent.prompt(Provider(), QUESTION, [])
        assert await anext(first) == AgentText("First fragment")
        assert agent.state.is_streaming
        overlapping = agent.prompt(FakeProvider(_text("Overlapping")), QUESTION, [])
        with pytest.raises(RuntimeError, match="already running"):
            await anext(overlapping)
        assert agent.state.is_streaming
        await first.aclose()
        assert closed == [True]
        assert not agent.state.is_streaming
        assert [event async for event in agent.prompt(FakeProvider(_text("Next")), QUESTION, [])] == [
            AgentText("Next"),
            AgentMessageEnd(AssistantMessage("Next")),
        ]

    asyncio.run(exercise())


def test_agent_cancellation_joins_tool_cleanup_before_releasing_state():
    async def exercise():
        started, cleaning, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

        async def execute(_name, _arguments):
            try:
                started.set()
                await asyncio.Event().wait()
            finally:
                cleaning.set()
                await release.wait()

        agent = Agent()
        provider = FakeProvider(_calls(), _text("Done"))

        async def consume():
            async for _event in agent.prompt(provider, QUESTION, bind_agent_tools(TOOLS, execute)):
                pass

        running = asyncio.create_task(consume())
        await started.wait()
        assert agent.state.pending_tool_calls == {"call_0"}
        running.cancel()
        await cleaning.wait()
        assert agent.state.is_streaming and not running.done()
        release.set()
        await asyncio.gather(running, return_exceptions=True)
        assert not agent.state.is_streaming
        assert not agent.state.pending_tool_calls

    asyncio.run(exercise())


def test_unregistered_tool_never_reaches_an_executor():
    executed = []

    async def execute(name, _arguments):
        executed.append(name)
        return AgentToolOutcome("Executed", True)

    async def exercise():
        provider = FakeProvider([ToolCallRequest((ToolCall("missing", "unregistered", "{}"),))], _text("Done"))
        events = [event async for event in agent_loop(provider, QUESTION, bind_agent_tools(TOOLS, execute))]
        outcome = next(event for event in events if isinstance(event, AgentToolUse))
        assert not outcome.ok and outcome.tool_call_id == "missing"
        assert provider.requests[1][0][-1]["tool_call_id"] == "missing"

    asyncio.run(exercise())
    assert executed == []


def test_a_tool_call_is_executed_and_returned_to_the_provider():
    provider = FakeProvider(_calls(), _text("Two people."))

    events = _run(provider)

    assert events[:2] == [
        AgentToolStart(BASH_TOOL, '{"command":"rg people"}', "call_0"),
        AgentToolUse(BASH_TOOL, '{"command":"rg people"}', "command result", True, "call_0"),
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

    async def execute(_name: str, _arguments: str) -> AgentToolOutcome:
        return AgentToolOutcome("Read image.", True, ToolResultImage("image/png", image))

    async def collect() -> None:
        async for _event in agent_loop(provider, QUESTION, bind_agent_tools(TOOLS, execute, frozenset())):
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

    async def execute(_name: str, _arguments: str) -> AgentToolOutcome:
        return AgentToolOutcome("Read image.", True, ToolResultImage("image/png", b"image"))

    async def collect() -> None:
        async for _event in agent_loop(provider, QUESTION, bind_agent_tools(TOOLS, execute, frozenset())):
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

    async def execute(_name: str, _arguments: str) -> AgentToolOutcome:
        return AgentToolOutcome("command result", True)

    def take_steering(close_if_empty: bool) -> list[tuple[str, str]]:
        close_checks.append(close_if_empty)
        messages = list(queued)
        queued.clear()
        return messages

    async def collect() -> list:
        return [
            event
            async for event in agent_loop(
                provider, QUESTION, bind_agent_tools(TOOLS, execute, frozenset()), take_steering=take_steering
            )
        ]

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

    assert [event.name for event in events if isinstance(event, AgentToolUse)] == [BASH_TOOL, BASH_TOOL]
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

    async def execute(_name: str, arguments: str) -> AgentToolOutcome:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        if active == 2:
            both_started.set()
        await both_started.wait()
        active -= 1
        return AgentToolOutcome(arguments, True)

    async def collect() -> list:
        return [
            event
            async for event in agent_loop(provider, QUESTION, bind_agent_tools(TOOLS, execute, frozenset({BASH_TOOL})))
        ]

    events = asyncio.run(collect())
    uses = [event for event in events if isinstance(event, AgentToolUse)]

    assert max_active == 2
    assert [event.result for event in uses] == ['{"command":"first"}', '{"command":"second"}']
    assert all(isinstance(event, AgentToolStart) for event in events[1:3])


def test_parallel_tool_failure_cancels_siblings_without_wrapping_the_error():
    calls = (
        ToolCall("call_0", BASH_TOOL, '{"command":"fail"}'),
        ToolCall("call_1", BASH_TOOL, '{"command":"wait"}'),
    )
    provider = FakeProvider([ToolCallRequest(calls)])
    sibling_started = asyncio.Event()
    sibling_cancelled = asyncio.Event()

    async def execute(_name: str, arguments: str) -> AgentToolOutcome:
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
        async for _event in agent_loop(provider, QUESTION, bind_agent_tools(TOOLS, execute, frozenset({BASH_TOOL}))):
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
    executed = []

    async def execute(_name: str, _arguments: str) -> AgentToolOutcome:
        nonlocal active, max_active
        executed.append(_name)
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return AgentToolOutcome("result", True)

    async def collect() -> None:
        async for _event in agent_loop(
            provider,
            QUESTION,
            bind_agent_tools(
                [*TOOLS, {"type": "function", "function": {"name": READ_TOOL}}], execute, frozenset({READ_TOOL})
            ),
        ):
            pass

    asyncio.run(collect())

    assert max_active == 1
    assert executed == [READ_TOOL, BASH_TOOL]


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

    async def execute(_name: str, _arguments: str) -> AgentToolOutcome:
        nonlocal executed
        assert activity == ["enter"]
        executed += 1
        return AgentToolOutcome("command result", True)

    async def collect() -> None:
        async for _event in agent_loop(
            provider, QUESTION, bind_agent_tools(TOOLS, execute, frozenset()), activity_batch
        ):
            pass

    asyncio.run(collect())

    assert activity == ["enter", "exit"]
    assert executed == 2


def test_tool_calls_continue_until_the_model_finishes():
    provider = FakeProvider(*[_calls() for _ in range(6)], _text("Done."))

    events = _run(provider)

    assert len([event for event in events if isinstance(event, AgentToolUse)]) == 6
    assert len(provider.requests) == 7
    assert events[-1] == AgentText("Done.")


def test_tool_round_budget_returns_one_final_answer_without_executing_more_calls():
    provider = FakeProvider(_calls(), _calls(), _text("I could not finish."))

    events = _run(provider, max_tool_rounds=1, max_tool_calls=10)

    uses = [event for event in events if isinstance(event, AgentToolUse)]
    assert [event.ok for event in uses] == [True, False]
    assert "budget is exhausted" in uses[-1].result
    assert provider.requests[-1][1] == []
    assert events[-1] == AgentText("I could not finish.")


def test_tool_call_budget_rejects_a_batch_that_would_partially_execute():
    provider = FakeProvider(_calls(2), _text("Please narrow the task."))

    events = _run(provider, max_tool_rounds=10, max_tool_calls=1)

    uses = [event for event in events if isinstance(event, AgentToolUse)]
    assert len(uses) == 2
    assert all(not event.ok for event in uses)
    assert events[-1] == AgentText("Please narrow the task.")


def test_reasoning_is_reported_without_entering_the_answer():
    provider = FakeProvider([ReasoningDelta("Counting people. "), TextDelta("Two people.")])

    assert _run(provider) == [AgentReasoning("Counting people. "), AgentText("Two people.")]


def test_a_failed_tool_call_is_reported_as_such():
    provider = FakeProvider(_calls(), _text("Sorry."))

    events = _run(provider, tool_ok=False)

    assert events[:2] == [
        AgentToolStart(BASH_TOOL, '{"command":"rg people"}', "call_0"),
        AgentToolUse(BASH_TOOL, '{"command":"rg people"}', "command result", False, "call_0"),
    ]


@pytest.mark.parametrize("arguments", ['{"command":"echo partial"}', '{"command":'])
def test_output_limit_refuses_tool_calls_and_reissues_with_safe_arguments(arguments):
    call = ToolCall("cut", BASH_TOOL, arguments)
    complete = ToolCall("complete", BASH_TOOL, '{"command":"echo complete"}')
    provider = FakeProvider(
        [ToolCallRequest((call,)), ResponseEnd("length")],
        [ToolCallRequest((complete,)), ResponseEnd("tool_calls")],
        _text("Done"),
    )
    executed = []
    agent = Agent()

    async def execute(name, raw):
        executed.append((name, raw))
        return AgentToolOutcome("complete result", True)

    async def collect():
        return [
            event
            async for event in agent.prompt(provider, QUESTION, bind_agent_tools(TOOLS, execute), max_tool_rounds=3)
        ]

    events = asyncio.run(collect())
    assert executed == [(BASH_TOOL, complete.arguments)]
    refused = next(event for event in events if isinstance(event, AgentToolUse))
    assert not refused.ok
    assert "output token limit" in refused.result
    replay = provider.requests[1][0]
    assert replay[-2]["tool_calls"][0]["function"]["arguments"] == "{}"
    assert replay[-1]["tool_call_id"] == "cut"
    assert agent.state.messages[0].tool_calls == (call,)
    assert agent.state.messages[0].stop_reason == "length"


@pytest.mark.parametrize("limits", [{"max_tool_rounds": 1}, {"max_tool_calls": 1}])
def test_repeated_truncated_calls_end_at_the_trusted_budget(limits):
    provider = FakeProvider([*_calls(), ResponseEnd("length")], _text("Final answer"))
    events = _run(provider, **limits)
    assert len(provider.requests) == 2
    assert provider.requests[-1][1] == []
    assert [event for event in events if isinstance(event, AgentText)] == [AgentText("Final answer")]


def test_agent_keeps_partial_output_when_closed_and_releases_it_on_reset():
    async def exercise():
        agent = Agent()
        stream = agent.prompt(FakeProvider(_text("Partial", "not delivered")), QUESTION, [])
        assert await anext(stream) == AgentText("Partial")
        with pytest.raises(RuntimeError, match="cleanup"):
            agent.reset()
        await stream.aclose()
        assert agent.state.messages == [AssistantMessage("Partial", "aborted")]
        agent.reset()
        assert agent.state.messages == []

    asyncio.run(exercise())


@pytest.mark.parametrize(
    ("call_count", "finish_reason", "limits"),
    [
        (1, "length", {"max_tool_rounds": 4}),
        (1, "length", {"max_tool_rounds": 1}),
        (2, "tool_calls", {"max_tool_calls": 1}),
    ],
    ids=["truncated-retry", "truncated-final-answer", "budget-refusal"],
)
def test_refused_tools_consume_steering_before_the_next_provider_request(call_count, finish_reason, limits):
    queued, executed, requests = [], [], []
    instruction = "Do not edit. Only explain."
    calls = tuple(ToolCall(f"call-{index}", BASH_TOOL, '{"command":"edit schedule"}') for index in range(call_count))

    class Provider:
        async def stream_events(self, messages, tools=None):
            requests.append(list(messages))
            if len(requests) == 1:
                queued.append(("cancel-edit", instruction))
                yield ToolCallRequest(calls)
                yield ResponseEnd(finish_reason)
            elif messages[-1]["content"] == instruction:
                yield TextDelta("I will only explain.")
            else:
                yield ToolCallRequest((ToolCall("retry", BASH_TOOL, calls[0].arguments),))

    def take_steering(_close_if_empty):
        messages = list(queued)
        queued.clear()
        return messages

    async def execute(_name, arguments):
        executed.append(arguments)
        return AgentToolOutcome("Edited", True)

    async def collect():
        return [
            event
            async for event in agent_loop(
                Provider(), QUESTION, bind_agent_tools(TOOLS, execute), take_steering=take_steering, **limits
            )
        ]

    events = asyncio.run(collect())
    assert requests[1][-1] == {"role": "user", "content": instruction}
    assert [message["tool_call_id"] for message in requests[1][2:-1]] == [call.id for call in calls]
    assert not executed
    assert len(requests) == 2
    assert events.count(AgentSteering("cancel-edit", instruction)) == 1
    assert events[-2:] == [AgentText("I will only explain."), AgentMessageEnd(AssistantMessage("I will only explain."))]

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

from nurse_scheduling.ai.agent import (
    AgentReasoning,
    AgentText,
    AgentToolOutcome,
    AgentToolStart,
    AgentToolUse,
    run_tool_agent,
)
from nurse_scheduling.ai.pi.bash import BASH_TOOL
from nurse_scheduling.ai.pi.read import READ_TOOL
from nurse_scheduling.ai.provider import ChatMessage, ReasoningDelta, TextDelta, ToolCall, ToolCallRequest

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


def _run(provider: FakeProvider, *, tool_ok: bool = True) -> list:
    async def execute(_name: str, _arguments: str) -> AgentToolOutcome:
        return AgentToolOutcome("command result", tool_ok)

    async def collect() -> list:
        return [
            event
            async for event in run_tool_agent(
                provider,
                QUESTION,
                TOOLS,
                execute,
            )
        ]

    return asyncio.run(collect())


def test_a_question_only_run_streams_text():
    provider = FakeProvider(_text("P1 ", "works."))

    assert _run(provider) == [AgentText("P1 "), AgentText("works.")]
    assert len(provider.requests) == 1


def test_a_tool_call_is_executed_and_returned_to_the_provider():
    provider = FakeProvider(_calls(), _text("Two people."))

    events = _run(provider)

    assert events[:2] == [
        AgentToolStart(BASH_TOOL, '{"command":"rg people"}'),
        AgentToolUse(BASH_TOOL, '{"command":"rg people"}', "command result", True),
    ]
    second_request = provider.requests[1][0]
    assert second_request[-2]["tool_calls"][0]["function"]["name"] == BASH_TOOL
    assert second_request[-1] == {
        "role": "tool",
        "tool_call_id": "call_0",
        "content": "command result",
    }


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
            async for event in run_tool_agent(
                provider,
                QUESTION,
                TOOLS,
                execute,
                parallel_tool_names=frozenset({BASH_TOOL}),
            )
        ]

    events = asyncio.run(collect())
    uses = [event for event in events if isinstance(event, AgentToolUse)]

    assert max_active == 2
    assert [event.result for event in uses] == ['{"command":"first"}', '{"command":"second"}']
    assert all(isinstance(event, AgentToolStart) for event in events[:2])


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
        async for _event in run_tool_agent(
            provider,
            QUESTION,
            TOOLS,
            execute,
            parallel_tool_names=frozenset({BASH_TOOL}),
        ):
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

    async def execute(_name: str, _arguments: str) -> AgentToolOutcome:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return AgentToolOutcome("result", True)

    async def collect() -> None:
        async for _event in run_tool_agent(
            provider,
            QUESTION,
            TOOLS,
            execute,
            parallel_tool_names=frozenset({READ_TOOL}),
        ):
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

    async def execute(_name: str, _arguments: str) -> AgentToolOutcome:
        nonlocal executed
        assert activity == ["enter"]
        executed += 1
        return AgentToolOutcome("command result", True)

    async def collect() -> None:
        async for _event in run_tool_agent(provider, QUESTION, TOOLS, execute, activity_batch):
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


def test_reasoning_is_reported_without_entering_the_answer():
    provider = FakeProvider([ReasoningDelta("Counting people. "), TextDelta("Two people.")])

    assert _run(provider) == [AgentReasoning("Counting people. "), AgentText("Two people.")]


def test_a_failed_tool_call_is_reported_as_such():
    provider = FakeProvider(_calls(), _text("Sorry."))

    events = _run(provider, tool_ok=False)

    assert events[:2] == [
        AgentToolStart(BASH_TOOL, '{"command":"rg people"}'),
        AgentToolUse(BASH_TOOL, '{"command":"rg people"}', "command result", False),
    ]

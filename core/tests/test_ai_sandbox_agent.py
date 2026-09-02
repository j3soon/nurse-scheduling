"""Tests for disposable sandbox-mode agent orchestration."""

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

from nurse_scheduling.ai.agent import AgentProposal, AgentText, AgentToolUse
from nurse_scheduling.ai.pi.bash import BASH_TOOL
from nurse_scheduling.ai.provider import ChatMessage, ProviderError, TextDelta, ToolCall, ToolCallRequest
from nurse_scheduling.ai.sandbox import CommandResult, SandboxError
from nurse_scheduling.ai.sandbox.fake import FakeSandboxBackend, FakeSandboxFactory
from nurse_scheduling.ai.sandbox_agent import (
    REFERENCE_README,
    REFERENCE_SCHEMA,
    WORKSPACE_SCHEDULE,
    AgentScheduleChange,
    SandboxAgentLimits,
    SandboxCandidateError,
    SandboxTurnTimeoutError,
    run_sandbox_agent,
)

from .ai_test_helper import SCHEDULE_BYTE_LIMIT, schedule_yaml

MESSAGES: list[ChatMessage] = [{"role": "user", "content": "Give P1 a description."}]


class ScriptedProvider:
    def __init__(self, *turns) -> None:
        self.turns = list(turns)
        self.requests: list[tuple[list[ChatMessage], object]] = []

    async def stream_events(self, messages: Sequence[ChatMessage], tools=None) -> AsyncIterator:
        self.requests.append((list(messages), tools))
        turn = self.turns[min(len(self.requests) - 1, len(self.turns) - 1)]
        if isinstance(turn, BaseException):
            raise turn
        for event in turn:
            yield event


def _run_call(command: str = "edit") -> list[object]:
    return [ToolCallRequest((ToolCall("call-1", BASH_TOOL, json.dumps({"command": command})),))]


def _limits(**overrides) -> SandboxAgentLimits:
    values = {
        "max_schedule_bytes": SCHEDULE_BYTE_LIMIT,
        "turn_timeout_seconds": 2,
        "cleanup_timeout_seconds": 1,
        "bash_command_timeout_seconds": 10,
    }
    values.update(overrides)
    return SandboxAgentLimits(**values)


def _rename_handler(_command: str, _timeout: float | None, backend: FakeSandboxBackend) -> CommandResult:
    current = backend.files[WORKSPACE_SCHEDULE].decode()
    backend.files[WORKSPACE_SCHEDULE] = current.replace(
        "  - id: P1\n    description: ''",
        "  - id: P1\n    description: Head",
        1,
    ).encode()
    return CommandResult("updated\n", "", 0)


def _collect(provider, factory, **limit_overrides) -> list:
    async def collect() -> list:
        return [
            event
            async for event in run_sandbox_agent(
                provider,
                factory,
                schedule_yaml(),
                MESSAGES,
                _limits(**limit_overrides),
            )
        ]

    return asyncio.run(collect())


def test_one_turn_hydrates_runs_reads_validates_proposes_and_closes():
    factory = FakeSandboxFactory(lambda sandbox_id: FakeSandboxBackend(sandbox_id, command_handler=_rename_handler))
    provider = ScriptedProvider(_run_call(), [TextDelta("I propose the description.")])

    events = _collect(provider, factory)

    backend = factory.created[0]
    assert backend.closed
    assert WORKSPACE_SCHEDULE in backend.files
    assert REFERENCE_README in backend.files
    assert REFERENCE_SCHEMA in backend.files
    assert b"Path: preferences.shift count" in backend.files[REFERENCE_SCHEMA]
    assert backend.commands == [("edit", None)]
    assert [tool["function"]["name"] for tool in provider.requests[0][1]] == [BASH_TOOL]
    assert isinstance(events[0], AgentToolUse)
    assert events[0].ok
    assert "Trusted schedule check after this command" in events[0].result
    assert "passed trusted server-side validation" in events[0].result
    schedule_change = next(event for event in events if isinstance(event, AgentScheduleChange))
    assert "description: Head" in schedule_change.schedule_yaml
    assert AgentText("I propose the description.") in events
    proposal = next(event for event in events if isinstance(event, AgentProposal))
    assert "description: Head" in proposal.text
    assert "people.items[0].description" in proposal.diff


def test_separate_agent_turns_get_fresh_isolated_sandboxes():
    factory = FakeSandboxFactory()
    provider = ScriptedProvider([TextDelta("No change.")])

    _collect(provider, factory)
    _collect(provider, factory)

    assert len(factory.created) == 2
    assert factory.created[0].sandbox_id != factory.created[1].sandbox_id
    factory.created[0].files["/workspace/turn-one-only"] = b"data"
    assert "/workspace/turn-one-only" not in factory.created[1].files
    assert all(backend.closed for backend in factory.created)


@pytest.mark.parametrize(
    "failure",
    [
        ProviderError("model failed"),
        SandboxError("command failed"),
    ],
    ids=["model", "command"],
)
def test_model_or_command_failure_closes_the_sandbox(failure: BaseException):
    if isinstance(failure, ProviderError):
        provider = ScriptedProvider(failure)
        factory = FakeSandboxFactory()
    else:

        def fail_command(*_args):
            raise failure

        provider = ScriptedProvider(_run_call())
        factory = FakeSandboxFactory(lambda sandbox_id: FakeSandboxBackend(sandbox_id, command_handler=fail_command))

    with pytest.raises(type(failure)):
        _collect(provider, factory)

    assert factory.created[0].closed


def test_candidate_read_failure_closes_the_sandbox():
    class ReadFailureBackend(FakeSandboxBackend):
        async def read_file(self, path: str) -> bytes:
            raise SandboxError(f"cannot read {path}")

    factory = FakeSandboxFactory(ReadFailureBackend)

    with pytest.raises(SandboxError, match="cannot read"):
        _collect(ScriptedProvider([TextDelta("Done.")]), factory)

    assert factory.created[0].closed


def test_trusted_validation_rejects_an_invalid_candidate_and_closes():
    def invalidate(_command: str, _timeout: float | None, backend: FakeSandboxBackend) -> CommandResult:
        backend.files[WORKSPACE_SCHEDULE] = b"not: [valid"
        return CommandResult("", "", 0)

    factory = FakeSandboxFactory(lambda sandbox_id: FakeSandboxBackend(sandbox_id, command_handler=invalidate))

    with pytest.raises(SandboxCandidateError, match="trusted schedule validation"):
        _collect(ScriptedProvider(_run_call(), [TextDelta("Done.")]), factory)

    assert factory.created[0].closed


def test_intermediate_trusted_validation_lets_the_model_repair_a_bad_edit():
    def edit(command: str, _timeout: float | None, backend: FakeSandboxBackend) -> CommandResult:
        if command == "break":
            backend.files[WORKSPACE_SCHEDULE] = b"not: [valid"
        else:
            current = schedule_yaml()
            backend.files[WORKSPACE_SCHEDULE] = current.replace(
                "  - id: P1\n    description: ''",
                "  - id: P1\n    description: Head",
                1,
            ).encode()
        return CommandResult("updated\n", "", 0)

    factory = FakeSandboxFactory(lambda sandbox_id: FakeSandboxBackend(sandbox_id, command_handler=edit))
    provider = ScriptedProvider(
        _run_call("break"),
        _run_call("repair"),
        [TextDelta("I repaired the candidate.")],
    )

    events = _collect(provider, factory)

    tools = [event for event in events if isinstance(event, AgentToolUse)]
    assert not tools[0].ok
    assert "introduces problems" in tools[0].result
    assert "Remaining edit attempts" not in tools[0].result
    assert tools[1].ok
    assert any(isinstance(event, AgentProposal) for event in events)
    assert len([event for event in events if isinstance(event, AgentScheduleChange)]) == 1
    assert factory.created[0].closed


def test_cancelling_the_model_turn_closes_the_sandbox():
    async def exercise() -> FakeSandboxBackend:
        entered = asyncio.Event()

        class WaitingProvider:
            async def stream_events(self, _messages, tools=None):
                entered.set()
                await asyncio.Event().wait()
                yield TextDelta("unreachable")

        factory = FakeSandboxFactory()

        async def collect() -> None:
            async for _ in run_sandbox_agent(
                WaitingProvider(),
                factory,
                schedule_yaml(),
                MESSAGES,
                _limits(turn_timeout_seconds=30),
            ):
                pass

        task = asyncio.create_task(collect())
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return factory.created[0]

    assert asyncio.run(exercise()).closed


def test_whole_turn_timeout_closes_the_sandbox():
    class WaitingProvider:
        async def stream_events(self, _messages, tools=None):
            await asyncio.Event().wait()
            yield TextDelta("unreachable")

    factory = FakeSandboxFactory()

    with pytest.raises(SandboxTurnTimeoutError, match="0.01-second limit"):
        _collect(WaitingProvider(), factory, turn_timeout_seconds=0.01)

    assert factory.created[0].closed

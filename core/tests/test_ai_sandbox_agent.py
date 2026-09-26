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

from nurse_scheduling.ai.agent_types import (
    AgentEvent,
    AgentProposal,
    AgentToolResult,
    MessageTextDelta,
    ToolExecutionEnd,
    ToolExecutionStart,
)
from nurse_scheduling.ai.optimizer import OPTIMIZER_TOOL, WORKSPACE_OPTIMIZER_RESULT
from nurse_scheduling.ai.pi.bash import BASH_TOOL
from nurse_scheduling.ai.pi.edit import EDIT_TOOL
from nurse_scheduling.ai.pi.read import READ_TOOL
from nurse_scheduling.ai.pi.write import WRITE_TOOL
from nurse_scheduling.ai.provider import ChatMessage, ProviderError, TextDelta, ToolCall, ToolCallRequest
from nurse_scheduling.ai.sandbox import CommandResult, SandboxError
from nurse_scheduling.ai.sandbox.fake import FakeSandboxBackend, FakeSandboxFactory
from nurse_scheduling.ai.schema import load_taiwan_holidays_reference, load_user_guide_references
from nurse_scheduling.ai.workspace import (
    REFERENCE_SCHEMAS,
    REFERENCE_USER_GUIDE,
    WORKSPACE_ATTACHMENT_MANIFEST,
    WORKSPACE_PENDING_DIFF,
    WORKSPACE_PENDING_PROPOSAL,
    WORKSPACE_SCHEDULE,
    AgentScheduleChange,
    SandboxAttachment,
    SandboxCandidateError,
    SandboxRunTimeoutError,
    WorkspaceLimits,
)
from nurse_scheduling.ai.workspace_tools import run_workspace

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


def _limits(**overrides) -> WorkspaceLimits:
    values = {
        "max_schedule_bytes": SCHEDULE_BYTE_LIMIT,
        "turn_timeout_seconds": 2,
        "cleanup_timeout_seconds": 1,
        "bash_command_timeout_seconds": 10,
        "max_tool_rounds": 10,
        "max_tool_calls": 20,
    }
    values.update(overrides)
    return WorkspaceLimits(**values)


def _rename_handler(_command: str, _timeout: float | None, backend: FakeSandboxBackend) -> CommandResult:
    current = backend.files[WORKSPACE_SCHEDULE].decode()
    backend.files[WORKSPACE_SCHEDULE] = current.replace(
        "  - id: P1\n    description: ''",
        "  - id: P1\n    description: Head",
        1,
    ).encode()
    return CommandResult("updated\n", "", 0)


def _collect(
    provider,
    factory,
    *,
    pending_proposal_yaml: str = "",
    pending_proposal_diff: str = "",
    attachments: Sequence[SandboxAttachment] = (),
    optimizer_result: bytes | None = None,
    **limit_overrides,
) -> list:
    async def collect() -> list:
        return [
            event
            async for event in run_workspace(
                provider,
                factory,
                schedule_yaml(),
                MESSAGES,
                _limits(**limit_overrides),
                pending_proposal_yaml=pending_proposal_yaml,
                pending_proposal_diff=pending_proposal_diff,
                attachments=attachments,
                optimizer_result=optimizer_result,
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
    assert set(REFERENCE_SCHEMAS.values()) <= backend.files.keys()
    assert b"# Experimental AI Chat" in backend.files[f"{REFERENCE_USER_GUIDE}/experimental-ai.md"]
    assert b"# People" in backend.files[f"{REFERENCE_USER_GUIDE}/people.md"]
    assert b"Path: preferences.shift count" in backend.files[REFERENCE_SCHEMAS["preferences"]]
    assert b"Path: export.formatting.cell" in backend.files[REFERENCE_SCHEMAS["export"]]
    assert b"Path: people.items" in backend.files[REFERENCE_SCHEMAS["core"]]
    assert b"SPECIAL_DATE_INFO" in backend.files[REFERENCE_SCHEMAS["taiwan-holidays"]]
    assert backend.commands == [("edit", None)]
    assert [tool["function"]["name"] for tool in provider.requests[0][1]] == [
        READ_TOOL,
        BASH_TOOL,
        EDIT_TOOL,
        WRITE_TOOL,
    ]
    assert isinstance(events[0], ToolExecutionStart)
    assert events[0].tool_call_id
    preview_result = next(event for event in events if isinstance(event, ToolExecutionEnd))
    assert preview_result.tool_call_id == events[0].tool_call_id
    assert preview_result.details["schedule_yaml"] == next(
        event.schedule_yaml for event in events if isinstance(event, AgentScheduleChange)
    )
    tool_use = next(event for event in events if isinstance(event, ToolExecutionEnd))
    assert tool_use.ok
    assert "Trusted schedule check after this command" in tool_use.result
    assert "passed trusted server-side validation" in tool_use.result
    schedule_change = next(event for event in events if isinstance(event, AgentScheduleChange))
    assert "description: Head" in schedule_change.schedule_yaml
    assert MessageTextDelta("I propose the description.") in events
    proposal = next(event for event in events if isinstance(event, AgentProposal))
    assert "description: Head" in proposal.text
    assert "people.items[0].description" in proposal.diff


def test_optimizer_tool_receives_the_current_working_schedule() -> None:
    optimizer_call = ToolCallRequest(
        (ToolCall("call-1", OPTIMIZER_TOOL, json.dumps({"action": "start", "timeout_seconds": 30})),)
    )
    provider = ScriptedProvider([optimizer_call], [TextDelta("The optimizer is running.")])
    factory = FakeSandboxFactory()
    received: list[tuple[str, str]] = []

    async def execute_optimizer(current_schedule: str, arguments: str):
        received.append((current_schedule, arguments))
        return AgentToolResult("Started in the background.", True)

    async def collect() -> list:
        return [
            event
            async for event in run_workspace(
                provider,
                factory,
                schedule_yaml(),
                MESSAGES,
                _limits(optimizer_default_timeout_seconds=420),
                execute_optimizer=execute_optimizer,
            )
        ]

    events = asyncio.run(collect())

    assert received == [(schedule_yaml(), '{"action": "start", "timeout_seconds": 30}')]
    assert OPTIMIZER_TOOL in [tool["function"]["name"] for tool in provider.requests[0][1]]
    optimizer_tool = next(tool for tool in provider.requests[0][1] if tool["function"]["name"] == OPTIMIZER_TOOL)
    assert (
        "Default: 420 seconds"
        in optimizer_tool["function"]["parameters"]["properties"]["timeout_seconds"]["description"]
    )
    assert next(event for event in events if isinstance(event, ToolExecutionEnd)).ok


def test_optimizer_rejects_an_invalid_working_schedule_before_submission() -> None:
    provider = ScriptedProvider(
        [
            ToolCallRequest(
                (
                    ToolCall(
                        "write-invalid",
                        WRITE_TOOL,
                        json.dumps({"path": "schedule.yaml", "content": "people: [unclosed"}),
                    ),
                )
            )
        ],
        [ToolCallRequest((ToolCall("start-optimizer", OPTIMIZER_TOOL, '{"action":"start"}'),))],
        [TextDelta("No run was submitted.")],
    )
    submitted: list[str] = []

    async def execute_optimizer(current_schedule: str, _arguments: str) -> AgentToolResult:
        submitted.append(current_schedule)
        return AgentToolResult("Started in the background.", True)

    async def collect() -> None:
        async for _event in run_workspace(
            provider,
            FakeSandboxFactory(),
            schedule_yaml(),
            MESSAGES,
            _limits(),
            execute_optimizer=execute_optimizer,
        ):
            pass

    with pytest.raises(SandboxCandidateError):
        asyncio.run(collect())

    assert submitted == []


@pytest.mark.parametrize("action", ["status", "finish_now"])
def test_optimizer_job_controls_work_with_an_invalid_working_schedule(action: str) -> None:
    arguments = json.dumps({"action": action})
    provider = ScriptedProvider(
        [
            ToolCallRequest(
                (
                    ToolCall(
                        "write-invalid",
                        WRITE_TOOL,
                        json.dumps({"path": "schedule.yaml", "content": "people: [unclosed"}),
                    ),
                )
            )
        ],
        [ToolCallRequest((ToolCall("control-job", OPTIMIZER_TOOL, arguments),))],
        [TextDelta("The job control completed.")],
    )
    controls: list[tuple[str, str]] = []
    events: list[AgentEvent | AgentScheduleChange] = []

    async def execute_optimizer(current_schedule: str, received_arguments: str) -> AgentToolResult:
        controls.append((current_schedule, received_arguments))
        return AgentToolResult("Existing job updated.", True)

    async def collect() -> None:
        async for event in run_workspace(
            provider,
            FakeSandboxFactory(),
            schedule_yaml(),
            MESSAGES,
            _limits(),
            execute_optimizer=execute_optimizer,
        ):
            events.append(event)

    with pytest.raises(SandboxCandidateError):
        asyncio.run(collect())

    assert controls == [("", arguments)]
    control_result = next(
        event for event in events if isinstance(event, ToolExecutionEnd) and event.name == OPTIMIZER_TOOL
    )
    assert control_result.ok


def test_pending_proposal_is_hydrated_as_trusted_read_only_context():
    factory = FakeSandboxFactory(lambda sandbox_id: FakeSandboxBackend(sandbox_id))

    _collect(
        ScriptedProvider(
            [ToolCallRequest((ToolCall("call-1", READ_TOOL, json.dumps({"path": WORKSPACE_PENDING_PROPOSAL})),))],
            [TextDelta("The pending description is Ready.")],
        ),
        factory,
        pending_proposal_yaml="apiVersion: alpha\ndescription: Ready\n",
        pending_proposal_diff='- description: "" -> "Ready"',
    )

    backend = factory.created[0]
    assert backend.files[WORKSPACE_PENDING_PROPOSAL] == b"apiVersion: alpha\ndescription: Ready\n"
    assert backend.files[WORKSPACE_PENDING_DIFF] == b'- description: "" -> "Ready"'
    assert backend.write_files_calls == 1


def test_hydration_uploads_every_reference_in_one_request():
    factory = FakeSandboxFactory(lambda sandbox_id: FakeSandboxBackend(sandbox_id, command_handler=_rename_handler))

    _collect(ScriptedProvider(_run_call(), [TextDelta("Done.")]), factory)

    backend = factory.created[0]
    # Hydration now runs in front of the first tool result, so per-file round trips are paid
    # by the user rather than absorbed before the turn starts.
    assert backend.write_files_calls == 1
    assert len(backend.files) > len(REFERENCE_SCHEMAS)


def test_hydration_places_untrusted_attachments_under_safe_paths():
    factory = FakeSandboxFactory()
    provider = ScriptedProvider(
        [ToolCallRequest((ToolCall("call-1", READ_TOOL, json.dumps({"path": WORKSPACE_ATTACHMENT_MANIFEST})),))],
        [TextDelta("Inspected.")],
    )

    _collect(
        provider,
        factory,
        attachments=(SandboxAttachment("../../staff data.bin", "application/octet-stream", b"payload"),),
    )

    backend = factory.created[0]
    manifest = json.loads(backend.files[WORKSPACE_ATTACHMENT_MANIFEST])
    attachment = manifest["attachments"][0]
    assert attachment == {
        "original_filename": "../../staff data.bin",
        "path": "/workspace/attachments/01-staff_data.bin",
        "media_type": "application/octet-stream",
        "bytes": 7,
        "trusted": False,
    }
    assert backend.files[attachment["path"]] == b"payload"
    assert b"inspect_workbook" in backend.files["/reference/tools/inspect_xlsx.py"]
    assert b"inspect_pdf" in backend.files["/reference/tools/inspect_pdf.py"]


def test_hydration_keeps_optimizer_result_outside_user_attachments():
    factory = FakeSandboxFactory()
    provider = ScriptedProvider(
        [ToolCallRequest((ToolCall("call-1", READ_TOOL, json.dumps({"path": WORKSPACE_OPTIMIZER_RESULT})),))],
        [TextDelta("Inspected.")],
    )

    _collect(provider, factory, optimizer_result=b"workbook")

    backend = factory.created[0]
    assert backend.files[WORKSPACE_OPTIMIZER_RESULT] == b"workbook"
    assert WORKSPACE_ATTACHMENT_MANIFEST not in backend.files


def test_reference_sources_are_read_from_disk_once_per_process():
    load_user_guide_references.cache_clear()
    load_taiwan_holidays_reference.cache_clear()

    first_guide = load_user_guide_references()
    first_holidays = load_taiwan_holidays_reference()

    assert load_user_guide_references() is first_guide
    assert load_taiwan_holidays_reference() is first_holidays
    with pytest.raises(TypeError):
        first_guide["people.md"] = "mutated"


def test_write_tool_rewrites_validates_and_proposes_the_schedule():
    schedule = schedule_yaml()
    changed = schedule.replace(
        "  - id: P1\n    description: ''",
        "  - id: P1\n    description: Head",
        1,
    )
    write_call = ToolCallRequest(
        (
            ToolCall(
                "call-1",
                WRITE_TOOL,
                json.dumps({"path": "schedule.yaml", "content": changed}),
            ),
        )
    )
    provider = ScriptedProvider([write_call], [TextDelta("I propose the description.")])
    factory = FakeSandboxFactory()

    events = _collect(provider, factory)

    tool_use = next(event for event in events if isinstance(event, ToolExecutionEnd))
    assert tool_use.name == WRITE_TOOL
    assert tool_use.ok
    assert "passed trusted server-side validation" in tool_use.result
    assert any(isinstance(event, AgentScheduleChange) for event in events)
    assert any(isinstance(event, AgentProposal) for event in events)


def test_edit_tool_replaces_validates_and_proposes_the_schedule():
    edit_call = ToolCallRequest(
        (
            ToolCall(
                "call-1",
                EDIT_TOOL,
                json.dumps(
                    {
                        "path": "schedule.yaml",
                        "edits": [
                            {
                                "oldText": "  - id: P1\n    description: ''",
                                "newText": "  - id: P1\n    description: Head",
                            }
                        ],
                    }
                ),
            ),
        )
    )
    provider = ScriptedProvider([edit_call], [TextDelta("I propose the description.")])
    factory = FakeSandboxFactory()

    events = _collect(provider, factory)

    tool_use = next(event for event in events if isinstance(event, ToolExecutionEnd))
    assert tool_use.name == EDIT_TOOL
    assert tool_use.ok
    assert "passed trusted server-side validation" in tool_use.result
    assert any(isinstance(event, AgentScheduleChange) for event in events)
    assert any(isinstance(event, AgentProposal) for event in events)


def test_read_tool_does_not_trigger_a_redundant_schedule_change_scan():
    class CountingReadBackend(FakeSandboxBackend):
        def __init__(self, sandbox_id: str) -> None:
            super().__init__(sandbox_id)
            self.read_paths: list[str] = []

        async def read_file(self, path: str) -> bytes:
            self.read_paths.append(path)
            return await super().read_file(path)

    provider = ScriptedProvider(
        [ToolCallRequest((ToolCall("call-1", READ_TOOL, '{"path":"schedule.yaml"}'),))],
        [TextDelta("Read it.")],
    )
    factory = FakeSandboxFactory(CountingReadBackend)

    _collect(provider, factory)

    backend = factory.created[0]
    assert isinstance(backend, CountingReadBackend)
    assert backend.read_paths.count(WORKSPACE_SCHEDULE) == 2


def test_text_only_turns_do_not_start_sandboxes():
    factory = FakeSandboxFactory()
    provider = ScriptedProvider([TextDelta("No change.")])

    _collect(provider, factory)
    _collect(provider, factory)

    assert factory.created == []


def test_separate_tool_turns_get_fresh_isolated_sandboxes():
    factory = FakeSandboxFactory()

    _collect(ScriptedProvider(_run_call(), [TextDelta("No change.")]), factory)
    _collect(ScriptedProvider(_run_call(), [TextDelta("No change.")]), factory)

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
def test_failure_before_tools_skips_sandbox_and_command_failure_closes_it(failure: BaseException):
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

    if isinstance(failure, ProviderError):
        assert factory.created == []
    else:
        assert factory.created[0].closed


def test_candidate_read_failure_closes_the_sandbox():
    class ReadFailureBackend(FakeSandboxBackend):
        async def read_file(self, path: str) -> bytes:
            raise SandboxError(f"cannot read {path}")

    factory = FakeSandboxFactory(ReadFailureBackend)

    with pytest.raises(SandboxError, match="cannot read"):
        _collect(ScriptedProvider(_run_call(), [TextDelta("Done.")]), factory)

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

    tools = [event for event in events if isinstance(event, ToolExecutionEnd)]
    assert not tools[0].ok
    assert "working copy retains this command's changes" in tools[0].result
    assert "Repair the reported problems before finishing" in tools[0].result
    assert "introduces problems" in tools[0].result
    assert "Remaining edit attempts" not in tools[0].result
    assert tools[1].ok
    assert any(isinstance(event, AgentProposal) for event in events)
    assert len([event for event in events if isinstance(event, AgentScheduleChange)]) == 1
    assert factory.created[0].closed


def test_a_deleted_working_copy_is_reported_so_the_model_can_restore_it():
    def edit(command: str, _timeout: float | None, backend: FakeSandboxBackend) -> CommandResult:
        if command == "delete":
            del backend.files[WORKSPACE_SCHEDULE]
        else:
            backend.files[WORKSPACE_SCHEDULE] = (
                schedule_yaml()
                .replace(
                    "  - id: P1\n    description: ''",
                    "  - id: P1\n    description: Head",
                    1,
                )
                .encode()
            )
        return CommandResult("", "", 0)

    factory = FakeSandboxFactory(lambda sandbox_id: FakeSandboxBackend(sandbox_id, command_handler=edit))
    provider = ScriptedProvider(
        _run_call("delete"),
        _run_call("restore"),
        [TextDelta("I restored the working copy.")],
    )

    events = _collect(provider, factory)

    tools = [event for event in events if isinstance(event, ToolExecutionEnd)]
    assert not tools[0].ok
    assert f"{WORKSPACE_SCHEDULE} no longer exists" in tools[0].result
    assert tools[1].ok
    assert any(isinstance(event, AgentProposal) for event in events)
    assert factory.created[0].closed


def test_a_turn_that_ends_without_the_working_copy_fails_candidate_validation():
    def delete(_command: str, _timeout: float | None, backend: FakeSandboxBackend) -> CommandResult:
        del backend.files[WORKSPACE_SCHEDULE]
        return CommandResult("", "", 0)

    factory = FakeSandboxFactory(lambda sandbox_id: FakeSandboxBackend(sandbox_id, command_handler=delete))

    with pytest.raises(SandboxCandidateError, match="no longer exists"):
        _collect(ScriptedProvider(_run_call("delete"), [TextDelta("Done.")]), factory)

    assert factory.created[0].closed


def test_cancelling_before_a_tool_call_does_not_start_a_sandbox():
    async def exercise() -> FakeSandboxFactory:
        entered = asyncio.Event()

        class WaitingProvider:
            async def stream_events(self, _messages, tools=None):
                entered.set()
                await asyncio.Event().wait()
                yield TextDelta("unreachable")

        factory = FakeSandboxFactory()

        async def collect() -> None:
            async for _ in run_workspace(
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
        return factory

    assert asyncio.run(exercise()).created == []


def test_whole_turn_timeout_before_a_tool_call_does_not_start_a_sandbox():
    class WaitingProvider:
        async def stream_events(self, _messages, tools=None):
            await asyncio.Event().wait()
            yield TextDelta("unreachable")

    factory = FakeSandboxFactory()

    with pytest.raises(SandboxRunTimeoutError, match="0.01-second limit"):
        _collect(WaitingProvider(), factory, turn_timeout_seconds=0.01)

    assert factory.created == []


@pytest.mark.parametrize("arguments", ["not json", "[]", "{}"], ids=["invalid-json", "not-object", "missing-fields"])
@pytest.mark.parametrize("tool", [READ_TOOL, BASH_TOOL, EDIT_TOOL, WRITE_TOOL, OPTIMIZER_TOOL])
def test_every_offered_tool_refuses_malformed_arguments_before_acting(tool: str, arguments: str) -> None:
    """Each tool owns Pi-compatible validation, so this contract replaces a central schema check."""
    from nurse_scheduling.ai.optimizer import SessionOptimizer

    from .test_ai_optimizer import FakeOptimizerBackend

    if tool == OPTIMIZER_TOOL and arguments == "{}":
        pytest.skip("An empty optimizer call means start, whose default action is valid")
    optimizer_backend = FakeOptimizerBackend()
    provider = ScriptedProvider(
        [ToolCallRequest((ToolCall("call-1", tool, arguments),))],
        [TextDelta("Done.")],
    )
    factory = FakeSandboxFactory()

    async def collect() -> list:
        async def on_completion(*_args) -> None:
            raise AssertionError("A refused call must not start a job")

        optimizer = SessionOptimizer(optimizer_backend, poll_interval_seconds=0.001, on_completion=on_completion)
        try:
            return [
                event
                async for event in run_workspace(
                    provider,
                    factory,
                    schedule_yaml(),
                    MESSAGES,
                    _limits(),
                    execute_optimizer=lambda current, raw: optimizer.execute("session", current, raw),
                )
            ]
        finally:
            await optimizer.close()

    events = asyncio.run(collect())

    result = next(event for event in events if isinstance(event, ToolExecutionEnd))
    assert not result.ok
    assert optimizer_backend.submissions == []
    for backend in factory.created:
        assert backend.commands == []
        assert backend.files[WORKSPACE_SCHEDULE].decode() == schedule_yaml()
    assert not any(isinstance(event, AgentProposal) for event in events)

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
import threading
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest

from nurse_scheduling.ai import provider as provider_module
from nurse_scheduling.ai.agent_types import (
    AgentEvent,
    AgentMessageEnd,
    AgentProposal,
    AgentText,
    AgentToolOutcome,
    AgentToolStart,
    AgentToolUse,
)
from nurse_scheduling.ai.attachment_tools.inspect_shift_requests import inspect_requests
from nurse_scheduling.ai.candidate import review_schedule_candidate
from nurse_scheduling.ai.config import AiSettings
from nurse_scheduling.ai.optimizer import OPTIMIZER_TOOL, WORKSPACE_OPTIMIZER_RESULT
from nurse_scheduling.ai.pi.bash import BASH_TOOL
from nurse_scheduling.ai.pi.edit import EDIT_TOOL
from nurse_scheduling.ai.pi.read import READ_TOOL
from nurse_scheduling.ai.pi.write import WRITE_TOOL
from nurse_scheduling.ai.provider import (
    ChatMessage,
    OpenAiCompatibleProvider,
    ProviderError,
    TextDelta,
    ToolCall,
    ToolCallRequest,
)
from nurse_scheduling.ai.result_context import build_result_context
from nurse_scheduling.ai.sandbox import CommandResult, SandboxError
from nurse_scheduling.ai.sandbox.fake import FakeSandboxBackend, FakeSandboxFactory
from nurse_scheduling.ai.schema import load_schedule_example, load_taiwan_holidays_reference, load_user_guide_references
from nurse_scheduling.ai.workspace import (
    REFERENCE_SCHEMAS,
    REFERENCE_USER_GUIDE,
    WORKSPACE_LAST_ACCEPTED_SCHEDULE,
    WORKSPACE_RESULT_CONTEXT,
    WORKSPACE_SCHEDULE,
    WORKSPACE_SOURCE_CONTEXT,
    AgentScheduleChange,
    SandboxAttachment,
    SandboxCandidateError,
    SandboxTurnTimeoutError,
    WorkspaceLimits,
    WorkspaceMetrics,
    _measured_sandbox_run,
    _read_candidate,
    _ScheduleCandidateTracker,
    attachment_path,
    hydrate_sandbox,
)
from nurse_scheduling.ai.workspace_tools import run_workspace

from .ai_test_helper import SCHEDULE_BYTE_LIMIT, base_schedule_payload, schedule_yaml
from .test_ai_provider import _delta_chunk, _sse_body

MESSAGES: list[ChatMessage] = [{"role": "user", "content": "Give P1 a description."}]


def test_schedule_reads_apply_the_limit_before_receiving_the_file():
    class BoundedBackend(FakeSandboxBackend):
        async def read_file(self, path, *, max_bytes=None):
            assert max_bytes == 4, "The schedule read must be bounded before buffering"
            return await super().read_file(path, max_bytes=max_bytes)

    async def exercise():
        backend = BoundedBackend("bounded", initial_files={WORKSPACE_SCHEDULE: b"12345"})
        with pytest.raises(SandboxCandidateError, match="schedule limit"):
            await _read_candidate(backend, 4)
        tracker = _ScheduleCandidateTracker(backend, "1234", 4)
        outcome, candidate = await tracker.review_if_changed()
        assert not outcome.ok
        assert "schedule limit" in outcome.text
        assert candidate is None

    asyncio.run(exercise())


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
                attachments=attachments,
                optimizer_result=optimizer_result,
            )
        ]

    return asyncio.run(collect())


def test_large_provider_read_batch_preserves_workspace_and_proposal(monkeypatch):
    def checkpoint(command, timeout, backend):
        backend.files["/workspace/checkpoint.txt"] = b"kept"
        return _rename_handler(command, timeout, backend)

    responses = [
        _sse_body(
            _delta_chunk(
                {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "setup",
                            "function": {"name": BASH_TOOL, "arguments": '{"command":"checkpoint"}'},
                        },
                    ]
                }
            )
        ),
        _sse_body(
            _delta_chunk(
                {
                    "tool_calls": [
                        {
                            "index": index,
                            "id": f"read-{index}",
                            "function": {
                                "name": READ_TOOL,
                                "arguments": '{"path":"/workspace/checkpoint.txt"}',
                            },
                        }
                        for index in range(9)
                    ]
                }
            )
        ),
        _sse_body(_delta_chunk({"content": "The checkpoint and proposal are preserved."})),
    ]
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, headers={"Content-Type": "text/event-stream"}, text=responses[len(requests) - 1])

    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(
        provider_module.httpx, "AsyncClient", lambda **kwargs: real_client(transport=transport, **kwargs)
    )
    provider = OpenAiCompatibleProvider(
        AiSettings(
            provider_base_url="https://provider.example/v1",
            provider_api_key="test",
            provider_model="test-model",
        )
    )
    factory = FakeSandboxFactory(lambda sandbox_id: FakeSandboxBackend(sandbox_id, command_handler=checkpoint))

    events = _collect(provider, factory)

    assert len(factory.created) == 1
    assert factory.created[0].commands == [("checkpoint", None)]
    assert factory.created[0].files["/workspace/checkpoint.txt"] == b"kept"
    reads = [event for event in events if isinstance(event, AgentToolUse) and event.name == READ_TOOL]
    assert len(reads) == 9 and all(event.ok and "kept" in event.result for event in reads)
    assert "description: Head" in next(event for event in events if isinstance(event, AgentProposal)).text
    replies = [message for message in requests[-1]["messages"] if message["role"] == "tool"]
    assert [message["tool_call_id"] for message in replies[-9:]] == [f"read-{index}" for index in range(9)]


def test_one_turn_hydrates_runs_reads_validates_proposes_and_closes():
    factory = FakeSandboxFactory(lambda sandbox_id: FakeSandboxBackend(sandbox_id, command_handler=_rename_handler))
    provider = ScriptedProvider(_run_call(), [TextDelta("I propose the description.")])

    events = _collect(provider, factory)

    backend = factory.created[0]
    assert backend.closed
    assert WORKSPACE_SCHEDULE in backend.files
    context = json.loads(backend.files[WORKSPACE_SOURCE_CONTEXT])
    assert context["people"] == ["P1", "P2"]
    assert inspect_requests(context, backend.files[WORKSPACE_SCHEDULE])["request_entries"] == 1
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
    assert isinstance(events[0], AgentMessageEnd)
    assert events[0].message.tool_calls[0].id == "call-1"
    assert isinstance(events[1], AgentToolStart)
    tool_use = next(event for event in events if isinstance(event, AgentToolUse))
    assert tool_use.ok
    assert "Trusted schedule check after this command" in tool_use.result
    assert "passed trusted server-side validation" in tool_use.result
    schedule_change = next(event for event in events if isinstance(event, AgentScheduleChange))
    assert "description: Head" in schedule_change.schedule_yaml
    assert AgentText("I propose the description.") in events
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
        return AgentToolOutcome("Started in the background.", True)

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
    assert next(event for event in events if isinstance(event, AgentToolUse)).ok


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

    async def execute_optimizer(current_schedule: str, _arguments: str) -> AgentToolOutcome:
        submitted.append(current_schedule)
        return AgentToolOutcome("Started in the background.", True)

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
@pytest.mark.parametrize("with_read", [False, True], ids=["control-only", "mixed-batch"])
def test_optimizer_job_controls_allocate_a_sandbox_only_for_file_tools(action: str, with_read: bool) -> None:
    factory = FakeSandboxFactory()
    arguments = json.dumps({"action": action})
    calls = [ToolCall("control-job", OPTIMIZER_TOOL, arguments)]
    if with_read:
        calls.append(ToolCall("read-schedule", READ_TOOL, '{"path":"schedule.yaml"}'))
    provider = ScriptedProvider([ToolCallRequest(tuple(calls))], [TextDelta("Checked.")])
    controls = []

    async def execute_optimizer(current_schedule: str, received_arguments: str) -> AgentToolOutcome:
        assert factory.created == []
        controls.append((current_schedule, received_arguments))
        return AgentToolOutcome("Existing job updated.", True)

    async def collect() -> list:
        return [
            event
            async for event in run_workspace(
                provider, factory, schedule_yaml(), MESSAGES, _limits(), execute_optimizer=execute_optimizer
            )
        ]

    events = asyncio.run(collect())
    assert controls == [("", arguments)]
    assert len(factory.created) == int(with_read)
    assert all(event.ok for event in events if isinstance(event, AgentToolUse))
    if with_read:
        assert factory.created[0].closed


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

    async def execute_optimizer(current_schedule: str, received_arguments: str) -> AgentToolOutcome:
        controls.append((current_schedule, received_arguments))
        return AgentToolOutcome("Existing job updated.", True)

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
    control_result = next(event for event in events if isinstance(event, AgentToolUse) and event.name == OPTIMIZER_TOOL)
    assert control_result.ok


def test_parallel_reads_share_hydration_and_controls_do_not_resume_the_sandbox() -> None:
    batches = []

    class Backend(FakeSandboxBackend):
        @asynccontextmanager
        async def activity_batch(self):
            batches.append("start")
            try:
                yield
            finally:
                batches.append("end")

        async def write_files(self, files):
            await asyncio.sleep(0)
            await super().write_files(files)

    factory = FakeSandboxFactory(Backend)
    provider = ScriptedProvider(
        [ToolCallRequest(tuple(ToolCall(f"read-{i}", READ_TOOL, '{"path":"schedule.yaml"}') for i in range(2)))],
        [ToolCallRequest((ToolCall("status", OPTIMIZER_TOOL, '{"action":"status"}'),))],
        [TextDelta("Checked.")],
    )

    async def execute_optimizer(_schedule: str, _arguments: str) -> AgentToolOutcome:
        assert batches == ["start", "end"]
        return AgentToolOutcome("Running.", True)

    async def collect() -> list:
        return [
            event
            async for event in run_workspace(
                provider, factory, schedule_yaml(), MESSAGES, _limits(), execute_optimizer=execute_optimizer
            )
        ]

    events = asyncio.run(collect())
    assert len(factory.created) == 1
    assert factory.created[0].write_files_calls == 1
    assert factory.created[0].closed
    assert batches == ["start", "end"]
    assert all(event.ok for event in events if isinstance(event, AgentToolUse))


@pytest.mark.parametrize("failure_count", [1, 2])
def test_parallel_reads_retry_failed_hydration_before_using_the_sandbox(failure_count) -> None:
    class Backend(FakeSandboxBackend):
        hydration_attempts = 0

        async def write_files(self, files):
            self.hydration_attempts += 1
            await asyncio.sleep(0)
            if self.hydration_attempts <= failure_count:
                # A failed upload can leave a valid schedule without its reference files.
                self.files[WORKSPACE_SCHEDULE] = schedule_yaml().encode()
                raise SandboxError("Hydration upload failed.")
            await super().write_files(files)

        async def read_file(self, path, *, max_bytes=None):
            assert WORKSPACE_SOURCE_CONTEXT in self.files
            return await super().read_file(path, max_bytes=max_bytes)

    factory = FakeSandboxFactory(Backend)

    async def read() -> list:
        async with _measured_sandbox_run(factory, 1, WorkspaceMetrics(), schedule_yaml(), (), None, None) as sandbox:
            async with sandbox.activity_batch():
                results = await asyncio.gather(
                    sandbox.read_file(WORKSPACE_SCHEDULE),
                    sandbox.read_file(WORKSPACE_SCHEDULE),
                    return_exceptions=True,
                )
            results.append(await sandbox.read_file(WORKSPACE_SCHEDULE))
            return results

    results = asyncio.run(read())

    assert all(isinstance(result, SandboxError) for result in results[:failure_count])
    assert all(str(result) == "Hydration upload failed." for result in results[:failure_count])
    assert results[failure_count:] == [schedule_yaml().encode()] * (3 - failure_count)
    assert len(factory.created) == 1
    assert factory.created[0].hydration_attempts == failure_count + 1
    assert factory.created[0].closed


def test_failed_bash_result_reaches_the_model_and_allows_the_next_tool_call():
    backend = FakeSandboxBackend(
        "fake-1", command_handler=lambda command, *_: CommandResult("partial", "", None if command == "failed" else 0)
    )
    provider = ScriptedProvider(_run_call("failed"), _run_call("retry"), [TextDelta("Recovered.")])

    events = _collect(provider, FakeSandboxFactory(lambda _: backend))

    outcomes = [event for event in events if isinstance(event, AgentToolUse)]
    assert [outcome.ok for outcome in outcomes] == [False, True]
    assert outcomes[0].result == "partial\n\nCommand terminated without an exit code"
    assert any(
        message.get("role") == "tool" and message.get("content") == outcomes[0].result
        for message in provider.requests[1][0]
    )
    assert backend.commands == [("failed", None), ("retry", None)]


def test_hydration_uploads_every_reference_in_one_request():
    factory = FakeSandboxFactory(lambda sandbox_id: FakeSandboxBackend(sandbox_id, command_handler=_rename_handler))

    _collect(ScriptedProvider(_run_call(), [TextDelta("Done.")]), factory)

    backend = factory.created[0]
    # Hydration now runs in front of the first tool result, so per-file round trips are paid
    # by the user rather than absorbed before the turn starts.
    assert backend.write_files_calls == 1
    assert len(backend.files) > len(REFERENCE_SCHEMAS)


@pytest.mark.parametrize("newline", ["\n", "\r\n"], ids=["lf", "crlf"])
def test_hydration_keeps_bundled_example_separate_from_current_schedule(newline, tmp_path, monkeypatch):
    bundled_source = (
        Path(__file__).resolve().parents[2] / "web-frontend/public/examples/large-ward-with-87-people-2025-11.yaml"
    )
    source = tmp_path / bundled_source.name
    source.write_bytes(bundled_source.read_text(encoding="utf-8").replace("\n", newline).encode("utf-8"))
    monkeypatch.setattr("nurse_scheduling.ai.schema.SCHEDULE_EXAMPLE_SOURCE", source)
    load_schedule_example.cache_clear()
    factory = FakeSandboxFactory()
    try:
        _collect(ScriptedProvider(_run_call(), [TextDelta("Done.")]), factory)
    finally:
        load_schedule_example.cache_clear()
    files = factory.created[0].files
    example = files["/reference/examples/large-ward-with-87-people-2025-11.yaml"]
    assert example == source.read_text(encoding="utf-8").encode("utf-8")
    assert files[WORKSPACE_SCHEDULE] != example
    assert b"/reference/examples/large-ward-with-87-people-2025-11.yaml" in files[REFERENCE_SCHEMAS["core"]]


def test_hydration_places_untrusted_attachments_under_safe_paths():
    factory = FakeSandboxFactory()
    provider = ScriptedProvider(
        [ToolCallRequest((ToolCall("call-1", READ_TOOL, json.dumps({"path": WORKSPACE_SCHEDULE})),))],
        [TextDelta("Inspected.")],
    )
    unnamed = SandboxAttachment("../../staff data.bin", "application/octet-stream", b"payload")
    uploaded = SandboxAttachment("報表 (1).xlsx", "application/octet-stream", b"sheet", id="upload-id")

    _collect(provider, factory, attachments=(unnamed, uploaded))

    backend = factory.created[0]
    assert attachment_path(unnamed, 1) == "/workspace/attachments/01-staff_data.bin"
    assert attachment_path(uploaded, 2) == "/workspace/attachments/upload-id-1_.xlsx"
    assert backend.files["/workspace/attachments/01-staff_data.bin"] == b"payload"
    assert backend.files["/workspace/attachments/upload-id-1_.xlsx"] == b"sheet"
    assert b"inspect_workbook" in backend.files["/reference/tools/inspect_xlsx.py"]
    assert b"inspect_pdf" in backend.files["/reference/tools/inspect_pdf.py"]


def test_hydration_loads_and_delivers_each_persisted_file_before_reading_the_next():
    actions = []
    payloads = {"one": b"first", "two": b"second"}

    class Backend(FakeSandboxBackend):
        async def write_file(self, path, content):
            actions.append(("write", path, content))
            await super().write_file(path, content)

    async def load(upload):
        actions.append(("load", upload.id))
        return payloads[upload.id]

    backend = Backend("hydration")
    uploads = tuple(SandboxAttachment(name, "text/plain", data, id=name).reference() for name, data in payloads.items())
    asyncio.run(hydrate_sandbox(backend, schedule_yaml(), uploads, load_attachment=load))

    assert actions == [
        ("load", "one"),
        ("write", "/workspace/attachments/one-one", b"first"),
        ("load", "two"),
        ("write", "/workspace/attachments/two-two", b"second"),
    ]
    assert backend.write_files_calls == 1


def test_hydration_keeps_optimizer_result_outside_user_attachments():
    factory = FakeSandboxFactory()
    provider = ScriptedProvider(
        [ToolCallRequest((ToolCall("call-1", READ_TOOL, json.dumps({"path": WORKSPACE_OPTIMIZER_RESULT})),))],
        [TextDelta("Inspected.")],
    )

    _collect(provider, factory, optimizer_result=b"workbook")

    backend = factory.created[0]
    assert backend.files[WORKSPACE_OPTIMIZER_RESULT] == b"workbook"
    assert not any(path.startswith("/workspace/attachments/") for path in backend.files)
    context = json.loads(backend.files[WORKSPACE_RESULT_CONTEXT])
    assert context["schema_version"] == 1
    assert context["people"] == ["P1", "P2"]
    assert b"inspect_optimizer_result.py" in backend.files["/reference/tools/README.md"]


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

    tool_use = next(event for event in events if isinstance(event, AgentToolUse))
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

    tool_use = next(event for event in events if isinstance(event, AgentToolUse))
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

        async def read_file(self, path: str, *, max_bytes: int | None = None) -> bytes:
            self.read_paths.append(path)
            return await super().read_file(path, max_bytes=max_bytes)

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
        async def read_file(self, path: str, *, max_bytes: int | None = None) -> bytes:
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

    tools = [event for event in events if isinstance(event, AgentToolUse)]
    assert not tools[0].ok
    # The browser receives the same check as the model, and only a valid copy as a preview.
    assert tools[0].details["schedule_check"]["ok"] is False
    assert tools[0].result.endswith("\n\n" + tools[0].details["schedule_check"]["text"])
    assert tools[0].details["schedule_yaml"] is None
    assert tools[1].details["schedule_check"]["ok"] is True
    assert "description: Head" in tools[1].details["schedule_yaml"]
    assert "Your edits are kept" in tools[0].result
    assert "last-accepted-schedule.yaml" in tools[0].result
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

    tools = [event for event in events if isinstance(event, AgentToolUse)]
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

    with pytest.raises(SandboxCandidateError, match="trusted schedule validation"):
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

    with pytest.raises(SandboxTurnTimeoutError, match="0.01-second limit"):
        _collect(WaitingProvider(), factory, turn_timeout_seconds=0.01)

    assert factory.created == []


def test_turn_deadline_closes_the_workspace_while_waiting_for_the_next_response():
    class WaitingAfterRead:
        requests = 0

        async def stream_events(self, _messages, tools=None):
            self.requests += 1
            if self.requests == 1:
                yield ToolCallRequest((ToolCall("read", READ_TOOL, '{"path":"/workspace/schedule.yaml"}'),))
            else:
                await asyncio.Event().wait()
                yield TextDelta("unreachable")

    provider = WaitingAfterRead()
    factory = FakeSandboxFactory()
    with pytest.raises(SandboxTurnTimeoutError):
        _collect(provider, factory, turn_timeout_seconds=0.2)
    assert provider.requests == 2
    assert len(factory.created) == 1
    assert factory.created[0].closed


def test_terminal_command_timeout_is_reported_before_any_further_sandbox_operation():
    from nurse_scheduling.ai.workspace import SandboxCommandTimeoutError

    def timeout(_command, _timeout, backend):
        backend.closed = True
        return CommandResult("", "", 124, timed_out=True, sandbox_terminated=True)

    factory = FakeSandboxFactory(lambda sandbox_id: FakeSandboxBackend(sandbox_id, command_handler=timeout))
    provider = ScriptedProvider(
        [
            ToolCallRequest(
                (
                    ToolCall("wait", BASH_TOOL, '{"command":"sleep 30","timeout":40}'),
                    ToolCall("next", READ_TOOL, '{"path":"/workspace/schedule.yaml"}'),
                )
            ),
        ]
    )
    events = []
    batches = []

    async def collect():
        with pytest.raises(SandboxCommandTimeoutError, match="Command timed out after 10 seconds"):
            async for event in run_workspace(
                provider,
                factory,
                schedule_yaml(),
                MESSAGES,
                _limits(),
                observe_tool_batch=batches.append,
            ):
                events.append(event)

    asyncio.run(collect())
    assert len(provider.requests) == 1
    assert factory.created[0].commands == [("sleep 30", 10)]
    assert [event.name for event in events if isinstance(event, AgentToolStart)] == [BASH_TOOL]
    outcomes = [event for event in events if isinstance(event, AgentToolUse)]
    assert len(outcomes) == 1
    assert not outcomes[0].ok
    assert outcomes[0].result == "Command timed out after 10 seconds"
    assert batches[0].call_count == 1
    assert not any(isinstance(event, AgentProposal) for event in events)


def test_recovered_command_timeout_keeps_files_and_allows_the_agent_to_continue():
    factory = FakeSandboxFactory(
        lambda sandbox_id: FakeSandboxBackend(
            sandbox_id,
            command_handler=lambda *_: CommandResult("partial\n", "", 124, timed_out=True),
        )
    )
    provider = ScriptedProvider(
        _run_call("slow"),
        [ToolCallRequest((ToolCall("read", READ_TOOL, '{"path":"/workspace/schedule.yaml"}'),))],
        [TextDelta("The command timed out. I can still read the schedule.")],
    )
    events = _collect(provider, factory)
    outcomes = [event for event in events if isinstance(event, AgentToolUse)]
    assert [event.ok for event in outcomes] == [False, True]
    assert "partial" in outcomes[0].result
    assert "Command timed out" in outcomes[0].result
    assert "P1" in outcomes[1].result
    assert factory.created[0].files[WORKSPACE_SCHEDULE] == schedule_yaml().encode()
    assert len(provider.requests) == 3
    assert not any(isinstance(event, AgentProposal) for event in events)


@pytest.mark.parametrize("has_result", [False, True])
def test_uncompilable_draft_keeps_yaml_without_a_source_context(has_result):
    backend = FakeSandboxBackend("draft")
    context = json.dumps({"schema_version": 1, "source_sha256": "submitted"}).encode() if has_result else None
    asyncio.run(
        hydrate_sandbox(
            backend, "not a schedule", optimizer_result=b"workbook" if has_result else None, optimizer_context=context
        )
    )
    assert backend.files[WORKSPACE_SCHEDULE] == b"not a schedule"
    assert WORKSPACE_SOURCE_CONTEXT not in backend.files
    if has_result:
        assert backend.files[WORKSPACE_RESULT_CONTEXT] == context


@pytest.mark.parametrize("new_schedule", [False, True])
def test_accepted_schedule_edits_refresh_request_inspection_context(new_schedule):
    async def check():
        base = (
            (Path(__file__).parent / "ai_eval/fixtures/new-schedule.yaml").read_text(encoding="utf-8")
            if new_schedule
            else schedule_yaml()
        )
        backend = FakeSandboxBackend("context-refresh")
        archived = b'{"source_sha256":"optimizer-submission"}'
        await hydrate_sandbox(backend, base, optimizer_result=b"workbook", optimizer_context=archived)
        tracker = _ScheduleCandidateTracker(backend, base, SCHEDULE_BYTE_LIMIT)
        payload = base_schedule_payload()
        payload["preferences"].append(
            {"type": "shift request", "person": ["P2"], "date": ["FIRST"], "shiftType": ["N"], "weight": 2}
        )
        await backend.write_file(WORKSPACE_SCHEDULE, schedule_yaml(payload))
        outcome, candidate = await tracker.review_if_changed()
        assert outcome.ok and candidate is not None
        context = json.loads(backend.files[WORKSPACE_SOURCE_CONTEXT])
        counts = inspect_requests(context, backend.files[WORKSPACE_SCHEDULE])
        assert (counts["request_entries"], counts["person_date_targets"]) == (2, 2)
        assert backend.files[WORKSPACE_RESULT_CONTEXT] == archived
        if not new_schedule:
            await backend.write_file(WORKSPACE_SCHEDULE, base)
            outcome, candidate = await tracker.review_if_changed()
            assert outcome.ok and candidate == base
            restored = json.loads(backend.files[WORKSPACE_SOURCE_CONTEXT])
            assert inspect_requests(restored, backend.files[WORKSPACE_SCHEDULE])["request_entries"] == 1

    asyncio.run(check())


@pytest.mark.parametrize("invalid", [b"not a schedule", b"\xff", None])
def test_invalid_or_deleted_schedule_keeps_previous_inspection_context(invalid):
    async def check():
        base = schedule_yaml()
        backend = FakeSandboxBackend("invalid-context")
        await hydrate_sandbox(backend, base)
        previous = backend.files[WORKSPACE_SOURCE_CONTEXT]
        tracker = _ScheduleCandidateTracker(backend, base, SCHEDULE_BYTE_LIMIT)
        if invalid is None:
            del backend.files[WORKSPACE_SCHEDULE]
        else:
            await backend.write_file(WORKSPACE_SCHEDULE, invalid)
        outcome, candidate = await tracker.review_if_changed()
        assert not outcome.ok and candidate is None
        assert backend.files[WORKSPACE_SOURCE_CONTEXT] == previous
        if invalid is not None:
            with pytest.raises(ValueError, match="stale"):
                inspect_requests(json.loads(previous), invalid)

    asyncio.run(check())


def test_inspection_context_builds_off_the_event_loop_and_tolerates_a_failed_write(monkeypatch):
    async def check():
        base = schedule_yaml()
        backend = FakeSandboxBackend("context-write-failure")
        await hydrate_sandbox(backend, base)
        tracker = _ScheduleCandidateTracker(backend, base, SCHEDULE_BYTE_LIMIT)
        build_threads = []

        def build(source, workbook=None):
            build_threads.append(threading.current_thread())
            return {"source": source}

        write_file = backend.write_file

        async def fail_context_write(path, content):
            if path == WORKSPACE_SOURCE_CONTEXT:
                raise SandboxError("context write failed")
            await write_file(path, content)

        monkeypatch.setattr("nurse_scheduling.ai.workspace.build_result_context", build)
        monkeypatch.setattr(backend, "write_file", fail_context_write)
        await write_file(WORKSPACE_SCHEDULE, base.replace("description: ''", "description: Updated", 1))
        outcome, candidate = await tracker.review_if_changed()
        assert outcome.ok and candidate is not None
        assert build_threads and build_threads[0] is not threading.main_thread()

    asyncio.run(check())


def test_run_validates_and_compiles_schedules_off_the_event_loop(monkeypatch):
    calls: list[tuple[str, bool]] = []

    def recorded(name, function):
        def run(*args, **kwargs):
            calls.append((name, threading.current_thread() is threading.main_thread()))
            return function(*args, **kwargs)

        return run

    monkeypatch.setattr(
        "nurse_scheduling.ai.workspace.review_schedule_candidate", recorded("edit check", review_schedule_candidate)
    )
    monkeypatch.setattr(
        "nurse_scheduling.ai.workspace_tools.review_schedule_candidate",
        recorded("optimizer or final check", review_schedule_candidate),
    )
    monkeypatch.setattr(
        "nurse_scheduling.ai.workspace.build_result_context", recorded("inspection context", build_result_context)
    )
    optimizer_call = ToolCallRequest(
        (ToolCall("call-2", OPTIMIZER_TOOL, json.dumps({"action": "start", "timeout_seconds": 30})),)
    )
    provider = ScriptedProvider(_run_call(), [optimizer_call])
    factory = FakeSandboxFactory(lambda sandbox_id: FakeSandboxBackend(sandbox_id, command_handler=_rename_handler))

    async def execute_optimizer(_current_schedule: str, _arguments: str):
        return AgentToolOutcome("Started in the background.", True)

    async def collect() -> list:
        return [
            event
            async for event in run_workspace(
                provider, factory, schedule_yaml(), MESSAGES, _limits(), execute_optimizer=execute_optimizer
            )
        ]

    events = asyncio.run(collect())

    assert any(isinstance(event, AgentProposal) for event in events)
    # Hydration and the accepted edit compile contexts. The optimizer start and final review check the copy.
    assert sorted(name for name, _ in calls) == [
        "edit check",
        "inspection context",
        "inspection context",
        "optimizer or final check",
        "optimizer or final check",
    ]
    assert not any(on_event_loop for _, on_event_loop in calls)


def test_unchanged_schedule_does_not_rebuild_inspection_context(monkeypatch):
    async def check():
        base = schedule_yaml()
        backend = FakeSandboxBackend("unchanged-context")
        await hydrate_sandbox(backend, base)
        tracker = _ScheduleCandidateTracker(backend, base, SCHEDULE_BYTE_LIMIT)

        def unexpected_build(_source, workbook=None):
            pytest.fail("Unchanged YAML must not rebuild its compiled context")

        monkeypatch.setattr("nurse_scheduling.ai.workspace.build_result_context", unexpected_build)
        assert await tracker.review_if_changed() is None

    asyncio.run(check())


def test_accepted_incomplete_draft_keeps_yaml_without_inspection_context():
    async def check():
        base = (Path(__file__).parent / "ai_eval/fixtures/new-schedule.yaml").read_text(encoding="utf-8")
        backend = FakeSandboxBackend("incomplete-context")
        await hydrate_sandbox(backend, base)
        tracker = _ScheduleCandidateTracker(backend, base, SCHEDULE_BYTE_LIMIT)
        candidate = base.replace("description: ''", "description: Draft")
        await backend.write_file(WORKSPACE_SCHEDULE, candidate)
        outcome, accepted = await tracker.review_if_changed()
        assert outcome.ok and accepted == candidate
        assert backend.files[WORKSPACE_SCHEDULE] == candidate.encode()
        assert backend.files[WORKSPACE_LAST_ACCEPTED_SCHEDULE] == candidate.encode()
        assert WORKSPACE_SOURCE_CONTEXT not in backend.files

    asyncio.run(check())


def test_required_rule_restoration_matches_preview_workspace_context_and_optimizer():
    import hashlib

    payload = base_schedule_payload()
    payload["description"] = "Rebuilt"
    payload["preferences"] = payload["preferences"][1:]

    def rebuild(_command, _timeout, backend):
        backend.files[WORKSPACE_SCHEDULE] = schedule_yaml(payload).encode()
        return CommandResult("Built schedule", "", 0)

    factory = FakeSandboxFactory(lambda sandbox_id: FakeSandboxBackend(sandbox_id, command_handler=rebuild))
    optimizer_call = ToolCallRequest((ToolCall("optimize", OPTIMIZER_TOOL, '{"action":"start"}'),))
    provider = ScriptedProvider(_run_call(), [optimizer_call], [TextDelta("Done")])
    submitted = []

    async def execute_optimizer(current_schedule, _arguments):
        submitted.append(current_schedule)
        return AgentToolOutcome("Started", True)

    async def exercise():
        return [
            event
            async for event in run_workspace(
                provider, factory, schedule_yaml(), MESSAGES, _limits(), execute_optimizer=execute_optimizer
            )
        ]

    events = asyncio.run(exercise())
    tool = next(event for event in events if isinstance(event, AgentToolUse))
    preview = next(event for event in events if isinstance(event, AgentScheduleChange)).schedule_yaml
    proposal = next(event for event in events if isinstance(event, AgentProposal)).text
    backend = factory.created[0]
    assert tool.ok
    assert "restored the required" in tool.result
    assert tool.details["schedule_check"]["text"] in tool.result
    assert proposal == preview == backend.files[WORKSPACE_SCHEDULE].decode() == submitted[0]
    assert backend.files[WORKSPACE_LAST_ACCEPTED_SCHEDULE] == proposal.encode()
    assert (
        json.loads(backend.files[WORKSPACE_SOURCE_CONTEXT])["source_sha256"]
        == hashlib.sha256(proposal.encode()).hexdigest()
    )
    assert proposal.count("type: at most one shift per day") == 1


@pytest.mark.parametrize("change", [None, "schedule", "bytes", "path", "removed"])
def test_analysis_hydration_requires_the_same_source_inputs(change):
    from dataclasses import replace

    from nurse_scheduling.ai.workspace import WORKSPACE_ANALYSIS, AgentAnalysis, analysis_source_sha256

    source = schedule_yaml()
    # Without a retained upload ID, the bytes identify the file.
    uploads = (SandboxAttachment("source.csv", "text/csv", b"P1,D"),)
    notes = AgentAnalysis(analysis_source_sha256(source, uploads), b"P1 requests D. User confirmation pending.")
    if change == "schedule":
        source += "\n"
    elif change == "bytes":
        uploads = (replace(uploads[0], data=b"P1,N"),)
    elif change == "path":
        uploads = (replace(uploads[0], filename="renamed.csv"),)
    elif change == "removed":
        uploads = ()
    backend = FakeSandboxBackend("new-workspace")
    asyncio.run(hydrate_sandbox(backend, source, uploads, analysis=notes))
    assert (WORKSPACE_ANALYSIS in backend.files) is (change is None)
    if change is None:
        assert backend.files[WORKSPACE_ANALYSIS] == notes.content


def test_analysis_hydration_accepts_the_persisted_reference_of_a_retained_upload():
    from nurse_scheduling.ai.workspace import WORKSPACE_ANALYSIS, AgentAnalysis, analysis_source_sha256

    source = schedule_yaml()
    upload = SandboxAttachment("source.csv", "text/csv", b"P1,D", id="source")
    notes = AgentAnalysis(analysis_source_sha256(source, (upload,)), b"P1 requests D. User confirmation pending.")

    async def load(_attachment):
        return upload.data

    backend = FakeSandboxBackend("new-workspace")
    asyncio.run(hydrate_sandbox(backend, source, (upload.reference(),), load_attachment=load, analysis=notes))
    assert backend.files[WORKSPACE_ANALYSIS] == notes.content


@pytest.mark.parametrize(
    "content",
    [b"Mapping: black cells mean 11m.", b"x" * (65536 + 1), b"\xff"],
    ids=["valid-notes", "oversized-notes", "invalid-utf8"],
)
def test_analysis_capture_is_bounded_and_does_not_execute_or_change_the_schedule(content):
    from nurse_scheduling.ai.workspace import WORKSPACE_ANALYSIS, AgentAnalysis

    def save_notes(_command, _timeout, backend):
        backend.files[WORKSPACE_ANALYSIS] = content
        return CommandResult("Saved notes", "", 0)

    factory = FakeSandboxFactory(lambda sandbox_id: FakeSandboxBackend(sandbox_id, command_handler=save_notes))
    events = _collect(ScriptedProvider(_run_call(), [TextDelta("Please confirm the mapping.")]), factory)
    notes = [event for event in events if isinstance(event, AgentAnalysis)]
    assert bool(notes) is (content.startswith(b"Mapping"))
    if notes:
        assert notes[0].content == content
    assert not any(isinstance(event, AgentProposal) for event in events)
    assert factory.created[0].files[WORKSPACE_SCHEDULE] == schedule_yaml().encode()


@pytest.mark.parametrize(
    "rejected",
    [b"", b"not: [valid", b"\xff", b"x" * (SCHEDULE_BYTE_LIMIT + 1), None],
    ids=["truncated", "malformed", "encoding", "oversized", "deleted"],
)
def test_rejected_schedule_keeps_the_draft_and_last_accepted_copy(rejected):
    async def check():
        base = schedule_yaml()
        backend = FakeSandboxBackend("recover-write")
        await hydrate_sandbox(backend, base)
        tracker = _ScheduleCandidateTracker(backend, base, SCHEDULE_BYTE_LIMIT)
        accepted = base.replace("description: ''", "description: Accepted", 1)
        await backend.write_file(WORKSPACE_SCHEDULE, accepted)
        assert (await tracker.review_if_changed())[0].ok
        if rejected is None:
            del backend.files[WORKSPACE_SCHEDULE]
        else:
            await backend.write_file(WORKSPACE_SCHEDULE, rejected)
        outcome, candidate = await tracker.review_if_changed()
        assert not outcome.ok and candidate is None
        assert backend.files.get(WORKSPACE_SCHEDULE) == rejected
        assert backend.files[WORKSPACE_LAST_ACCEPTED_SCHEDULE] == accepted.encode()
        assert "last-accepted-schedule.yaml" in outcome.text
        assert tracker.rejection is not None
        repaired = backend.files[WORKSPACE_LAST_ACCEPTED_SCHEDULE].decode().replace("Accepted", "Repaired", 1)
        await backend.write_file(WORKSPACE_SCHEDULE, repaired)
        assert (await tracker.review_if_changed())[0].ok
        assert tracker.rejection is None
        assert backend.files[WORKSPACE_LAST_ACCEPTED_SCHEDULE] == repaired.encode()

    asyncio.run(check())


def test_valid_schedule_is_kept_when_a_later_command_assertion_fails():
    updated = schedule_yaml().replace("description: ''", "description: Accepted", 1)

    def edit(_command, _timeout, backend):
        backend.files[WORKSPACE_SCHEDULE] = updated.encode()
        return CommandResult("", "AssertionError in a later audit", 1)

    factory = FakeSandboxFactory(lambda sid: FakeSandboxBackend(sid, command_handler=edit))
    events = _collect(ScriptedProvider(_run_call(), [TextDelta("Updated.")]), factory)
    tool = next(event for event in events if isinstance(event, AgentToolUse))
    assert not tool.ok
    assert tool.details["schedule_check"]["ok"]
    assert factory.created[0].files[WORKSPACE_SCHEDULE] == updated.encode()
    assert next(event for event in events if isinstance(event, AgentProposal)).text == updated


@pytest.mark.parametrize("draft_changed", [False, True], ids=["unchanged-draft", "rejected-draft"])
@pytest.mark.parametrize("tampered", [b"forged: schedule", None], ids=["overwritten", "deleted"])
def test_last_accepted_copy_is_restored_from_server_state(draft_changed, tampered):
    def tamper(_command, _timeout, backend):
        backup = WORKSPACE_LAST_ACCEPTED_SCHEDULE
        if tampered is None:
            del backend.files[backup]
        else:
            backend.files[backup] = tampered
        if draft_changed:
            backend.files[WORKSPACE_SCHEDULE] = b"dates: ["
        return CommandResult("", "", 0)

    from nurse_scheduling.ai.workspace_tools import WorkspaceTools

    async def check():
        base = schedule_yaml()
        backend = FakeSandboxBackend("tampered-backup", command_handler=tamper)
        await hydrate_sandbox(backend, base)
        tools = WorkspaceTools(backend, base, _limits(), None)
        assert backend.files[WORKSPACE_LAST_ACCEPTED_SCHEDULE] == base.encode()
        await tools._execute(BASH_TOOL, json.dumps({"command": "tamper"}))
        assert backend.files[WORKSPACE_LAST_ACCEPTED_SCHEDULE] == base.encode()
        assert backend.files[WORKSPACE_SCHEDULE] == (b"dates: [" if draft_changed else base.encode())
        assert (tools.candidate_tracker.rejection is not None) == draft_changed

    asyncio.run(check())


def test_group_rename_can_remain_invalid_between_tool_calls():
    base = schedule_yaml()

    def edit(command, _timeout, backend):
        current = backend.files[WORKSPACE_SCHEDULE].decode()
        if command == "rename":
            current = current.replace("id: FIRST", "id: OPENING", 1)
        else:
            assert "id: OPENING" in current
            assert "- FIRST" in current
            assert backend.files[WORKSPACE_LAST_ACCEPTED_SCHEDULE] == base.encode()
            current = current.replace("- FIRST", "- OPENING")
        backend.files[WORKSPACE_SCHEDULE] = current.encode()
        return CommandResult("updated", "", 0)

    provider = ScriptedProvider(_run_call("rename"), _run_call("references"), [TextDelta("Renamed the group.")])
    factory = FakeSandboxFactory(lambda sid: FakeSandboxBackend(sid, command_handler=edit))
    events = _collect(provider, factory)
    tools = [event for event in events if isinstance(event, AgentToolUse)]
    assert not tools[0].details["schedule_check"]["ok"]
    assert tools[1].details["schedule_check"]["ok"]
    assert "last-accepted-schedule.yaml" in tools[0].result
    result = next(event for event in events if isinstance(event, AgentProposal)).text
    assert "FIRST" not in result
    assert "id: OPENING" in result
    assert factory.created[0].files[WORKSPACE_LAST_ACCEPTED_SCHEDULE] == result.encode()
    assert any(
        message.get("role") == "tool" and "last-accepted-schedule.yaml" in str(message.get("content"))
        for message in provider.requests[1][0]
    )


def test_restoring_the_last_accepted_copy_clears_the_rejection():
    from nurse_scheduling.ai.workspace_tools import WorkspaceTools

    async def check():
        base = schedule_yaml()
        backend = FakeSandboxBackend("restore-accepted")
        await hydrate_sandbox(backend, base)
        tools = WorkspaceTools(backend, base, _limits(), None)
        accepted = base.replace("description: ''", "description: Accepted", 1)
        await tools._execute(WRITE_TOOL, json.dumps({"path": WORKSPACE_SCHEDULE, "content": accepted}))
        await tools._execute(WRITE_TOOL, json.dumps({"path": WORKSPACE_SCHEDULE, "content": "dates: ["}))
        assert tools.candidate_tracker.rejection is not None
        restored = backend.files[WORKSPACE_LAST_ACCEPTED_SCHEDULE].decode()
        result = await tools._execute(WRITE_TOOL, json.dumps({"path": WORKSPACE_SCHEDULE, "content": restored}))
        assert result.ok
        assert tools.candidate_tracker.rejection is None
        assert backend.files[WORKSPACE_SCHEDULE] == accepted.encode()
        assert result.details["schedule_yaml"] == accepted

    asyncio.run(check())


@pytest.mark.parametrize(
    "rejected",
    [b"dates: [", b"", b"\xff", b"x" * (SCHEDULE_BYTE_LIMIT + 1), None],
    ids=["malformed", "truncated", "encoding", "oversized", "deleted"],
)
@pytest.mark.parametrize(
    "tool,arguments",
    [
        (READ_TOOL, {"path": WORKSPACE_LAST_ACCEPTED_SCHEDULE}),
        (BASH_TOOL, {"command": "cat schedule.yaml"}),
        (WRITE_TOOL, {"path": "notes.txt", "content": "notes"}),
    ],
)
def test_pending_rejection_does_not_fail_unrelated_successful_commands(tool, arguments, rejected):
    from nurse_scheduling.ai.workspace_tools import WorkspaceTools

    async def check():
        base = schedule_yaml()

        def command(name, _timeout, backend):
            if name == "break":
                if rejected is None:
                    backend.files.pop(WORKSPACE_SCHEDULE, None)
                else:
                    backend.files[WORKSPACE_SCHEDULE] = rejected
            return CommandResult("read", "", 0)

        backend = FakeSandboxBackend("pending-rejection", command_handler=command)
        await hydrate_sandbox(backend, base)
        tools = WorkspaceTools(backend, base, _limits(), None)
        bad_edit = {"command": "break"}
        assert not (await tools._execute(BASH_TOOL, json.dumps(bad_edit))).ok
        result = await tools._execute(tool, json.dumps(arguments))
        assert result.ok
        assert result.details["schedule_check"]["ok"] is False
        assert tools.candidate_tracker.rejection in result.text
        assert tools.candidate_tracker.rejection is not None
        assert backend.files.get(WORKSPACE_SCHEDULE) == rejected
        assert backend.files[WORKSPACE_LAST_ACCEPTED_SCHEDULE] == base.encode()

        async def unexpected_start(*_):
            pytest.fail("An unresolved rejected edit must block optimization")

        tools.execute_optimizer = unexpected_start
        blocked = await tools._execute(OPTIMIZER_TOOL, '{"action":"start"}')
        assert not blocked.ok
        # Repeating the same draft must keep the failed check visible.
        repeated = await tools._execute(BASH_TOOL, json.dumps(bad_edit))
        assert not repeated.details["schedule_check"]["ok"]
        assert tools.candidate_tracker.rejection is not None

    asyncio.run(check())


def test_pending_rejection_preserves_real_command_failure():
    from nurse_scheduling.ai.workspace_tools import WorkspaceTools

    async def check():
        backend = FakeSandboxBackend("failed-command", command_handler=lambda *_: CommandResult("", "missing file", 1))
        base = schedule_yaml()
        await hydrate_sandbox(backend, base)
        tools = WorkspaceTools(backend, base, _limits(), None)
        await tools._execute(WRITE_TOOL, json.dumps({"path": WORKSPACE_SCHEDULE, "content": "dates: ["}))
        result = await tools._execute(BASH_TOOL, json.dumps({"command": "cat missing"}))
        assert not result.ok
        assert "missing file" in result.text
        assert tools.candidate_tracker.rejection is not None

    asyncio.run(check())

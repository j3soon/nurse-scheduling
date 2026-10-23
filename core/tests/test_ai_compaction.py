"""Tests for automatic context compaction and overflow recovery."""

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
import hashlib
import json
from dataclasses import asdict

import pytest

from nurse_scheduling.ai.agent import Agent
from nurse_scheduling.ai.agent_loop import agent_loop
from nurse_scheduling.ai.agent_types import AgentCompaction, AgentText, AgentTool, AgentToolOutcome
from nurse_scheduling.ai.compaction import COMPACTION_MANIFEST, ContextCompactor, estimate_context_tokens
from nurse_scheduling.ai.context import (
    apply_compaction,
    interrupted_entries,
    prepare_provider_request,
    projected_history,
    retained_entries,
)
from nurse_scheduling.ai.provider import (
    ProviderCall,
    ProviderContextOverflowError,
    ProviderError,
    ResponseEnd,
    TextDelta,
    TokenUsage,
    ToolCallRequest,
)
from nurse_scheduling.ai.system_prompt import load_system_prompt_entries, load_system_prompt_sections
from nurse_scheduling.ai.transcript import (
    AssistantMessage,
    CompactionEntry,
    ProviderIdentity,
    ToolCall,
    ToolResultImage,
    ToolResultMessage,
    UserMessage,
    entry_from_record,
    entry_record,
)


class CompactionProvider:
    context_tokens = 6000
    identity = ProviderIdentity("https://provider.example/v1", "model")

    def __init__(self, *, fail_summary=None, overflow=False):
        self.requests = []
        self.summaries = []
        self.fail_summary = fail_summary
        self.overflow = overflow
        self.summary_started = asyncio.Event()

    async def stream_events(self, messages, tools=None):
        if messages[0]["role"] == "system" and str(messages[0]["content"]).startswith("Summarize the supplied"):
            self.summaries.append((messages, tools))
            self.summary_started.set()
            if self.fail_summary == "cancel":
                await asyncio.Event().wait()
            if self.fail_summary == "error":
                raise ProviderError("summary failed")
            yield ProviderCall("summary-" + str(len(self.summaries)), "model", "reported", "0.01")
            yield TextDelta("Goal: keep nights. Files: /workspace/schedule.yaml. Pending: inspect P1.")
            if self.fail_summary == "tool":
                yield ToolCallRequest((ToolCall("bad", "read", "{}"),))
            if self.fail_summary != "eof":
                yield ResponseEnd("length" if self.fail_summary == "length" else "stop")
            return
        self.requests.append((messages, tools))
        if self.overflow:
            raise ProviderContextOverflowError("maximum context length")
        yield TextDelta("Done.")
        yield ResponseEnd("stop")


def history(size=26000):
    return [
        {"role": "system", "content": "Scheduling assistant"},
        {"role": "user", "content": "Keep nights. " + "x" * size},
        {"role": "assistant", "content": "Earlier answer"},
        {"role": "user", "content": "Inspect P1"},
    ]


async def collect(stream):
    return [event async for event in stream]


def test_auto_compaction_preserves_current_request_and_persists_the_summary():
    provider = CompactionProvider()
    messages = history()
    original = json.dumps(messages)
    run = []
    events = asyncio.run(collect(agent_loop(provider, messages, [], run_messages=run)))
    assert [event.text for event in events if isinstance(event, AgentText)] == ["Done."]
    assert provider.summaries
    assert all(tools == [] for _request, tools in provider.summaries)
    assert all(estimate_context_tokens(request, []) < 4500 for request, _tools in provider.summaries)
    assert any(isinstance(event, ProviderCall) for event in events)
    (entry,) = [event.entry for event in events if isinstance(event, AgentCompaction)]
    assert entry.keep_messages > 0
    assert provider.requests[0][0][0] == messages[0]
    assert provider.requests[0][0][-1] == messages[-1]
    assert "Goal: keep nights" in str(provider.requests[0][0])
    assert "x" * 1000 not in str(provider.requests[0][0])
    assert json.dumps(messages) == original
    transcript = [
        UserMessage(messages[1]["content"]),
        AssistantMessage("Earlier answer"),
        UserMessage("Inspect P1"),
        *run,
    ]
    restored = [
        entry_from_record(kind, payload)
        for kind, payload in json.loads(json.dumps([entry_record(e) for e in retained_entries(transcript)]))
    ]
    request = prepare_provider_request(
        projected_history(restored), [UserMessage("Continue")], provider=provider.identity
    )
    assert "Goal: keep nights" in str(request) and "x" * 1000 not in str(request)
    assert request[-1]["content"] == "Continue"


def test_context_compaction_tool_continuation_keeps_native_tool_pairs_and_status():
    provider = CompactionProvider()
    call = ToolCall("read-1", "read", '{"path":"/workspace/schedule.yaml"}')
    native = {"thinking_blocks": [{"type": "redacted_thinking", "data": "opaque"}]}
    entries = [
        AssistantMessage("Checking", "tool_use", "", (call,), native, provider.identity),
        ToolResultMessage(call.id, call.name, "P1 exists", True, ToolResultImage("image/png", b"png")),
    ]
    messages = prepare_provider_request(history()[:-1], entries, _preserve_native=True)
    messages.append(
        {"role": "user", "content": "[Current status]\nCurrent schedule is active", "_current_status": True}
    )
    events = asyncio.run(collect(ContextCompactor(provider).compact(messages, [])))
    (entry,) = [event.entry for event in events if isinstance(event, AgentCompaction)]
    request = prepare_provider_request(apply_compaction(messages, entry), [], provider=provider.identity)
    assert request[-1]["content"].startswith("[Current status]")
    assistant = next(message for message in request if message.get("tool_calls"))
    assert assistant["thinking_blocks"] == native["thinking_blocks"]
    index = request.index(assistant)
    assert request[index + 1]["tool_call_id"] == call.id
    assert request[index + 2]["content"][-1]["type"] == "image_url"
    # Removing transient images must not move the saved boundary across a tool pair.
    transcript = [UserMessage("old"), AssistantMessage("old answer"), *retained_entries(entries), entry]
    restored = projected_history(transcript)
    assert any(message.get("tool_call_id") == call.id for message in restored)


@pytest.mark.parametrize("failure", ["error", "length", "tool", "eof"])
def test_failed_summary_keeps_original_context(failure):
    provider = CompactionProvider(fail_summary=failure)
    messages = history()
    events = asyncio.run(collect(agent_loop(provider, messages, [])))
    assert not any(isinstance(event, AgentCompaction) for event in events)
    assert provider.requests[0][0] == messages
    assert len(provider.summaries) == 1


def test_stop_during_summary_discards_partial_summary_and_closes_the_agent():
    async def exercise():
        provider = CompactionProvider(fail_summary="cancel")
        agent = Agent()
        task = asyncio.create_task(collect(agent.prompt(provider, history(), [])))
        await provider.summary_started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not agent.state.is_streaming
        assert not any(isinstance(entry, CompactionEntry) for entry in agent.state.messages)

    asyncio.run(exercise())


def test_context_overflow_retries_once_without_repeating_tools():
    class Provider(CompactionProvider):
        context_tokens = 16000

        async def stream_events(self, messages, tools=None):
            if messages[0]["content"].startswith("Summarize the supplied"):
                async for event in super().stream_events(messages, tools):
                    yield event
                return
            self.requests.append((messages, tools))
            if len(self.requests) == 1:
                yield ToolCallRequest((ToolCall("read", "read", "{}"),))
                yield ResponseEnd("tool_calls")
            elif len(self.requests) == 2:
                raise ProviderContextOverflowError("context_length_exceeded")
            else:
                yield TextDelta("Recovered")
                yield ResponseEnd("stop")

    provider = Provider()
    executed = []

    async def execute(arguments):
        executed.append(arguments)
        return AgentToolOutcome("P1 result", True)

    tool = AgentTool({"type": "function", "function": {"name": "read", "parameters": {"type": "object"}}}, execute)
    events = asyncio.run(collect(agent_loop(provider, history(8000), [tool])))
    assert executed == ["{}"]
    assert len(provider.requests) == 3
    assert any(isinstance(event, AgentCompaction) for event in events)
    assert "P1 result" in str(provider.requests[-1])


def test_repeated_overflow_stops_after_one_compact_and_retry():
    provider = CompactionProvider(overflow=True)
    provider.context_tokens = 16000
    with pytest.raises(ProviderContextOverflowError):
        asyncio.run(collect(agent_loop(provider, history(8000), [])))
    assert len(provider.requests) == 2
    assert len(provider.summaries) == 1


def test_usage_estimates_follow_trailing_results_and_reset_after_compaction_or_model_switch():
    identity = ProviderIdentity("https://provider.example/v1", "model")
    entries = [
        UserMessage("read"),
        AssistantMessage("Checking", provider=identity, usage=asdict(TokenUsage(9000, 100, 9100))),
        UserMessage("follow up"),
    ]
    messages = prepare_provider_request([], entries, _preserve_native=True)
    assert estimate_context_tokens(messages, [], asdict(identity)) > 9100
    assert estimate_context_tokens(messages, [], asdict(ProviderIdentity(identity.endpoint, "other"))) < 100
    compacted = apply_compaction(messages, CompactionEntry("Goal: continue", 2, 9200))
    assert estimate_context_tokens(compacted, [], asdict(identity)) < 100


def test_failed_run_does_not_replay_a_summary_of_discarded_workspace_claims():
    entries = [UserMessage("Edit"), AssistantMessage("Changed"), CompactionEntry("Changed P1", 0, 9000)]
    failed = interrupted_entries(entries, "error")
    assert not failed[2].valid
    projected = projected_history(failed)
    assert "Changed P1" not in str(projected) and "interrupted" in str(projected)


def test_compaction_prompt_manifest_matches_the_shipped_prompt():
    entries = load_system_prompt_entries(COMPACTION_MANIFEST)
    (section,) = load_system_prompt_sections(entries)
    assert entries[0]["sha256"] == hashlib.sha256(section.encode()).hexdigest()
    assert "exact file paths" in section and "unresolved questions" in section


def test_unknown_model_limit_keeps_existing_request_behavior():
    provider = CompactionProvider()
    provider.context_tokens = None
    events = asyncio.run(collect(agent_loop(provider, history(), [])))
    assert not provider.summaries
    assert not any(isinstance(event, AgentCompaction) for event in events)


def test_retention_keeps_a_summary_and_its_referenced_tool_exchange_together():
    from nurse_scheduling.ai.context import drop_oldest_exchange

    call = ToolCall("read", "read", "{}")
    entries = [
        UserMessage("Old"),
        AssistantMessage("Old answer"),
        UserMessage("Read"),
        AssistantMessage("Checking", "tool_use", tool_calls=(call,)),
        ToolResultMessage(call.id, call.name, "result", True),
        CompactionEntry("Earlier constraints", 3, 5000),
        AssistantMessage("Done"),
    ]
    drop_oldest_exchange(entries)
    assert entries[0] == UserMessage("Read")
    assert drop_oldest_exchange(entries) == []
    assert "result" in str(projected_history(entries))
    entries.extend([UserMessage("New"), AssistantMessage("New answer")])
    removed = drop_oldest_exchange(entries)
    assert any(isinstance(entry, CompactionEntry) for entry in removed)
    assert entries == [UserMessage("New"), AssistantMessage("New answer")]


def test_typed_status_text_is_conversation_data():
    provider = CompactionProvider()
    messages = history()
    messages[-1]["content"] = "[Current status]\nPlease inspect P1"
    events = asyncio.run(collect(ContextCompactor(provider).compact(messages, [])))
    (entry,) = [event.entry for event in events if isinstance(event, AgentCompaction)]
    assert apply_compaction(messages, entry)[-1] == messages[-1]


def test_session_api_checkpoints_compaction_and_accounts_for_summary_calls():
    from . import test_ai_basic as basic

    provider = CompactionProvider()
    provider.context_tokens = 32000
    app = basic.create_test_app(settings=basic.make_settings(), provider=provider)
    with basic.AuthenticatedTestClient(app) as client:
        session_id = basic.create_session(client, basic.schedule_yaml())
        store = app.state.session_store
        session = store._sessions[session_id]
        snapshot = store.begin(session_id, session.owner_token)
        store.finish(
            session_id, [UserMessage("Keep nights " + "x" * 100000), AssistantMessage("Old answer")], snapshot=snapshot
        )
        response = client.post(f"/sessions/{session_id}/messages", json={"message": "Inspect P1"})
        assert response.status_code == 200
        assert not session.active
        assert any(isinstance(entry, CompactionEntry) for entry in session.transcript)
        events = basic.parse_sse(response.text)
        assert [data["text"] for kind, data in events if kind == "delta"] == ["Done."]
        assert any(kind == "provider_call" and data.get("cost_usd") == "0.01" for kind, data in events)
        assert "x" * 1000 not in str(session.history)


def test_large_tool_result_triggers_compaction_before_the_next_model_turn():
    class Provider(CompactionProvider):
        context_tokens = 16000

        async def stream_events(self, messages, tools=None):
            if str(messages[0]["content"]).startswith("Summarize the supplied"):
                async for event in super().stream_events(messages, tools):
                    yield event
                return
            self.requests.append((messages, tools))
            if len(self.requests) == 1:
                yield ToolCallRequest((ToolCall("read", "read", '{"path":"/workspace/schedule.yaml"}'),))
                yield ResponseEnd("tool_calls")
            else:
                yield TextDelta("Done")
                yield ResponseEnd("stop")

    provider = Provider()
    executed = []

    async def execute(arguments):
        executed.append(arguments)
        return AgentToolOutcome("P1 tool result " + "x" * 60000, True)

    tool = AgentTool({"type": "function", "function": {"name": "read", "parameters": {"type": "object"}}}, execute)
    events = asyncio.run(collect(agent_loop(provider, history(1000), [tool])))
    assert len(executed) == 1 and len(provider.requests) == 2
    assert any(isinstance(event, AgentCompaction) for event in events)
    assert "P1 tool result" in str(provider.summaries)
    assert "Tool result truncated for summary" in str(provider.summaries)
    assert "x" * 10000 not in str(provider.requests[-1])


def test_closing_after_a_summary_cost_event_closes_the_provider_before_returning():
    async def exercise():
        closed = False

        class Provider(CompactionProvider):
            async def stream_events(self, messages, tools=None):
                nonlocal closed
                try:
                    yield ProviderCall("summary", "model")
                    await asyncio.Event().wait()
                finally:
                    closed = True

        agent = Agent()
        stream = agent.prompt(Provider(), history(), [])
        assert isinstance(await anext(stream), ProviderCall)
        await stream.aclose()
        assert closed
        assert not agent.state.is_streaming

    asyncio.run(exercise())


def test_steering_received_during_compaction_reaches_the_next_provider_request():
    agent = Agent()

    class Provider(CompactionProvider):
        sent = False

        async def stream_events(self, messages, tools=None):
            if str(messages[0]["content"]).startswith("Summarize the supplied") and not self.sent:
                self.sent = True
                agent.steer("steering", "Also inspect P2")
            async for event in super().stream_events(messages, tools):
                yield event

    provider = Provider()
    agent.open_steering(True)
    asyncio.run(collect(agent.prompt(provider, history(), [], take_steering=agent.take_steering)))
    assert provider.requests[0][0][-1]["content"] == "Also inspect P2"

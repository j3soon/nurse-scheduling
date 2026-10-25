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
from nurse_scheduling.ai.agent_types import (
    AgentCompaction,
    AgentCompactionEnd,
    AgentCompactionStart,
    AgentText,
    AgentTool,
    AgentToolOutcome,
)
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
    AppEventEntry,
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
        if messages[0]["role"] == "system" and str(messages[0]["content"]).startswith(
            "You are a context summarization assistant."
        ):
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


def test_app_event_indices_survive_compaction_retention_and_restore():
    from nurse_scheduling.ai.context import SCHEDULE_CHANGED_EVENT
    from nurse_scheduling.ai.session_event_projection import RunEvents
    from nurse_scheduling.ai.sessions import SessionStore

    from .test_ai_basic import make_settings, schedule_yaml

    async def exercise():
        settings = make_settings()
        store = SessionStore(settings)
        session = store.create("owner", schedule_yaml())

        def add(*entries):
            for entry in entries:
                session._add_entry(entry)

        def prepare():
            snapshot = store.begin(session.id, "owner")
            published = []
            events = RunEvents("run", lambda event: published.append(event))
            messages, _, _ = session._prepare_run(snapshot, "Continue", None, settings, events, "question")
            events.flush()
            store.finish(session.id, [], snapshot=snapshot)
            model_input = next(event for event in published if event["type"] == "model_input")
            assert not any("_source_index" in message for message in messages)
            return [entry for entry in model_input["messages"] if entry["content"] == SCHEDULE_CHANGED_EVENT]

        add(AppEventEntry(SCHEDULE_CHANGED_EVENT), AppEventEntry(SCHEDULE_CHANGED_EVENT))
        assert [entry["index"] for entry in prepare()] == [0, 1]
        add(UserMessage("First"), AssistantMessage("First answer"), CompactionEntry("Earlier constraints", 0, 1000))
        add(AppEventEntry(SCHEDULE_CHANGED_EVENT))
        assert [entry["index"] for entry in prepare()] == [5]
        # The same pending event must retain its ID when preparation is repeated.
        assert [entry["index"] for entry in prepare()] == [5]
        add(UserMessage("Second"), AssistantMessage("Second answer"), CompactionEntry("Updated constraints", 0, 1000))
        add(AppEventEntry(SCHEDULE_CHANGED_EVENT))
        assert [entry["index"] for entry in prepare()] == [9]
        while SessionStore._drop_oldest_exchange(session):
            pass
        assert session.dropped_entries > 0
        assert [entry["index"] for entry in prepare()] == [9]
        owner, expires, state = store.recovery_state(session.id)
        recovered = SessionStore(settings)
        session = recovered.restore(
            session.id, owner, state, expires, entries=session.transcript, next_entry_seq=session.next_entry_seq
        )
        store = recovered
        assert [entry["index"] for entry in prepare()] == [9]
        add(AppEventEntry(SCHEDULE_CHANGED_EVENT))
        assert [entry["index"] for entry in prepare()] == [9, 10]

    asyncio.run(exercise())


@pytest.mark.parametrize("invalid", ["primary", "unavailable", None])
def test_live_compaction_validates_models_before_starting_paid_cases(monkeypatch, invalid):
    from nurse_scheduling.ai.models import AvailableModel

    from . import test_ai_compaction_live as live
    from .test_ai_basic import make_settings

    for key in ("AI_PROVIDER_BASE_URL", "AI_PROVIDER_API_KEY", "AI_PROVIDER_MODEL", "E2B_API_KEY"):
        monkeypatch.setenv(key, "test-only")
    settings = make_settings()
    monkeypatch.setattr(live.AiSettings, "from_env", lambda: settings)
    started = []

    async def models(_self, _credential):
        return (
            []
            if invalid == "unavailable"
            else [
                AvailableModel(
                    settings.provider_model, "Primary", context_tokens=None if invalid == "primary" else 32000
                ),
            ]
        )

    async def run_case(name, *_args):
        started.append(name)
        return {"passed": True}

    monkeypatch.setattr(live.ModelCatalog, "models", models)
    monkeypatch.setattr(live, "run_live_case", run_case)
    if invalid is None:
        live.test_real_chat_runs_preserve_context_through_compaction(monkeypatch)
        assert started == ["threshold", "repeated", "model-lock", "cancellation", "manual"]
        return
    expected = "unavailable" if invalid == "unavailable" else "context limit"
    with pytest.raises(AssertionError, match=expected):
        live.test_real_chat_runs_preserve_context_through_compaction(monkeypatch)
    assert started == []


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
    assert isinstance(events[0], AgentCompactionStart)
    end = next(event for event in events if isinstance(event, AgentCompactionEnd))
    assert end.success and not end.aborted and end.reason == "threshold"
    assert end.estimated_tokens_after < end.tokens_before
    assert events.index(end) > next(i for i, event in enumerate(events) if isinstance(event, AgentCompaction))
    (entry,) = [event.entry for event in events if isinstance(event, AgentCompaction)]
    assert end.summary == entry.summary
    assert end.keep_messages == entry.keep_messages
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


def test_compaction_keeps_a_long_current_question_with_its_trailing_status():
    provider = CompactionProvider()
    question = "Inspect the file again in this new workspace. " + "filler " * 1500
    messages = [
        *history()[:-1],
        {"role": "user", "content": question},
        {"role": "user", "content": "[Current status]\nWorkspace timezone: UTC."},
    ]
    asyncio.run(collect(agent_loop(provider, messages, [])))
    assert provider.summaries
    assert provider.requests[0][0][-2:] == messages[-2:]


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
    assert isinstance(events[0], AgentCompactionStart)
    assert next(event for event in events if isinstance(event, AgentCompactionEnd)).success is False
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


def test_session_stop_ends_compaction_before_the_terminal_event():
    import httpx

    from . import test_ai_basic as basic

    async def exercise():
        provider = CompactionProvider(fail_summary="cancel")
        provider.context_tokens = 32000
        app = basic.create_test_app(settings=basic.make_settings(), provider=provider)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://testserver", headers=basic.AI_AUTH_HEADERS
            ) as client,
        ):
            session_id = (await client.post("/sessions", json={"schedule_yaml": basic.schedule_yaml()})).json()["id"]
            store = app.state.session_store
            session = store._sessions[session_id]
            snapshot = store.begin(session_id, session.owner_token)
            store.finish(
                session_id,
                [UserMessage("Keep nights " + "x" * 100000), AssistantMessage("Old answer")],
                snapshot=snapshot,
            )
            turn = asyncio.create_task(client.post(f"/sessions/{session_id}/messages", json={"message": "Continue"}))
            await asyncio.wait_for(provider.summary_started.wait(), timeout=2)
            assert (await client.post(f"/sessions/{session_id}/stop")).status_code == 202
            response = await asyncio.wait_for(turn, timeout=2)
            events = basic.parse_sse(response.text)
            end_index = next(i for i, (kind, _) in enumerate(events) if kind == "compaction_end")
            assert events[end_index][1]["aborted"] and not events[end_index][1]["success"]
            assert end_index < next(i for i, (kind, _) in enumerate(events) if kind == "stopped")
            assert not any(isinstance(entry, CompactionEntry) for entry in session.transcript)

    asyncio.run(exercise())


def test_context_overflow_retries_once_without_repeating_tools():
    class Provider(CompactionProvider):
        context_tokens = 16000

        async def stream_events(self, messages, tools=None):
            if messages[0]["content"].startswith("You are a context summarization assistant."):
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
    sections = load_system_prompt_sections(entries)
    for entry, section in zip(entries, sections, strict=True):
        assert entry["sha256"] == hashlib.sha256(section.encode()).hexdigest()


def test_unknown_model_limit_keeps_existing_request_behavior():
    provider = CompactionProvider()
    provider.context_tokens = None
    events = asyncio.run(collect(agent_loop(provider, history(), [])))
    assert not provider.summaries
    assert not any(isinstance(event, AgentCompaction) for event in events)


@pytest.mark.parametrize("history_limit,message_limit", [(20000, 1000), (200000, 3)], ids=["characters", "messages"])
def test_unknown_model_limit_still_compacts_at_history_limits(history_limit, message_limit):
    provider = CompactionProvider()
    provider.context_tokens = None
    messages = history()
    events = asyncio.run(
        collect(agent_loop(provider, messages, [], history_limit=history_limit, message_limit=message_limit))
    )
    assert provider.summaries
    end = next(event for event in events if isinstance(event, AgentCompactionEnd))
    assert end.success and end.reason == "threshold"
    assert any(isinstance(event, AgentCompaction) for event in events)
    assert "Goal: keep nights" in str(provider.requests[0][0])
    assert provider.requests[0][0][-1] == messages[-1]


def test_failed_compaction_does_not_retry_at_history_limits_without_model_metadata():
    provider = CompactionProvider(fail_summary="error")
    provider.context_tokens = None
    compactor = ContextCompactor(provider, history_limit=20000)
    messages = history()

    async def run():
        first = await collect(compactor.compact(messages, []))
        assert any(isinstance(event, AgentCompactionEnd) and not event.success for event in first)
        assert not await collect(compactor.compact(messages, []))

    asyncio.run(run())
    assert len(provider.summaries) == 1


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
        kinds = [kind for kind, _ in events]
        assert kinds.index("compaction_start") < kinds.index("compaction_end") < kinds.index("delta")
        end_index = kinds.index("compaction_end")
        end = events[end_index][1]
        assert end["success"] and not end["aborted"]
        latest_context = [data for kind, data in events if kind == "context_usage"][-1]
        assert latest_context["used_tokens"] > end["estimated_tokens_after"]
        assert latest_context["used_tokens"] < end["tokens_before"]
        assert "x" * 1000 not in str(session.history)


def test_large_tool_result_triggers_compaction_before_the_next_model_turn():
    class Provider(CompactionProvider):
        context_tokens = 16000

        async def stream_events(self, messages, tools=None):
            if str(messages[0]["content"]).startswith("You are a context summarization assistant."):
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
        assert isinstance(await anext(stream), AgentCompactionStart)
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
            if str(messages[0]["content"]).startswith("You are a context summarization assistant.") and not self.sent:
                self.sent = True
                agent.steer("steering", "Also inspect P2")
            async for event in super().stream_events(messages, tools):
                yield event

    provider = Provider()
    agent.open_steering()
    asyncio.run(collect(agent.prompt(provider, history(), [], take_steering=agent.take_steering)))
    assert provider.requests[0][0][-1]["content"] == "Also inspect P2"


def test_compaction_prompts_match_pi_without_project_notes():
    from nurse_scheduling.ai.system_prompt import PROMPT_DIRECTORY

    # Pi v1.0.0, a13d35a742c6ef8462812a28fbe1d8c8b7431c32.
    # Hashes cover the original strings, with TypeScript interpolation expanded.
    expected = {
        "compaction-system": "c464889dcfa60441e642f291445b49523f263e6fb2725d0c25075543a2ec3f8f",
        "context-compaction": "9b00aa68df1a64279bc36e9093367f638701d48ec82e3d08436f65092a515f9b",
        "compaction-update": "240c52982209146eae47d73c7172f6ba1dab60f44520bcb6a6ec1a883fef2ec7",
        "compaction-turn-prefix": "7b0a15be5e0fdcce338ce7c1ef1fdd386faed258cc25d03915a05b05e7a6a183",
    }
    entries = load_system_prompt_entries(COMPACTION_MANIFEST)
    sections = load_system_prompt_sections(entries)
    assert {entry["id"] for entry in entries} == set(expected)
    for entry, section in zip(entries, sections, strict=True):
        raw = (PROMPT_DIRECTORY / entry["file"]).read_text(encoding="utf-8")
        body = raw.split("<!-- This file is mostly AI generated. -->\n\n", 1)[1].rstrip("\n")
        assert hashlib.sha256(body.encode()).hexdigest() == expected[entry["id"]]
        assert entry["upstream_sha256"] == expected[entry["id"]]
        assert "<!--" not in section
        assert section == body
        assert entry["sha256"] == entry["upstream_sha256"]
        assert hashlib.sha256(section.encode()).hexdigest() == entry["sha256"]


def test_repeated_compaction_uses_pi_update_prompt_with_previous_summary(monkeypatch):
    import nurse_scheduling.ai.compaction as module
    from nurse_scheduling.ai.context import summary_message

    provider = CompactionProvider()
    provider.context_tokens = 16000
    monkeypatch.setattr(module, "_cut_point", lambda _messages, _keep: 2)
    messages = [
        {"role": "system", "content": "Scheduling assistant"},
        summary_message("Earlier goal: preserve P1 nights and /workspace/notes.txt"),
        {"role": "user", "content": "Additional request " + "x" * 8000},
        {"role": "assistant", "content": "Earlier work completed"},
        {"role": "user", "content": "Next request"},
    ]
    events = asyncio.run(collect(ContextCompactor(provider).compact(messages, [], force=True)))
    assert any(isinstance(event, AgentCompaction) for event in events)
    ((request, _tools),) = provider.summaries
    content = request[-1]["content"]
    assert (
        "<previous-summary>\nEarlier goal: preserve P1 nights and /workspace/notes.txt\n</previous-summary>" in content
    )
    conversation = content.split("<conversation>\n", 1)[1].split("\n</conversation>", 1)[0]
    assert "Earlier goal" not in conversation
    assert "Additional request" in conversation
    assert "The messages above are NEW conversation messages" in content
    assert content.index("</conversation>") < content.index("The messages above are NEW")


def test_split_turn_uses_pi_history_and_turn_prefix_prompts(monkeypatch):
    import nurse_scheduling.ai.compaction as module

    provider = CompactionProvider()
    provider.context_tokens = 16000
    monkeypatch.setattr(module, "_cut_point", lambda _messages, _keep: 3)
    messages = [
        {"role": "system", "content": "Scheduling assistant"},
        {"role": "user", "content": "Older task " + "x" * 8000},
        {"role": "assistant", "content": "Older result"},
        {"role": "user", "content": "Active task: inspect P1"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "read", "type": "function", "function": {"name": "read", "arguments": "{}"}}],
        },
        {"role": "tool", "tool_call_id": "read", "content": "P1 found"},
    ]
    events = asyncio.run(collect(ContextCompactor(provider).compact(messages, [], force=True)))
    assert len(provider.summaries) == 2
    history, prefix = [request[-1]["content"] for request, _tools in provider.summaries]
    assert "Create a structured context checkpoint summary" in history
    assert "Active task" not in history
    assert "## Original Request" in prefix and "Active task: inspect P1" in prefix
    assert "Older task" not in prefix and "P1 found" not in prefix
    (entry,) = [event.entry for event in events if isinstance(event, AgentCompaction)]
    assert "**Turn Context (split turn):**" in entry.summary
    request = prepare_provider_request(apply_compaction(messages, entry), [], provider=provider.identity)
    assert request[-2]["tool_calls"][0]["id"] == request[-1]["tool_call_id"] == "read"


def test_user_written_summary_prefix_remains_conversation_data(monkeypatch):
    import nurse_scheduling.ai.compaction as module

    provider = CompactionProvider()
    provider.context_tokens = 16000
    monkeypatch.setattr(module, "_cut_point", lambda _messages, _keep: 2)
    messages = [
        {"role": "system", "content": "Scheduling assistant"},
        {"role": "user", "content": "[Conversation summary]\nThis is a quoted example " + "x" * 8000},
        {"role": "assistant", "content": "Acknowledged"},
        {"role": "user", "content": "Next"},
    ]
    events = asyncio.run(collect(ContextCompactor(provider).compact(messages, [], force=True)))
    assert any(isinstance(event, AgentCompaction) for event in events)
    request, _ = provider.summaries[0]
    assert "<previous-summary>" not in request[-1]["content"]
    assert "[user]: [Conversation summary]" in request[-1]["content"]


def test_failed_split_turn_summary_leaves_original_context_intact(monkeypatch):
    import nurse_scheduling.ai.compaction as module

    class Provider(CompactionProvider):
        async def stream_events(self, messages, tools=None):
            if len(self.summaries) == 1:
                raise ProviderError("turn prefix failed")
            async for event in super().stream_events(messages, tools):
                yield event

    provider = Provider()
    provider.context_tokens = 16000
    monkeypatch.setattr(module, "_cut_point", lambda _messages, _keep: 3)
    messages = [
        {"role": "system", "content": "Scheduling assistant"},
        {"role": "user", "content": "Old task " + "x" * 8000},
        {"role": "assistant", "content": "Old result"},
        {"role": "user", "content": "Active task"},
        {"role": "assistant", "content": "Recent work"},
    ]
    before = json.dumps(messages)
    compactor = ContextCompactor(provider)
    events = asyncio.run(collect(compactor.compact(messages, [], force=True)))
    assert not any(isinstance(event, AgentCompaction) for event in events)
    assert compactor.failed
    assert json.dumps(messages) == before


@pytest.mark.parametrize("failure", [None, "error", "cancel"])
def test_manual_compaction_uses_session_events_without_a_question_or_workspace(failure):
    import httpx

    from . import test_ai_basic as basic

    async def exercise():
        provider = CompactionProvider(fail_summary=failure)
        provider.context_tokens = 131072
        app = basic.create_test_app(settings=basic.make_settings(), provider=provider)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://testserver", headers=basic.AI_AUTH_HEADERS
            ) as client,
        ):
            sid = (await client.post("/sessions", json={"schedule_yaml": basic.schedule_yaml()})).json()["id"]
            session = app.state.session_store._sessions[sid]
            original = [UserMessage("Keep nights " + "x" * 12000), AssistantMessage("Earlier answer")]
            for entry in original:
                session._add_entry(entry)
            publications = []
            session.subscribe(publications.append)
            request = {"message_id": "manual-compact"}
            response = await client.post(f"/sessions/{sid}/compact", json=request)
            assert response.status_code == 202, response.text
            await asyncio.wait_for(provider.summary_started.wait(), 2)
            if failure == "cancel":
                busy = await client.post(f"/sessions/{sid}/compact", json={"message_id": "another"})
                assert busy.status_code == 409
                queued = await client.post(
                    f"/sessions/{sid}/messages/queue", json={"message": "hello", "message_id": "steer"}
                )
                assert queued.status_code == 409
                assert (await client.post(f"/sessions/{sid}/stop")).status_code == 202
            async with asyncio.timeout(3):
                while app.state.runs.busy(sid):
                    await asyncio.sleep(0)
            repeated = await client.post(f"/sessions/{sid}/compact", json=request)
            assert repeated.json() == response.json()
            assert len(provider.summaries) == 1
            assert not provider.requests
            assert app.state.sandbox_factory.created == []
            assert not session.active
            assert session.transcript[:2] == original
            assert not any(entry.text == "/compact" for entry in session.transcript if isinstance(entry, UserMessage))
            assert not any(
                event["type"] in {"delta", "reasoning", "tool_start", "tool", "response_end"} for event in publications
            )
            assert publications[0]["trigger"] == "compaction"
            end = next(event for event in publications if event["type"] == "compaction_end")
            assert end["reason"] == "manual"
            assert end["success"] is (failure is None)
            assert end["aborted"] is (failure == "cancel")
            if failure is None:
                assert isinstance(session.transcript[-1], CompactionEntry)
                assert end["summary"] == session.transcript[-1].summary
                assert any(event["type"] == "context_usage" and event["estimated"] for event in publications)
            else:
                assert session.transcript == original
            assert publications[-1]["type"] == ("stopped" if failure == "cancel" else "done")

    asyncio.run(exercise())

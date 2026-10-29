"""Provider cost records, retries, cancellation, and restart checks."""

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
from dataclasses import asdict, replace
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest

from nurse_scheduling.ai.costs import CostTotals
from nurse_scheduling.ai.provider import (
    OpenAiCompatibleProvider,
    ProviderCall,
    ReasoningDelta,
    ResponseEnd,
    TextDelta,
    TokenUsage,
    _parse_cost,
)
from nurse_scheduling.ai.session_event_stream import SessionEventStream
from nurse_scheduling.ai.sessions import SessionStore

from . import test_ai_basic as basic
from .test_ai_history import postgres_history, recorded_history, uninitialized_postgres_history

__all__ = ["postgres_history", "recorded_history", "uninitialized_postgres_history"]


def test_context_tokens_and_costs_update_before_the_stream_finishes():
    class Provider:
        context_tokens = 32000

        async def stream_events(self, _messages, _tools=None):
            call = ProviderCall("streamed-call", "model")
            yield call
            yield ReasoningDelta("Planning the answer.")
            await asyncio.sleep(0.04)
            yield TextDelta("First part of the answer. ")
            await asyncio.sleep(0.04)
            yield replace(call, cost_usd="0.01")
            yield TextDelta("Second part of the answer.")
            await asyncio.sleep(0.04)
            yield TokenUsage(500, 100, 600)
            yield replace(call, status="reported", cost_usd="0.02")
            yield ResponseEnd("stop")

    app = basic.create_test_app(settings=basic.make_settings(), provider=Provider())
    with basic.AuthenticatedTestClient(app) as client:
        session = basic.create_session(client, basic.schedule_yaml())
        response = client.post(f"/sessions/{session}/messages", json={"message": "Question"})
    events = basic.parse_sse(response.text)
    last_delta = max(index for index, (kind, _) in enumerate(events) if kind == "delta")
    progress = [data for kind, data in events[:last_delta] if kind == "context_usage" and "used_tokens" in data]
    assert len(progress) >= 2
    assert progress[-1]["used_tokens"] > progress[0]["used_tokens"]
    assert progress[-1]["used_chars"] > progress[0]["used_chars"]
    assert progress[-1]["max_tokens"] == 32000
    assert any(kind == "cost_summary" and data["conversation"]["usd"] == "0.01" for kind, data in events[:last_delta])
    assert [data for kind, data in events if kind == "context_usage"][-1]["used_tokens"] == 600
    assert [data for kind, data in events if kind == "cost_summary"][-1]["conversation"]["usd"] == "0.02"


def stream_response(cost, *, usage=True, header_cost="0", text="Answer"):
    events = [
        {"model": "actual-model", "choices": [{"delta": {"content": text}, "finish_reason": None}]},
        {"choices": [{"delta": {}, "finish_reason": "stop"}]},
    ]
    if usage:
        events.append(
            {
                "choices": [],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "total_tokens": 120,
                    "completion_tokens_details": {"reasoning_tokens": 10},
                    "cost": cost,
                },
            }
        )
    return httpx.Response(
        200,
        headers={"x-litellm-response-cost": header_cost, "x-litellm-call-id": "gateway-call"},
        text="".join(f"data: {json.dumps(event)}\n\n" for event in events) + "data: [DONE]\n\n",
    )


def patch_gateway(monkeypatch, costs):
    original = httpx.AsyncClient
    requests = []

    def respond(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "test-model", "context_length": 262144}]})
        if request.url.path.endswith("/model/info"):
            return httpx.Response(404)
        requests.append(request)
        return stream_response(costs[len(requests) - 1])

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: original(**{**kwargs, "transport": httpx.MockTransport(respond)})
    )
    return requests


@pytest.mark.parametrize("cost", [0.000123, 4.45e-322, 5e-324])
def test_cost_uses_stream_usage_instead_of_initial_zero_header(monkeypatch, cost):
    patch_gateway(monkeypatch, [cost])
    provider = OpenAiCompatibleProvider(basic.make_settings(), include_usage=True, include_costs=True)
    events = asyncio.run(collect(provider.stream_events([])))
    calls = [event for event in events if isinstance(event, ProviderCall)]
    assert calls[0].status == "pending"
    assert calls[-1].status == "reported"
    assert Decimal(calls[-1].cost_usd) == Decimal(str(cost))
    assert calls[-1].usage == TokenUsage(100, 20, 120, reasoning_tokens=10)
    assert calls[-1].provider_call_id == "gateway-call" and calls[-1].response_model == "actual-model"
    totals = CostTotals()
    previous = None
    for call in calls:
        totals.update(call, previous)
        previous = call
    assert totals.public() == {"usd": str(Decimal(str(cost))), "calls": 1, "pending": 0, "unavailable": 0}


async def collect(stream):
    return [event async for event in stream]


@pytest.mark.parametrize("cost", [None, True, -1, "NaN", "Infinity", "invalid", {}, "1e1000000", "1e-1000000"])
def test_missing_or_invalid_cost_is_unknown(cost):
    assert _parse_cost(cost) is None


def test_zero_cost_is_known_and_decimal_updates_do_not_accumulate_rounding():
    assert _parse_cost(0) == "0"
    totals = CostTotals()
    for index in range(10):
        pending = ProviderCall(str(index), "model")
        totals.update(pending)
        final = replace(pending, status="reported", cost_usd="0.1")
        totals.update(final, pending)
        totals.update(final, final)
    assert totals.public() == {"usd": "1.0", "calls": 10, "pending": 0, "unavailable": 0}


def test_timeout_retry_records_each_http_attempt(monkeypatch):
    class TimeoutStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'data: {"choices":[{"delta":{"content":"Partial"},"finish_reason":null}]}\n\n'
            raise httpx.ReadTimeout("timed out")

    original = httpx.AsyncClient
    attempts = []

    def respond(request):
        attempts.append(request)
        if len(attempts) == 1:
            return httpx.Response(200, stream=TimeoutStream())
        return stream_response(0.01)

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: original(**{**kwargs, "transport": httpx.MockTransport(respond)})
    )
    provider = OpenAiCompatibleProvider(basic.make_settings(provider_retry_backoff_seconds=0), include_costs=True)
    provider.context_tokens = 262144
    provider._context_tokens_loaded = True
    events = asyncio.run(collect(provider.stream_events([])))
    finals = [event for event in events if isinstance(event, ProviderCall) and event.status != "pending"]
    assert len(attempts) == len(finals) == 2
    assert finals[0].status == "unavailable" and finals[0].cost_usd is None
    assert finals[1].status == "reported" and finals[1].cost_usd == "0.01"
    assert finals[0].id != finals[1].id


def test_session_aggregates_calls_across_turns_without_replay_charges(monkeypatch):
    requests = patch_gateway(monkeypatch, [0.1, None, 0])
    app = basic.create_test_app(settings=basic.make_settings(), provider=None)
    with basic.AuthenticatedTestClient(app) as client:
        session = basic.create_session(client)
        path = f"/sessions/{session}/messages"
        first = {"message": "First", "message_id": "one"}
        assert client.post(path, json=first).status_code == 200
        assert client.post(path, json=first).status_code == 202
        assert client.post(path, json={"message": "Second"}).status_code == 200
        result = client.post(path, json={"message": "Third"})
        summary = [data for kind, data in basic.parse_sse(result.text) if kind == "cost_summary"][-1]
        assert {key: value for key, value in summary["conversation"].items() if key != "version"} == {
            "usd": "0.1",
            "calls": 3,
            "pending": 0,
            "unavailable": 1,
        }
        assert summary["run"] == {"usd": "0", "calls": 1, "pending": 0, "unavailable": 0}
    assert len(requests) == 3


def test_cancelled_run_reports_unknown_cost_instead_of_free():
    class WaitingProvider:
        async def stream_events(self, messages, tools=None):
            yield ProviderCall("cancel-call", "model")
            raise asyncio.CancelledError

    app = basic.create_test_app(settings=basic.make_settings(), provider=WaitingProvider())
    with basic.AuthenticatedTestClient(app) as client:
        session = basic.create_session(client)
        result = client.post(f"/sessions/{session}/messages", json={"message": "Wait"})
        summary = [data for kind, data in basic.parse_sse(result.text) if kind == "cost_summary"][-1]
        assert {key: value for key, value in summary["conversation"].items() if key != "version"} == {
            "usd": "0",
            "calls": 1,
            "pending": 0,
            "unavailable": 1,
        }
        assert basic.parse_sse(result.text)[-1][0] == "stopped"


@pytest.mark.parametrize("checkpoint_saved", [False, True])
@pytest.mark.parametrize("phase", ["initial", "header", "reported"])
def test_stop_during_cost_checkpoint_preserves_reported_prices(monkeypatch, postgres_history, checkpoint_saved, phase):
    from nurse_scheduling.ai.provider import TextDelta
    from nurse_scheduling.ai.recovery import SessionRecovery

    save_checkpoint = SessionRecovery.save_provider_call

    async def exercise():
        started, release = asyncio.Event(), asyncio.Event()
        attempted = []

        class Provider:
            async def stream_events(self, messages, tools=None):
                yield ProviderCall("stop-call", "model")
                attempted.append(True)
                yield ProviderCall("stop-call", "model", "pending" if phase == "header" else "reported", "0.1")
                yield TextDelta("Answer")

        async def checkpoint(recorder, session_id, event):
            call = event.data
            target = (
                call["cost_usd"] is None
                if phase == "initial"
                else call["status"] == ("pending" if phase == "header" else "reported") and call["cost_usd"] == "0.1"
            )
            if target and not started.is_set():
                started.set()
                await release.wait()
            if target and not checkpoint_saved:
                return False
            return await save_checkpoint(recorder, session_id, event)

        monkeypatch.setattr(SessionRecovery, "save_provider_call", checkpoint)
        configuration = basic.make_settings(history_postgres_url="test")
        app = basic.create_test_app(settings=configuration, provider=Provider())
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://testserver", headers=basic.AI_AUTH_HEADERS
            ) as client,
        ):
            created = await client.post("/sessions", json={"schedule_yaml": "description: test"})
            session_id = created.json()["id"]
            response = asyncio.create_task(
                client.post(f"/sessions/{session_id}/messages", json={"message": "Question", "message_id": "one"})
            )
            try:
                await asyncio.wait_for(started.wait(), timeout=1)
                stopped = await client.post(f"/sessions/{session_id}/stop", json={"message_id": "one"})
                assert stopped.status_code == 202
            finally:
                release.set()
                result = await asyncio.wait_for(response, timeout=2)
            assert basic.parse_sse(result.text)[-1][0] == "stopped"
            expected = {
                "usd": "0" if phase == "initial" else "0.1",
                "calls": int(phase != "initial"),
                "pending": 0,
                "unavailable": 0,
            }
            session = app.state.session_store.get(session_id)
            assert session.cost_totals.public() == expected
            assert attempted == ([] if phase == "initial" else [True])
            assert not session.pending_provider_calls
            assert not app.state.runs.busy(session_id)
            await app.state.recovery.flush(session_id)
            owner = client.cookies[basic.OWNER_COOKIE]
            saved = await asyncio.to_thread(postgres_history.load_session, session_id, owner)
            assert saved["state"]["cost_totals"] == expected
            restored = SessionStore(configuration).restore(
                session_id, owner, saved["state"], saved["expires_at"], entries=[], next_entry_seq=0
            )
            assert restored.cost_totals.public() == expected
            if phase != "initial":
                calls = [data for kind, data in basic.parse_sse(result.text) if kind == "provider_call"]
                assert calls[-1]["status"] == "reported"
                assert calls[-1]["cost_usd"] == "0.1"
                saved_events = await asyncio.to_thread(postgres_history.load_events, session_id, 0)
                saved_calls = [data for _first, _last, _run, kind, data in saved_events if kind == "provider_call"]
                assert saved_calls[-1]["status"] == "reported"
                assert saved_calls[-1]["cost_usd"] == "0.1"

    asyncio.run(exercise())


def test_reset_during_cost_checkpoint_keeps_the_cost_publication_version(monkeypatch):
    from nurse_scheduling.ai.provider import TextDelta
    from nurse_scheduling.ai.recovery import SessionRecovery

    from .test_ai_history import read_events

    async def exercise():
        started, release = asyncio.Event(), asyncio.Event()

        class Provider:
            async def stream_events(self, messages, tools=None):
                yield ProviderCall("reset-call", "model")
                yield ProviderCall("reset-call", "model", "reported", "0.1")
                yield TextDelta("Answer")

        async def checkpoint(_self, _session_id, event):
            if event.data["status"] == "reported":
                started.set()
                await release.wait()
            return True

        monkeypatch.setattr(SessionRecovery, "save_provider_call", checkpoint)
        app = basic.create_test_app(settings=basic.make_settings(), provider=Provider())
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://testserver", headers=basic.AI_AUTH_HEADERS
            ) as client,
        ):
            created = await client.post("/sessions", json={"schedule_yaml": "description: test"})
            session_id = created.json()["id"]
            response = asyncio.create_task(
                client.post(f"/sessions/{session_id}/messages", json={"message": "Question"})
            )
            await asyncio.wait_for(started.wait(), timeout=1)
            session = app.state.session_store.get(session_id)
            session.publish({"type": "warning", "message": "An intervening event"})
            try:
                frames = await read_events(
                    app, session_id, client.cookies[basic.OWNER_COOKIE], until="session_reset", reset=True
                )
                reset = next(data for _identity, kind, data in frames if kind == "session_reset")
                assert reset["cost_summary"] == {**session.cost_totals.public(), "version": session.cost_totals_version}
            finally:
                release.set()
                result = await asyncio.wait_for(response, timeout=2)
            summaries = [data for kind, data in basic.parse_sse(result.text) if kind == "cost_summary"]
            final = summaries[-1]["conversation"]
            assert final["usd"] == "0.1"
            assert final["version"] > reset["cost_summary"]["version"]

    asyncio.run(exercise())


@pytest.mark.parametrize("amount", ["0.123", "4.45e-322"])
def test_postgres_restores_totals_from_call_events_even_without_saved_session_totals(postgres_history, amount):
    history = postgres_history
    session, owner, run = str(uuid4()), str(uuid4()), str(uuid4())
    from .test_ai_history import session_state

    history.save_session(session, session_state(owner))
    records = [
        (1, 1, run, "provider_call", {"call_id": "one", "cost_usd": None, "status": "pending"}),
        (2, 2, run, "provider_call", {"call_id": "one", "cost_usd": amount, "status": "reported"}),
        (3, 3, run, "provider_call", {"call_id": "two", "cost_usd": None, "status": "pending"}),
    ]
    history.append_events(session, records)
    history.append_events(session, records)
    restored = history.load_session(session, owner)
    totals = CostTotals.restored(restored["state"]["cost_totals"]).public()
    assert Decimal(totals["usd"]) == Decimal(amount)
    assert len(totals["usd"]) <= 80
    assert {key: value for key, value in totals.items() if key != "usd"} == {"calls": 2, "pending": 0, "unavailable": 1}
    assert history.load_session(session, str(uuid4())) is None


def test_call_updates_fold_by_call_id_instead_of_run_id():
    stream = SessionEventStream()
    for identity, amount in [("one", None), ("two", None), ("one", "0.1")]:
        stream.publish("session", {"type": "provider_call", "call_id": identity, "run_id": "run", "cost_usd": amount})
    calls = [event for event in stream._sessions["session"].recovery if event.type == "provider_call"]
    assert len(calls) == 2
    assert [event.data["call_id"] for event in calls] == ["two", "one"]


@pytest.mark.parametrize("phase", ["reported", "pending", "rejected"])
@pytest.mark.parametrize("newer", [False, True])
def test_postgres_reconciles_call_events_after_the_saved_cost_version(postgres_history, phase, newer):
    from .test_ai_history import session_state

    session, owner, run = str(uuid4()), str(uuid4()), str(uuid4())
    pending = ProviderCall("one", "model", cost_usd="0.1")
    totals = CostTotals()
    if phase != "rejected":
        totals.update(pending if phase == "pending" else replace(pending, status="reported", cost_usd="0.3"))
    state = session_state(
        owner,
        cost_totals=totals.public(),
        cost_totals_version=2,
        pending_provider_calls=[asdict(pending)] if phase == "pending" else [],
    )
    postgres_history.save_session(session, state)
    # The newer checkpoint failed, leaving only the initial pending call on disk.
    records = [(1, 1, run, "provider_call", {"call_id": "one", "cost_usd": None, "status": "pending"})]
    if newer:
        identity, amount = ("one", "0.3") if phase == "pending" else ("two", "0.2")
        records.append((3, 3, run, "provider_call", {"call_id": identity, "cost_usd": amount, "status": "reported"}))
    postgres_history.append_events(session, records)
    restored = postgres_history.load_session(session, owner)["state"]
    expected = {
        ("reported", False): ("0.3", 1),
        ("reported", True): ("0.5", 2),
        ("pending", False): ("0.1", 1),
        ("pending", True): ("0.3", 1),
        ("rejected", False): ("0", 0),
        ("rejected", True): ("0.2", 1),
    }
    amount, count = expected[phase, newer]
    assert restored["cost_totals"] == {"usd": amount, "calls": count, "pending": 0, "unavailable": 0}
    assert restored["pending_provider_calls"] == []
    postgres_history.save_session(session, (state[0], state[1], restored))
    assert postgres_history.load_session(session, owner)["state"]["cost_totals"] == restored["cost_totals"]


def test_tool_follow_up_calls_contribute_to_the_same_turn_total():
    from nurse_scheduling.ai.provider import TextDelta, ToolCall, ToolCallRequest

    provider = basic.ScriptedToolProvider(
        [
            ProviderCall("first", "model", "reported", "0.1", TokenUsage(10, 10, 20), streaming_seconds=1),
            ToolCallRequest((ToolCall("read", "read", '{"path":"/workspace/schedule.yaml"}'),)),
        ],
        [
            ProviderCall("second", "model", "reported", "0.2", TokenUsage(10, 90, 100), streaming_seconds=3),
            TextDelta("Read the schedule"),
        ],
    )
    app = basic.create_test_app(settings=basic.make_settings(), provider=provider)
    with basic.AuthenticatedTestClient(app) as client:
        session = basic.create_session(client)
        response = client.post(f"/sessions/{session}/messages", json={"message": "Read schedule"})
        summary = [data for kind, data in basic.parse_sse(response.text) if kind == "cost_summary"][-1]
        assert summary["run"] == {
            "usd": "0.3",
            "calls": 2,
            "pending": 0,
            "unavailable": 0,
            "streaming": {"calls": 2, "output_tokens": 100, "seconds": 4},
        }
        assert summary["conversation"]["streaming"] == summary["run"]["streaming"]


@pytest.mark.parametrize("failed_status", ["pending", "reported"])
def test_cost_checkpoint_failure_preserves_attempt_counts_and_saved_totals(
    monkeypatch, recorded_history, failed_status
):
    from nurse_scheduling.ai.provider import TextDelta
    from nurse_scheduling.ai.recovery import SessionRecovery

    sent = []

    class Provider:
        async def stream_events(self, messages, tools=None):
            yield ProviderCall("new-call", "model")
            sent.append(True)
            yield ProviderCall("new-call", "model", "reported", "0.1")
            yield TextDelta("Answer")

    async def unavailable(_self, _session_id, event):
        return event.data["status"] != failed_status

    monkeypatch.setattr(SessionRecovery, "save_provider_call", unavailable)
    app = basic.create_test_app(settings=basic.make_settings(history_postgres_url="test"), provider=Provider())
    with basic.AuthenticatedTestClient(app) as client:
        session = basic.create_session(client)
        response = client.post(f"/sessions/{session}/messages", json={"message": "Question"})
        events = basic.parse_sse(response.text)
        if failed_status == "pending":
            assert events[-1][0] == "error"
            assert "provider request was not started" in events[-1][1]["message"]
            assert sent == []
            expected = {"usd": "0", "calls": 0, "pending": 0, "unavailable": 0}
        else:
            assert events[-1][0] == "done"
            assert sent == [True]
            expected = {"usd": "0.1", "calls": 1, "pending": 0, "unavailable": 0}
        current = app.state.session_store.get(session)
        assert not current.active
        assert current.cost_totals.public() == expected
        assert not current.pending_provider_calls
        assert not any(kind == "provider_call" and data["status"] == "unavailable" for kind, data in events)
        state = recorded_history["finishes"][-1][-1][2]
        assert state["cost_totals"] == expected
        assert (
            state["cost_totals_version"]
            == [
                event.id
                for event in app.state.session_event_stream.events_after(session)
                if event.type == "provider_call"
            ][-1]
        )


def test_tiny_totals_and_restored_mixed_prices_fit_the_browser_contract():
    totals = CostTotals()
    totals.update(ProviderCall("tiny", "model", "reported", "4.45e-322"))
    assert totals.public()["usd"] == "4.45E-322"
    restored = CostTotals.restored(
        {"usd": "0.1" + "0" * 319 + "445", "calls": 2, "pending": 0, "unavailable": 0}
    ).public()
    assert len(restored["usd"]) <= 80
    assert Decimal(restored["usd"]) == Decimal("0.1")


@pytest.mark.parametrize("kind", ["text", "reasoning", "tool"])
def test_provider_times_only_generated_output_between_first_and_last_chunk(monkeypatch, kind):
    from types import SimpleNamespace

    from nurse_scheduling.ai import provider as module

    now = 0.0
    monkeypatch.setattr(module, "time", SimpleNamespace(perf_counter=lambda: now, monotonic=module.time.monotonic))
    if kind == "tool":
        deltas = [
            {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "read",
                        "type": "function",
                        "function": {"name": "read", "arguments": '{"path":'},
                    }
                ]
            },
            {"tool_calls": [{"index": 0, "function": {"arguments": '"/workspace/schedule.yaml"}'}}]},
        ]
    else:
        key = "content" if kind == "text" else "reasoning_content"
        deltas = [{key: "First"}, {key: "last"}]

    class TimedStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            nonlocal now
            for at, event in [
                (1, {"choices": [{"delta": {"role": "assistant"}, "finish_reason": None}]}),
                (5, {"choices": [{"delta": deltas[0], "finish_reason": None}]}),
                (7, {"choices": [{"delta": deltas[1], "finish_reason": None}]}),
                (10, {"choices": [{"delta": {}, "finish_reason": "tool_calls" if kind == "tool" else "stop"}]}),
                (
                    14,
                    {
                        "choices": [],
                        "usage": {
                            "prompt_tokens": 100,
                            "completion_tokens": 20,
                            "total_tokens": 120,
                            "completion_tokens_details": {"reasoning_tokens": 10},
                        },
                    },
                ),
            ]:
                now = at
                yield f"data: {json.dumps(event)}\n\n".encode()
            now = 30
            yield b"data: [DONE]\n\n"

    original = httpx.AsyncClient

    def respond(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "test-model", "context_length": 262144}]})
        return httpx.Response(200, stream=TimedStream())

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: original(**{**kwargs, "transport": httpx.MockTransport(respond)})
    )
    provider = OpenAiCompatibleProvider(basic.make_settings(), include_usage=True, include_costs=True)
    events = asyncio.run(collect(provider.stream_events([])))
    call = [event for event in events if isinstance(event, ProviderCall)][-1]
    assert call.status == "unavailable"  # Missing price does not hide measured speed.
    assert call.streaming_seconds == 2
    assert call.time_to_first_output_seconds == 5
    totals = CostTotals()
    totals.update(call)
    assert totals.public()["streaming"] == {"calls": 1, "output_tokens": 20, "seconds": 2}


def test_streaming_totals_replace_updates_and_restore_without_averaging_speeds():
    first = ProviderCall("one", "model", "reported", "0.1", TokenUsage(10, 10, 20), streaming_seconds=1)
    second = ProviderCall("two", "model", "unavailable", usage=TokenUsage(10, 90, 100), streaming_seconds=3)
    missing_usage = ProviderCall("three", "model", "reported", "0", streaming_seconds=5)
    single_chunk = replace(first, id="four", streaming_seconds=None)
    totals = CostTotals()
    for call in (first, second, missing_usage, single_chunk):
        totals.update(call)
    totals.update(replace(first, cost_usd="0.2"), first)
    measured = totals.public()["streaming"]
    assert measured == {"calls": 2, "output_tokens": 100, "seconds": 4}
    assert measured["output_tokens"] / measured["seconds"] == 25
    assert CostTotals.restored(totals.public()).public() == totals.public()
    assert ProviderCall.restored(asdict(first)) == first


def test_single_output_chunk_keeps_first_output_time_but_has_no_speed(monkeypatch):
    patch_gateway(monkeypatch, [0.1])
    provider = OpenAiCompatibleProvider(basic.make_settings(), include_usage=True, include_costs=True)
    events = asyncio.run(collect(provider.stream_events([])))
    call = [event for event in events if isinstance(event, ProviderCall)][-1]
    assert call.time_to_first_output_seconds is not None
    assert call.streaming_seconds is None


@pytest.mark.parametrize("saved_totals", [False, True])
def test_postgres_restores_streaming_usage_from_call_checkpoints(postgres_history, saved_totals):
    from .test_ai_history import session_state

    session, owner, run = str(uuid4()), str(uuid4()), str(uuid4())
    call = ProviderCall(
        "one", "model", usage=TokenUsage(10, 20, 30), streaming_seconds=2, time_to_first_output_seconds=5
    )
    totals = CostTotals()
    totals.update(call)
    state = session_state(owner)
    if saved_totals:
        state[2].update(cost_totals=totals.public(), cost_totals_version=1, pending_provider_calls=[asdict(call)])
    postgres_history.save_session(session, state)
    postgres_history.append_events(
        session,
        [
            (
                2,
                2,
                run,
                "provider_call",
                {
                    **asdict(replace(call, status="reported", cost_usd="0.1")),
                    "call_id": call.id,
                },
            )
        ],
    )
    restored = postgres_history.load_session(session, owner)["state"]
    assert restored["cost_totals"]["streaming"] == {"calls": 1, "output_tokens": 20, "seconds": 2}
    postgres_history.save_session(session, (session_state(owner)[0], session_state(owner)[1], restored))
    assert postgres_history.load_session(session, owner)["state"]["cost_totals"] == restored["cost_totals"]


def test_session_keeps_run_speed_separate_from_conversation_speed_and_replays():
    provider = basic.ScriptedToolProvider(
        [
            ProviderCall("one", "model", "reported", "0.1", TokenUsage(10, 20, 30), streaming_seconds=2),
            TextDelta("First"),
        ],
        [
            ProviderCall("two", "model", "reported", "0.1", TokenUsage(10, 90, 100), streaming_seconds=3),
            TextDelta("Second"),
        ],
    )
    app = basic.create_test_app(settings=basic.make_settings(), provider=provider)
    with basic.AuthenticatedTestClient(app) as client:
        session = basic.create_session(client)
        path = f"/sessions/{session}/messages"
        first = {"message": "First", "message_id": "one"}
        client.post(path, json=first)
        assert client.post(path, json=first).status_code == 202
        response = client.post(path, json={"message": "Second"})
        summary = [data for kind, data in basic.parse_sse(response.text) if kind == "cost_summary"][-1]
        assert summary["run"]["streaming"] == {"calls": 1, "output_tokens": 90, "seconds": 3}
        assert summary["conversation"]["streaming"] == {"calls": 2, "output_tokens": 110, "seconds": 5}

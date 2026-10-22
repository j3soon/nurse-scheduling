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
from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest

from nurse_scheduling.ai.costs import CostTotals
from nurse_scheduling.ai.provider import OpenAiCompatibleProvider, ProviderCall, TokenUsage, _parse_cost
from nurse_scheduling.ai.session_event_stream import SessionEventStream

from . import test_ai_basic as basic
from .test_ai_history import postgres_history, uninitialized_postgres_history

__all__ = ["postgres_history", "uninitialized_postgres_history"]


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
            return httpx.Response(200, json={"data": [{"id": "test-model"}]})
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


def test_tool_follow_up_calls_contribute_to_the_same_turn_total():
    from nurse_scheduling.ai.provider import TextDelta, ToolCall, ToolCallRequest

    provider = basic.ScriptedToolProvider(
        [
            ProviderCall("first", "model", "reported", "0.1"),
            ToolCallRequest((ToolCall("read", "read", '{"path":"/workspace/schedule.yaml"}'),)),
        ],
        [ProviderCall("second", "model", "reported", "0.2"), TextDelta("Read the schedule")],
    )
    app = basic.create_test_app(settings=basic.make_settings(), provider=provider)
    with basic.AuthenticatedTestClient(app) as client:
        session = basic.create_session(client)
        response = client.post(f"/sessions/{session}/messages", json={"message": "Read schedule"})
        summary = [data for kind, data in basic.parse_sse(response.text) if kind == "cost_summary"][-1]
        assert summary["run"] == {"usd": "0.3", "calls": 2, "pending": 0, "unavailable": 0}


def test_cost_checkpoint_failure_does_not_start_provider_or_leave_run_open(monkeypatch):
    from nurse_scheduling.ai.recovery import SessionRecovery

    sent = []

    class Provider:
        async def stream_events(self, messages, tools=None):
            yield ProviderCall("new-call", "model")
            sent.append(True)

    async def unavailable(*_args):
        return False

    monkeypatch.setattr(SessionRecovery, "save_provider_call", unavailable)
    app = basic.create_test_app(settings=basic.make_settings(), provider=Provider())
    with basic.AuthenticatedTestClient(app) as client:
        session = basic.create_session(client)
        response = client.post(f"/sessions/{session}/messages", json={"message": "Question"})
        events = basic.parse_sse(response.text)
        assert events[-1][0] == "error"
        assert "provider request was not started" in events[-1][1]["message"]
        assert sent == []
        assert not app.state.session_store.get(session).active


def test_tiny_totals_and_restored_mixed_prices_fit_the_browser_contract():
    totals = CostTotals()
    totals.update(ProviderCall("tiny", "model", "reported", "4.45e-322"))
    assert totals.public()["usd"] == "4.45E-322"
    restored = CostTotals.restored(
        {"usd": "0.1" + "0" * 319 + "445", "calls": 2, "pending": 0, "unavailable": 0}
    ).public()
    assert len(restored["usd"]) <= 80
    assert Decimal(restored["usd"]) == Decimal("0.1")

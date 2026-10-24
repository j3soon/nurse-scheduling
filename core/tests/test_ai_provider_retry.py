"""Tests for bounded transient retries and safe continuation."""

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
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest

from nurse_scheduling.ai import provider as provider_module
from nurse_scheduling.ai.agent_loop import agent_loop
from nurse_scheduling.ai.agent_types import AgentToolOutcome
from nurse_scheduling.ai.provider import ProviderCall, ProviderContextOverflowError, ProviderError, TextDelta
from nurse_scheduling.ai.provider_retry import retry_delay

from .ai_test_helper import bind_agent_tools
from .test_ai_provider import TOOLS, _collect, _delta_chunk, _events, _sse_body, _transport_provider


@pytest.mark.parametrize(
    "headers,expected",
    [
        ({"retry-after-ms": "1250", "retry-after": "40"}, 1.25),
        ({"retry-after": "0"}, 0),
        ({"retry-after": "60"}, 60),
        ({"retry-after": "61"}, None),
        ({"retry-after-ms": "60001"}, None),
        ({"retry-after-ms": "invalid", "retry-after": "3"}, 3),
        ({"retry-after-ms": "nan", "retry-after": "3"}, 3),
        ({"retry-after": "nan"}, 2),
        ({"retry-after": "inf"}, 2),
        ({"retry-after": "-1"}, 2),
        ({"retry-after": "invalid"}, 2),
    ],
)
def test_retry_delay_honors_valid_headers_and_bounds_waits(monkeypatch, headers, expected):
    monkeypatch.setattr("nurse_scheduling.ai.provider_retry.random.random", lambda: 0)
    assert retry_delay(httpx.Headers(headers), 2, 1) == expected


def test_retry_after_http_dates_and_jittered_backoff(monkeypatch):
    now = datetime(2031, 4, 1, tzinfo=UTC)
    for seconds, expected in [(5, 5), (-5, 0), (61, None)]:
        headers = httpx.Headers({"Retry-After": format_datetime(now + timedelta(seconds=seconds), usegmt=True)})
        assert retry_delay(headers, 1, 1, now=now) == expected
    monkeypatch.setattr("nurse_scheduling.ai.provider_retry.random.random", lambda: 0)
    assert retry_delay(httpx.Headers(), 100000, 1) == 8
    monkeypatch.setattr("nurse_scheduling.ai.provider_retry.random.random", lambda: 1)
    assert retry_delay(httpx.Headers(), 100000, 1) == 6


@pytest.mark.parametrize("headers,delay", [({"retry-after-ms": "1250"}, 1.25), ({"retry-after": "2"}, 2)])
def test_adapter_uses_server_retry_delay(monkeypatch, headers, delay):
    requests, delays = [], []

    def handle(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(429, headers=headers, text="Too many requests")
        return httpx.Response(200, text=_sse_body(_delta_chunk({"content": "Recovered"})))

    async def sleep(seconds):
        delays.append(seconds)

    monkeypatch.setattr(provider_module.asyncio, "sleep", sleep)
    provider = _transport_provider(monkeypatch, handle)
    assert TextDelta("Recovered") in _events(provider)
    assert len(requests) == 2 and delays == [delay]


@pytest.mark.parametrize("status,headers", [(503, {"retry-after": "120"}), (429, {"retry-after-ms": "90000"})])
def test_long_server_retry_delays_fail_without_sending_another_request(monkeypatch, status, headers):
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(status, headers=headers, text="Try again later")

    provider = _transport_provider(monkeypatch, handle)
    with pytest.raises(ProviderError, match="retry delay above 60 seconds"):
        _events(provider)
    assert len(requests) == 1


@pytest.mark.parametrize("error_type", [httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError])
def test_transport_failures_retry_before_output(monkeypatch, error_type):
    requests = []

    def handle(request):
        requests.append(request)
        if len(requests) == 1:
            raise error_type("Connection closed", request=request)
        return httpx.Response(200, text=_sse_body(_delta_chunk({"content": "Recovered"})))

    provider = _transport_provider(monkeypatch, handle, provider_retry_backoff_seconds=0)
    assert _events(provider) == [TextDelta("Recovered"), provider_module.ResponseEnd(None)]
    assert len(requests) == 2


def test_premature_eof_continues_visible_text_without_replaying_failed_native_metadata(monkeypatch):
    requests = []

    def handle(request):
        requests.append(json.loads(request.content))
        if len(requests) == 1:
            chunk = _delta_chunk(
                {
                    "content": "First. ",
                    "reasoning_content": "Private",
                    "reasoning_details": [{"type": "reasoning.encrypted", "data": "opaque", "id": "r"}],
                }
            )
            return httpx.Response(200, text=_sse_body(chunk).removesuffix("data: [DONE]\n\n"))
        return httpx.Response(200, text=_sse_body(_delta_chunk({"content": "Finished."})))

    provider = _transport_provider(monkeypatch, handle, provider_retry_backoff_seconds=0)
    events = _events(provider)
    assert [event.text for event in events if isinstance(event, TextDelta)] == ["First. ", "Finished."]
    assert requests[-1]["messages"][-2] == {"role": "assistant", "content": "First. "}
    assert "Private" not in str(requests[-1]) and "opaque" not in str(requests[-1])


def test_retry_after_tool_result_does_not_execute_the_completed_tool_again(monkeypatch):
    requests, executed = [], []

    def handle(request):
        if request.method == "GET":
            return httpx.Response(200, json={"data": []})
        requests.append(request)
        if len(requests) == 1:
            call = {"index": 0, "id": "edit", "function": {"name": "schedule_patch", "arguments": "{}"}}
            return httpx.Response(200, text=_sse_body(_delta_chunk({"tool_calls": [call]})))
        if len(requests) == 2:
            return httpx.Response(503, text="Overloaded")
        return httpx.Response(200, text=_sse_body(_delta_chunk({"content": "Done."})))

    async def execute(name, arguments):
        executed.append((name, arguments))
        return AgentToolOutcome("Applied", True)

    provider = _transport_provider(monkeypatch, handle, provider_retry_backoff_seconds=0)
    asyncio.run(_collect(agent_loop(provider, [{"role": "user", "content": "Edit"}], bind_agent_tools(TOOLS, execute))))
    assert executed == [("schedule_patch", "{}")]
    assert len(requests) == 3
    assert requests[1].content == requests[2].content


def test_cancelling_backoff_stops_without_another_request_and_preserves_attempt_cost(monkeypatch):
    async def exercise():
        requests, events = [], []
        waiting = asyncio.Event()

        def handle(request):
            requests.append(request)
            return httpx.Response(503, headers={"Retry-After": "30"}, text="Busy")

        async def sleep(_seconds):
            waiting.set()
            await asyncio.Event().wait()

        monkeypatch.setattr(provider_module.asyncio, "sleep", sleep)
        provider = _transport_provider(monkeypatch, handle)
        provider._include_costs = True

        async def consume():
            async for event in provider.stream_events([{"role": "user", "content": "Question"}]):
                events.append(event)

        task = asyncio.create_task(consume())
        await asyncio.wait_for(waiting.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert len(requests) == 1
        calls = [event for event in events if isinstance(event, ProviderCall)]
        assert [call.status for call in calls] == ["pending", "unavailable"]
        assert calls[0].id == calls[1].id

    asyncio.run(exercise())


def test_context_overflow_is_left_for_compaction_instead_of_transient_retries(monkeypatch):
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(400, json={"error": {"code": "context_length_exceeded"}})

    provider = _transport_provider(monkeypatch, handle, provider_retry_backoff_seconds=0)
    with pytest.raises(ProviderContextOverflowError):
        _events(provider)
    assert len(requests) == 1


def test_transient_http_retries_stop_at_the_attempt_budget(monkeypatch):
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(503, text="Overloaded")

    provider = _transport_provider(monkeypatch, handle, provider_max_attempts=3, provider_retry_backoff_seconds=0)
    with pytest.raises(ProviderError, match="HTTP 503"):
        _events(provider)
    assert len(requests) == 3

"""Tests for the OpenAI-compatible provider adapter."""

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
import logging
import re
import time
from collections.abc import AsyncIterator
from types import SimpleNamespace

import httpx
import pytest

from nurse_scheduling.ai import provider as provider_module
from nurse_scheduling.ai.agent_loop import agent_loop
from nurse_scheduling.ai.agent_types import AgentToolOutcome
from nurse_scheduling.ai.config import AiSettings
from nurse_scheduling.ai.provider import (
    ChatMessage,
    OpenAiCompatibleProvider,
    ProviderAttempt,
    ProviderCall,
    ProviderError,
    ProviderResponseLimitError,
    ProviderRetry,
    ReasoningDelta,
    ReasoningReplay,
    ResponseEnd,
    TextDelta,
    TokenUsage,
    ToolCall,
    ToolCallRequest,
)

from .ai_test_helper import bind_agent_tools


async def _collect(stream: AsyncIterator) -> list:
    """Consume a provider stream so request errors are raised."""
    return [item async for item in stream]


@pytest.mark.parametrize(
    ("content_type", "response_body", "expected_logged_body"),
    [
        (
            "application/json",
            '{"error":{"message":"origin TLS handshake failed","api_key":"test-token","code":525}}',
            '{"error":{"message":"origin TLS handshake failed","api_key":"[REDACTED]","code":525}}',
        ),
        (
            "text/html",
            "<html>\n<body>Cloud proxy error 525</body>\n</html>",
            "<html> <body>Cloud proxy error 525</body> </html>",
        ),
    ],
)
def test_provider_http_error_logs_redacted_body_and_returns_error_id(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    content_type: str,
    response_body: str,
    expected_logged_body: str,
) -> None:
    real_async_client = httpx.AsyncClient
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(525, headers={"Content-Type": content_type}, text=response_body)
    )
    monkeypatch.setattr(
        provider_module.httpx,
        "AsyncClient",
        lambda **kwargs: real_async_client(transport=transport, **kwargs),
    )
    provider = OpenAiCompatibleProvider(
        AiSettings(
            provider_base_url="https://provider.example/v1",
            provider_api_key="test-token",
            provider_model="test-model",
            auth_token="ai-shared-test-token",
            provider_max_attempts=1,
        )
    )
    messages: list[ChatMessage] = [{"role": "user", "content": "Question"}]
    caplog.set_level(logging.ERROR, logger="nurse_scheduling.ai.provider")

    with pytest.raises(ProviderError) as error:
        asyncio.run(_collect(provider.stream_chat(messages)))

    error_match = re.fullmatch(
        r"The AI provider returned HTTP 525\. Error ID: ([0-9a-f-]{36})\.",
        str(error.value),
    )
    assert error_match is not None
    assert f"error_id={error_match.group(1)} status=525" in caplog.text
    assert f"content_type={content_type}" in caplog.text
    assert expected_logged_body in caplog.text
    assert "test-token" not in caplog.text


def test_provider_http_error_bounds_untrusted_response_excerpt(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response_body = "authorization: Bearer exposed-token\n" + "x" * 5_000
    real_async_client = httpx.AsyncClient
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(520, headers={"Content-Type": "text/html; charset=UTF-8"}, text=response_body)
    )
    monkeypatch.setattr(
        provider_module.httpx,
        "AsyncClient",
        lambda **kwargs: real_async_client(transport=transport, **kwargs),
    )
    provider = OpenAiCompatibleProvider(
        AiSettings(
            provider_base_url="https://provider.example/v1",
            provider_api_key="test-token",
            provider_model="test-model",
            auth_token="ai-shared-test-token",
            provider_max_attempts=1,
        )
    )
    caplog.set_level(logging.ERROR, logger="nurse_scheduling.ai.provider")

    with pytest.raises(ProviderError, match="HTTP 520"):
        asyncio.run(_collect(provider.stream_chat([{"role": "user", "content": "Question"}])))

    message = caplog.records[-1].getMessage()
    excerpt = message.split(" response_excerpt=", maxsplit=1)[1]
    assert "content_type=text/html; charset=UTF-8" in message
    assert "[REDACTED]" in excerpt
    assert "exposed-token" not in excerpt
    assert excerpt.endswith(provider_module.PROVIDER_ERROR_TRUNCATION_MARKER)
    assert len(excerpt) == provider_module.MAX_PROVIDER_ERROR_EXCERPT_CHARS


def _sse_body(*chunks: dict) -> str:
    """Render provider chunks as one server-sent event stream."""
    events = "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks)
    return events + "data: [DONE]\n\n"


def _delta_chunk(delta: dict) -> dict:
    return {"choices": [{"delta": delta}]}


def _streaming_provider(
    monkeypatch: pytest.MonkeyPatch,
    body: str,
    requests: list[httpx.Request] | None = None,
    *,
    include_usage: bool = False,
    model_metadata: dict | None = None,
    models_status: int = 200,
) -> OpenAiCompatibleProvider:
    """Build a provider whose endpoint replies with one prepared stream."""
    real_async_client = httpx.AsyncClient

    def handle(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(request)
        if request.url.path.endswith("/models"):
            return httpx.Response(models_status, json=model_metadata if model_metadata is not None else {"data": []})
        return httpx.Response(200, headers={"Content-Type": "text/event-stream"}, text=body)

    monkeypatch.setattr(
        provider_module.httpx,
        "AsyncClient",
        lambda **kwargs: real_async_client(transport=httpx.MockTransport(handle), **kwargs),
    )
    return OpenAiCompatibleProvider(
        AiSettings(
            provider_base_url="https://provider.example/v1",
            provider_api_key="test-token",
            provider_model="test-model",
            auth_token="ai-shared-test-token",
            # These tests read one response. Retry policy has its own tests.
            provider_max_attempts=1,
        ),
        include_usage=include_usage,
    )


def _transport_provider(
    monkeypatch: pytest.MonkeyPatch,
    handler,
    *,
    include_attempts: bool = False,
    **settings_overrides,
) -> OpenAiCompatibleProvider:
    """Build a provider around a stateful mock transport."""
    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        provider_module.httpx,
        "AsyncClient",
        lambda **kwargs: real_async_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    settings = {
        "provider_base_url": "https://provider.example/v1",
        "provider_api_key": "test-token",
        "provider_model": "test-model",
        "auth_token": "ai-shared-test-token",
    }
    settings.update(settings_overrides)
    return OpenAiCompatibleProvider(AiSettings(**settings), include_attempts=include_attempts)


def _events(provider: OpenAiCompatibleProvider, tools: list[dict] | None = None) -> list:
    messages: list[ChatMessage] = [{"role": "user", "content": "Question"}]
    return asyncio.run(_collect(provider.stream_events(messages, tools)))


TOOLS = [{"type": "function", "function": {"name": "schedule_patch", "parameters": {"type": "object"}}}]


@pytest.mark.parametrize("status", [408, 409, 429, 500, 502, 503, 504, 524])
def test_retries_transient_http_errors_with_stable_affinity_and_distinct_cost_records(monkeypatch, status):
    requests = []

    def handle(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(status, json={"error": {"message": "Temporary upstream failure"}})
        return httpx.Response(200, text=_sse_body(_delta_chunk({"content": "Recovered"})))

    provider = _transport_provider(monkeypatch, handle, provider_retry_backoff_seconds=0).with_session_id("chat-1")
    provider._include_costs = True
    events = _events(provider)
    assert TextDelta("Recovered") in events
    assert len(requests) == 2 and all(request.headers["x-session-id"] == "chat-1" for request in requests)
    calls = [event for event in events if isinstance(event, ProviderCall)]
    assert len({event.id for event in calls}) == 2
    assert [event.status for event in calls] == ["pending", "unavailable", "pending", "unavailable"]


@pytest.mark.parametrize(
    "status,body,headers",
    [
        (401, "Unauthorized", {"x-should-retry": "true"}),
        (403, "Forbidden", {}),
        (400, "Invalid request", {}),
        (429, '{"code":"insufficient_quota"}', {"x-should-retry": "true"}),
        (429, "Monthly usage limit reached", {}),
        (429, "Out of budget", {}),
        (503, "Billing account disabled", {}),
        (503, "Busy", {"x-should-retry": "false"}),
    ],
)
def test_deterministic_provider_errors_fail_without_retry(monkeypatch, status, body, headers):
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(status, text=body, headers=headers)

    provider = _transport_provider(monkeypatch, handle, provider_retry_backoff_seconds=0)
    with pytest.raises(ProviderError, match=f"HTTP {status}"):
        _events(provider)
    assert len(requests) == 1


def test_retries_connection_errors_and_incomplete_streams_with_notices(monkeypatch):
    attempts = []

    def handle(request):
        attempts.append(request)
        if len(attempts) == 1:
            raise httpx.ConnectError("refused", request=request)
        if len(attempts) == 2:
            return httpx.Response(200, text=f"data: {json.dumps(_delta_chunk({}))}\n\n")
        return httpx.Response(200, text=_sse_body(_delta_chunk({"content": "Recovered"})))

    delays = []

    async def record_sleep(delay):
        delays.append(delay)

    monkeypatch.setattr(provider_module.asyncio, "sleep", record_sleep)
    monkeypatch.setattr("nurse_scheduling.ai.provider_retry.random.random", lambda: 0)
    events = _events(_transport_provider(monkeypatch, handle))
    assert events == [
        ProviderRetry("The AI provider is unavailable. Retrying in 2 s (attempt 2 of 5)."),
        ProviderRetry("The AI provider stream ended before completion. Retrying in 4 s (attempt 3 of 5)."),
        TextDelta("Recovered"),
        ResponseEnd(None),
    ]
    assert delays == [2, 4]


def test_retry_budget_ends_retries_before_the_attempt_limit(monkeypatch):
    attempts = []
    clock = [0.0]
    real_monotonic = time.monotonic

    def handle(request):
        attempts.append(request)
        return httpx.Response(503, headers={"Retry-After": "50"})

    async def advance(delay):
        clock[0] += delay

    monkeypatch.setattr(provider_module.asyncio, "sleep", advance)
    monkeypatch.setattr(provider_module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    assert time.monotonic is real_monotonic
    with pytest.raises(ProviderError, match="HTTP 503"):
        _events(_transport_provider(monkeypatch, handle))
    # Failures at 0 and 50 seconds retry. A third wait would end after the 120-second budget.
    assert len(attempts) == 3
    assert clock[0] == 100


@pytest.mark.parametrize("partial_text", [False, True], ids=["waiting-for-headers", "streaming"])
@pytest.mark.parametrize("coarse_clock", [False, True], ids=["system-clock", "unchanged-clock-tick"])
def test_retry_budget_interrupts_a_stalled_request(monkeypatch, partial_text, coarse_clock):
    attempts = []
    closed = []

    class StalledStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield f"data: {json.dumps(_delta_chunk({'content': 'Partial'}))}\n\n".encode()
            await asyncio.Event().wait()

        async def aclose(self):
            closed.append(True)

    async def handle(request):
        attempts.append(request)
        if len(attempts) == 1:
            return httpx.Response(503)
        if partial_text:
            return httpx.Response(200, stream=StalledStream())
        try:
            await asyncio.Event().wait()
        finally:
            closed.append(True)

    monkeypatch.setattr(provider_module, "PROVIDER_RETRY_BUDGET_SECONDS", 0.02)
    if coarse_clock:
        # A deadline timer can fire before a coarse clock reaches the deadline.
        # Replace only the provider clock so asyncio's timers still advance.
        monkeypatch.setattr(provider_module, "time", SimpleNamespace(monotonic=lambda: 0.0))
    provider = _transport_provider(monkeypatch, handle, provider_retry_backoff_seconds=0)

    async def run():
        with pytest.raises(ProviderError, match="timed out"):
            await asyncio.wait_for(_collect(provider.stream_events([])), timeout=0.5)

    asyncio.run(run())
    assert len(attempts) == 2
    assert closed == [True]


@pytest.mark.parametrize("expired_by", [0, 1], ids=["at-deadline", "past-deadline"])
def test_expired_retry_budget_does_not_send_another_request(monkeypatch, expired_by):
    attempts = []
    retries = []
    clock = [0.0]

    def handle(request):
        attempts.append(request)
        if len(attempts) == 1:
            return httpx.Response(503)
        return httpx.Response(200, text=_sse_body(_delta_chunk({"content": "Too late"})))

    monkeypatch.setattr(provider_module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    provider = _transport_provider(monkeypatch, handle, provider_retry_backoff_seconds=0)

    async def run():
        with pytest.raises(ProviderError, match="timed out"):
            async for event in provider.stream_events([]):
                if isinstance(event, ProviderRetry):
                    retries.append(event)
                    clock[0] = provider_module.PROVIDER_RETRY_BUDGET_SECONDS + expired_by

    asyncio.run(run())
    assert len(attempts) == 1
    assert len(retries) == 1


def test_retries_discard_partial_tool_calls(monkeypatch):
    streams = []

    def handle(_request):
        stream = _InterruptedStream(
            _delta_chunk({"tool_calls": [{"index": 0, "id": "partial", "function": {"name": "schedule_patch"}}]})
        )
        streams.append(stream)
        return httpx.Response(200, stream=stream)

    provider = _transport_provider(monkeypatch, handle, provider_max_attempts=2, provider_retry_backoff_seconds=0)
    events = []

    async def consume():
        async for event in provider.stream_events([ChatMessage(role="user", content="Edit")], TOOLS):
            events.append(event)

    with pytest.raises(ProviderError, match="timed out"):
        asyncio.run(consume())
    assert len(streams) == 2
    assert all(stream.closed for stream in streams)
    assert not any(isinstance(event, (ToolCallRequest, ResponseEnd)) for event in events)


def test_retries_pre_stream_timeouts_with_exponential_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("nurse_scheduling.ai.provider_retry.random.random", lambda: 0)
    attempts: list[httpx.Request] = []
    delays: list[float] = []

    def handle(request: httpx.Request) -> httpx.Response:
        attempts.append(request)
        if len(attempts) < 3:
            raise httpx.ReadTimeout("provider stalled", request=request)
        return httpx.Response(200, text=_sse_body(_delta_chunk({"content": "Recovered"})))

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(provider_module.asyncio, "sleep", record_sleep)
    provider = _transport_provider(
        monkeypatch,
        handle,
        include_attempts=True,
        provider_max_attempts=3,
        provider_retry_backoff_seconds=0.25,
    )

    assert [event for event in _events(provider) if not isinstance(event, ProviderRetry)] == [
        ProviderAttempt(1),
        ProviderAttempt(2),
        ProviderAttempt(3),
        TextDelta("Recovered"),
        ResponseEnd(None),
    ]
    assert len(attempts) == 3
    assert delays == [0.25, 0.5]


def test_reports_timeout_after_all_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        attempts.append(request)
        raise httpx.ReadTimeout("provider stalled", request=request)

    provider = _transport_provider(
        monkeypatch,
        handle,
        provider_max_attempts=3,
        provider_retry_backoff_seconds=0,
    )

    with pytest.raises(ProviderError, match="timed out before starting the response"):
        _events(provider)

    assert len(attempts) == 3


class _InterruptedStream(httpx.AsyncByteStream):
    """Emit SSE fragments before simulating a stalled response body."""

    def __init__(self, *chunks: dict) -> None:
        self.body = "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks)
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield self.body.encode()
        raise httpx.ReadTimeout("provider stalled")

    async def aclose(self) -> None:
        self.closed = True


def test_reports_streaming_timeout_after_all_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts: list[httpx.Request] = []
    events: list[object] = []

    def handle(request: httpx.Request) -> httpx.Response:
        attempts.append(request)
        return httpx.Response(200, stream=_InterruptedStream(_delta_chunk({"content": "Partial"})))

    provider = _transport_provider(
        monkeypatch,
        handle,
        provider_max_attempts=3,
        provider_retry_backoff_seconds=0,
    )

    async def consume() -> None:
        messages: list[ChatMessage] = [{"role": "user", "content": "Question"}]
        async for event in provider.stream_events(messages):
            events.append(event)

    with pytest.raises(ProviderError, match="timed out while streaming the response"):
        asyncio.run(consume())

    assert [event for event in events if not isinstance(event, ProviderRetry)] == [TextDelta("Partial")] * 3
    assert len(attempts) == 3


def test_continues_partial_answer_with_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("nurse_scheduling.ai.provider_retry.random.random", lambda: 0)
    requests: list[dict] = []
    delays: list[float] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        if len(requests) < 3:
            return httpx.Response(
                200,
                stream=_InterruptedStream(
                    _delta_chunk({"content": "First. " if len(requests) == 1 else "Second. "}),
                    _delta_chunk({"reasoning_content": "Private reasoning"}),
                ),
            )
        return httpx.Response(200, text=_sse_body(_delta_chunk({"content": "Third."})))

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(provider_module.asyncio, "sleep", record_sleep)
    provider = _transport_provider(monkeypatch, handle)
    events = _events(provider, TOOLS)
    assert "".join(event.text for event in events if isinstance(event, TextDelta)) == "First. Second. Third."
    assert events[-1] == ResponseEnd(None)
    assert delays == [2, 4]
    for request, partial in zip(requests[1:], ["First. ", "First. Second. "], strict=True):
        assert request["messages"][:-2] == requests[0]["messages"]
        assert request["messages"][-2] == {"role": "assistant", "content": partial}
        assert request["messages"][-1] == {
            "role": "user",
            "content": f"[App event] The response was interrupted after {len(partial)} text characters.",
        }
        assert "Private reasoning" not in json.dumps(request)
        assert request["tools"] == TOOLS


def test_cancellation_during_backoff_stops_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    streams: list[_InterruptedStream] = []

    def handle(request: httpx.Request) -> httpx.Response:
        stream = _InterruptedStream(_delta_chunk({"content": "Partial"}))
        streams.append(stream)
        return httpx.Response(200, stream=stream)

    async def cancel_sleep(delay: float) -> None:
        assert streams[0].closed
        raise asyncio.CancelledError

    monkeypatch.setattr(provider_module.asyncio, "sleep", cancel_sleep)
    provider = _transport_provider(monkeypatch, handle)
    with pytest.raises(asyncio.CancelledError):
        _events(provider)
    assert len(streams) == 1


@pytest.mark.parametrize(
    "chunk",
    [
        _delta_chunk({"reasoning_content": "Thinking"}),
        _delta_chunk({}),
        {"choices": [], "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}},
    ],
    ids=["reasoning", "empty", "usage"],
)
def test_retries_without_partial_answer(monkeypatch: pytest.MonkeyPatch, chunk: dict) -> None:
    requests: list[dict] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        if len(requests) == 1:
            return httpx.Response(200, stream=_InterruptedStream(chunk))
        return httpx.Response(200, text=_sse_body(_delta_chunk({"content": "Recovered"})))

    provider = _transport_provider(monkeypatch, handle, provider_retry_backoff_seconds=0)
    assert TextDelta("Recovered") in _events(provider)
    assert requests[0] == requests[1]


@pytest.mark.parametrize(
    ("field", "limit", "message"),
    [
        ("content", "MAX_RESPONSE_TEXT_CHARS", "more text"),
        ("reasoning_content", "MAX_RESPONSE_REASONING_CHARS", "more reasoning"),
    ],
)
def test_output_limits_apply_across_retries(monkeypatch: pytest.MonkeyPatch, field, limit, message) -> None:
    monkeypatch.setattr(provider_module, limit, 5)
    streams: list[_InterruptedStream] = []

    def handle(request: httpx.Request) -> httpx.Response:
        stream = _InterruptedStream(_delta_chunk({field: "1234"}))
        streams.append(stream)
        return httpx.Response(200, stream=stream)

    provider = _transport_provider(monkeypatch, handle, provider_retry_backoff_seconds=0)
    with pytest.raises(ProviderResponseLimitError, match=message):
        _events(provider)
    assert len(streams) == 2
    assert all(stream.closed for stream in streams)


def test_interrupted_tool_call_is_regenerated_and_executed_once(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[dict] = []
    executed: list[tuple[str, str]] = []
    partial = {"index": 0, "id": "lost", "function": {"name": "schedule_patch", "arguments": '{"lost":'}}
    complete = {"index": 0, "id": "retry", "function": {"name": "schedule_patch", "arguments": "{}"}}

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        if len(requests) == 1:
            body = _delta_chunk({"content": "Checking. ", "tool_calls": [partial]})
            return httpx.Response(200, stream=_InterruptedStream(body))
        if len(requests) == 2:
            return httpx.Response(200, text=_sse_body(_delta_chunk({"tool_calls": [complete]})))
        return httpx.Response(200, text=_sse_body(_delta_chunk({"content": "Done."})))

    async def execute(name: str, arguments: str) -> AgentToolOutcome:
        executed.append((name, arguments))
        return AgentToolOutcome("Applied", True)

    provider = _transport_provider(monkeypatch, handle, provider_retry_backoff_seconds=0)
    tools = bind_agent_tools(TOOLS, execute)
    asyncio.run(_collect(agent_loop(provider, [{"role": "user", "content": "Edit"}], tools)))
    assert executed == [("schedule_patch", "{}")]
    assert len(requests) == 3
    assert '"lost"' not in json.dumps(requests[1:])
    assert requests[-1]["messages"][-1] == {"role": "tool", "tool_call_id": "retry", "content": "Applied"}


def test_reconstructs_one_tool_call_from_streamed_fragments(monkeypatch: pytest.MonkeyPatch) -> None:
    body = _sse_body(
        _delta_chunk({"tool_calls": [{"index": 0, "id": "call_1", "function": {"name": "schedule_patch"}}]}),
        _delta_chunk({"tool_calls": [{"index": 0, "function": {"arguments": '{"operations":'}}]}),
        _delta_chunk({"tool_calls": [{"index": 0, "function": {"arguments": "[]}"}}]}),
    )

    events = _events(_streaming_provider(monkeypatch, body), TOOLS)

    assert events == [
        ToolCallRequest((ToolCall(id="call_1", name="schedule_patch", arguments='{"operations":[]}'),)),
        ResponseEnd(None),
    ]


def test_reconstructs_parallel_tool_calls_in_index_order(monkeypatch: pytest.MonkeyPatch) -> None:
    body = _sse_body(
        _delta_chunk({"tool_calls": [{"index": 1, "id": "call_2", "function": {"name": "b", "arguments": "{}"}}]}),
        _delta_chunk({"tool_calls": [{"index": 0, "id": "call_1", "function": {"name": "a", "arguments": "{}"}}]}),
    )

    events = _events(_streaming_provider(monkeypatch, body), TOOLS)

    assert [call.name for call in events[0].calls] == ["a", "b"]


def test_separates_tool_calls_when_the_provider_omits_the_index(monkeypatch: pytest.MonkeyPatch) -> None:
    body = _sse_body(
        _delta_chunk({"tool_calls": [{"id": "call_1", "function": {"name": "a", "arguments": '{"x":'}}]}),
        _delta_chunk({"tool_calls": [{"function": {"arguments": "1}"}}]}),
        _delta_chunk({"tool_calls": [{"id": "call_2", "function": {"name": "b", "arguments": "{}"}}]}),
    )

    events = _events(_streaming_provider(monkeypatch, body), TOOLS)

    assert [(call.id, call.name, call.arguments) for call in events[0].calls] == [
        ("call_1", "a", '{"x":1}'),
        ("call_2", "b", "{}"),
    ]


def test_streams_text_before_the_tool_call_it_ends_with(monkeypatch: pytest.MonkeyPatch) -> None:
    body = _sse_body(
        _delta_chunk({"content": "Checking. "}),
        _delta_chunk({"tool_calls": [{"index": 0, "id": "call_1", "function": {"name": "a", "arguments": "{}"}}]}),
    )
    provider = _streaming_provider(monkeypatch, body)

    events = _events(provider, TOOLS)

    assert events[0] == TextDelta("Checking. ")
    assert isinstance(events[1], ToolCallRequest)


def test_stream_chat_yields_text_only(monkeypatch: pytest.MonkeyPatch) -> None:
    body = _sse_body(
        _delta_chunk({"content": "Answer"}),
        _delta_chunk({"tool_calls": [{"index": 0, "id": "call_1", "function": {"name": "a", "arguments": "{}"}}]}),
    )
    provider = _streaming_provider(monkeypatch, body)
    messages: list[ChatMessage] = [{"role": "user", "content": "Question"}]

    assert asyncio.run(_collect(provider.stream_chat(messages))) == ["Answer"]


def test_sends_tools_only_when_they_are_offered(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[httpx.Request] = []
    provider = _streaming_provider(monkeypatch, _sse_body(_delta_chunk({"content": "Answer"})), requests)

    _events(provider, TOOLS)
    _events(provider)

    with_tools = json.loads(requests[0].content)
    without_tools = json.loads(requests[1].content)
    assert with_tools["tools"] == TOOLS
    assert with_tools["tool_choice"] == "auto"
    assert "tools" not in without_tools
    assert "tool_choice" not in without_tools


def test_requests_and_streams_token_usage_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[httpx.Request] = []
    usage = {
        "prompt_tokens": 120,
        "completion_tokens": 30,
        "total_tokens": 150,
        "prompt_tokens_details": {"cached_tokens": 80},
        "completion_tokens_details": {"reasoning_tokens": 12},
    }
    body = _sse_body(_delta_chunk({"content": "Answer"}), {"choices": [], "usage": usage})

    events = _events(_streaming_provider(monkeypatch, body, requests, include_usage=True))

    assert json.loads(requests[-1].content)["stream_options"] == {"include_usage": True}
    assert events == [TextDelta("Answer"), TokenUsage(120, 30, 150, 80, 12), ResponseEnd(None)]


@pytest.mark.parametrize(
    ("model_metadata", "expected"),
    [
        ({"data": [{"id": "other-model", "max_model_len": 9999}, {"id": "test-model", "max_model_len": 16384}]}, 16384),
        ({"data": [{"id": "test-model", "context_length": 8192}]}, 8192),
        ({"data": [{"id": "other-model", "max_model_len": 9999}]}, None),
        ({"data": [{"id": "test-model", "max_model_len": -1}]}, None),
        ({"data": [{"id": "test-model", "max_model_len": True}]}, None),
        ({"data": None}, None),
    ],
    ids=["configured-model", "context-length", "other-model", "invalid-limit", "boolean-limit", "invalid-model-list"],
)
def test_discovers_and_caches_the_configured_model_context_limit(monkeypatch, model_metadata, expected) -> None:
    requests: list[httpx.Request] = []
    provider = _streaming_provider(
        monkeypatch,
        _sse_body(_delta_chunk({"content": "Answer"})),
        requests,
        include_usage=True,
        model_metadata=model_metadata,
    )

    assert _events(provider) == _events(provider) == [TextDelta("Answer"), ResponseEnd(None)]

    assert provider.context_tokens == expected
    assert [request.method for request in requests] == ["GET", "POST", "POST"]
    assert str(requests[0].url) == "https://provider.example/v1/models"
    assert requests[0].headers["Authorization"] == "Bearer test-token"


@pytest.mark.parametrize("status", [403, 404, 503])
def test_missing_model_metadata_does_not_prevent_chat_or_usage(monkeypatch, status) -> None:
    usage = {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150}
    provider = _streaming_provider(
        monkeypatch,
        _sse_body(_delta_chunk({"content": "Answer"}), {"choices": [], "usage": usage}),
        include_usage=True,
        models_status=status,
    )

    assert _events(provider) == [TextDelta("Answer"), TokenUsage(120, 30, 150), ResponseEnd(None)]
    assert provider.context_tokens is None


@pytest.mark.parametrize("models_status", [200, 503], ids=["discovered", "unavailable"])
def test_session_and_output_copies_share_model_limit_discovery(monkeypatch, models_status):
    requests = []

    async def handle(request):
        requests.append(request)
        if request.method == "GET":
            await asyncio.sleep(0)
            return httpx.Response(
                models_status,
                json={
                    "data": [
                        {
                            "id": "test-model",
                            "context_length": 32000,
                            "max_output_tokens": 8192,
                            "supported_openai_params": ["max_completion_tokens"],
                        }
                    ]
                },
            )
        return httpx.Response(200, text=_sse_body(_delta_chunk({"content": "Done"})))

    original = _transport_provider(monkeypatch, handle)
    original._include_usage = True
    first = original.with_session_id("first").with_output_limit(1000)
    second = original.with_output_limit(2000).with_session_id("second")

    async def run():
        await asyncio.gather(first.prepare_context(), second.prepare_context())
        later = original.with_session_id("later").with_output_limit(3000)
        await asyncio.gather(*(_collect(provider.stream_events([])) for provider in (first, second, later)))
        return later

    later = asyncio.run(run())
    assert len([request for request in requests if request.method == "GET"]) == 1
    parameter = "max_completion_tokens" if models_status == 200 else "max_tokens"
    for provider in (original, first, second, later):
        assert provider.context_tokens == (32000 if models_status == 200 else None)
        assert provider.output_tokens == (8192 if models_status == 200 else None)
        assert provider.output_token_parameter == parameter
    completions = [request for request in requests if request.method == "POST"]
    assert {request.headers["x-session-id"]: json.loads(request.content)[parameter] for request in completions} == {
        "first": 1000,
        "second": 2000,
        "later": 3000,
    }
    assert original._session_id is None and original._max_output_tokens is None


def test_skips_a_choiceless_chunk_that_carries_no_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    body = _sse_body({"choices": []}, _delta_chunk({"content": "Answer"}))

    events = _events(_streaming_provider(monkeypatch, body))

    assert events == [TextDelta("Answer"), ResponseEnd(None)]


@pytest.mark.parametrize("details", [None, {}, {"cached_tokens": None}, {"cached_tokens": 0}])
def test_distinguishes_missing_cache_usage_from_zero(monkeypatch: pytest.MonkeyPatch, details) -> None:
    usage = {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150, "prompt_tokens_details": details}
    events = _events(_streaming_provider(monkeypatch, _sse_body({"choices": [], "usage": usage}), include_usage=True))

    assert events == [TokenUsage(120, 30, 150, 0 if details == {"cached_tokens": 0} else None), ResponseEnd(None)]


def test_missing_cache_usage_propagates_across_provider_turns() -> None:
    reported = TokenUsage(120, 30, 150, 80)
    missing = TokenUsage(120, 30, 150)

    assert (reported + reported).cached_prompt_tokens == 160
    assert (reported + missing).cached_prompt_tokens is None
    assert (missing + reported).cached_prompt_tokens is None


def test_does_not_request_token_usage_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[httpx.Request] = []

    _events(_streaming_provider(monkeypatch, _sse_body(_delta_chunk({"content": "Answer"})), requests))

    assert "stream_options" not in json.loads(requests[0].content)


def test_rejects_more_tool_calls_than_the_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    body = _sse_body(
        _delta_chunk(
            {
                "tool_calls": [
                    {"index": index, "id": f"call_{index}", "function": {"name": "a", "arguments": "{}"}}
                    for index in range(provider_module.MAX_TOOL_CALLS_PER_RESPONSE + 1)
                ]
            }
        )
    )

    with pytest.raises(ProviderResponseLimitError, match="more than"):
        _events(_streaming_provider(monkeypatch, body), TOOLS)


def test_rejects_oversized_tool_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    oversized = "x" * (provider_module.MAX_TOOL_ARGUMENT_CHARS + 1)
    body = _sse_body(
        _delta_chunk({"tool_calls": [{"index": 0, "id": "call_1", "function": {"name": "a", "arguments": oversized}}]})
    )

    with pytest.raises(ProviderResponseLimitError, match="too large"):
        _events(_streaming_provider(monkeypatch, body), TOOLS)


def test_rejects_a_tool_call_without_a_name(monkeypatch: pytest.MonkeyPatch) -> None:
    body = _sse_body(_delta_chunk({"tool_calls": [{"index": 0, "id": "call_1", "function": {"arguments": "{}"}}]}))

    with pytest.raises(ProviderError, match="without a name"):
        _events(_streaming_provider(monkeypatch, body), TOOLS)


@pytest.mark.parametrize("field", ["reasoning_content", "reasoning", "reasoning_text"])
def test_streams_reasoning_separately_from_the_answer(monkeypatch: pytest.MonkeyPatch, field: str) -> None:
    body = _sse_body(
        _delta_chunk({field: "The ward "}),
        _delta_chunk({field: "has 3 nurses."}),
        _delta_chunk({"content": "Yes."}),
    )

    events = _events(_streaming_provider(monkeypatch, body))

    assert events == [
        ReasoningDelta("The ward "),
        ReasoningDelta("has 3 nurses."),
        TextDelta("Yes."),
        ReasoningReplay(
            {field: "The ward has 3 nurses."},
            provider_module.ProviderIdentity("https://provider.example/v1", "test-model"),
        ),
        ResponseEnd(None),
    ]


def test_rejects_an_answer_longer_than_the_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    body = _sse_body(_delta_chunk({"content": "x" * (provider_module.MAX_RESPONSE_TEXT_CHARS + 1)}))

    with pytest.raises(ProviderResponseLimitError, match="more text than"):
        _events(_streaming_provider(monkeypatch, body))


def test_rejects_reasoning_longer_than_the_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    body = _sse_body(_delta_chunk({"reasoning_content": "x" * (provider_module.MAX_RESPONSE_REASONING_CHARS + 1)}))

    with pytest.raises(ProviderResponseLimitError, match="more reasoning than"):
        _events(_streaming_provider(monkeypatch, body))


@pytest.mark.parametrize("finish_reason", [None, "stop", "tool_calls", "length", "content_filter"])
@pytest.mark.parametrize("done", [False, True])
def test_completion_is_checked_before_releasing_tool_calls(monkeypatch, finish_reason, done):
    chunk = _delta_chunk({"tool_calls": [{"index": 0, "id": "edit", "function": {"name": "edit", "arguments": "{}"}}]})
    chunk["choices"][0]["finish_reason"] = finish_reason
    body = _sse_body(chunk)
    if not done:
        body = body.removesuffix("data: [DONE]\n\n")
    provider = _streaming_provider(monkeypatch, body)
    seen = []

    async def consume():
        async for event in provider.stream_events([{"role": "user", "content": "Edit"}], TOOLS):
            seen.append(event)

    if finish_reason == "content_filter" or (finish_reason is None and not done):
        with pytest.raises(ProviderError):
            asyncio.run(consume())
        assert not any(isinstance(event, ToolCallRequest) for event in seen)
    else:
        asyncio.run(consume())
        assert seen == [ToolCallRequest((ToolCall("edit", "edit", "{}"),)), ResponseEnd(finish_reason)]


@pytest.mark.parametrize("chunk", [[], {"choices": [None]}, {"choices": [{"delta": None}]}])
def test_malformed_stream_shapes_raise_provider_error(monkeypatch, chunk):
    provider = _streaming_provider(monkeypatch, _sse_body(chunk))
    with pytest.raises(ProviderError, match="invalid stream"):
        _events(provider)


@pytest.mark.parametrize("initial_reason", ["length", "content_filter", "tool_calls"])
def test_conflicting_finish_reasons_cannot_release_tool_calls(monkeypatch, initial_reason):
    first = _delta_chunk({"tool_calls": [{"index": 0, "id": "edit", "function": {"name": "edit", "arguments": "{}"}}]})
    first["choices"][0]["finish_reason"] = initial_reason
    second = {"choices": [{"delta": {}, "finish_reason": "stop"}]}
    provider = _streaming_provider(monkeypatch, _sse_body(first, second))
    seen = []

    async def consume():
        async for event in provider.stream_events([{"role": "user", "content": "Edit"}], TOOLS):
            seen.append(event)

    with pytest.raises(ProviderError, match="conflicting finish reasons"):
        asyncio.run(consume())
    assert not any(isinstance(event, ToolCallRequest) for event in seen)


@pytest.mark.parametrize(
    "delta",
    [
        {"content": "Late answer"},
        {"reasoning": "Late thought"},
        {"tool_calls": [{"index": 0, "function": {"arguments": "changed"}}]},
    ],
    ids=["text", "reasoning", "tool-arguments"],
)
def test_output_after_completion_cannot_release_tool_calls(monkeypatch, delta):
    first = _delta_chunk({"tool_calls": [{"index": 0, "id": "edit", "function": {"name": "edit", "arguments": "{}"}}]})
    first["choices"][0]["finish_reason"] = "tool_calls"
    provider = _streaming_provider(monkeypatch, _sse_body(first, _delta_chunk(delta)))
    with pytest.raises(ProviderError, match="output after completion"):
        _events(provider, TOOLS)


def test_duplicate_empty_completion_and_usage_chunks_are_accepted(monkeypatch):
    final = {"choices": [{"delta": {"content": "Done"}, "finish_reason": "stop"}]}
    repeated = {"choices": [{"delta": {}, "finish_reason": "stop"}]}
    usage = {"choices": [], "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}
    provider = _streaming_provider(monkeypatch, _sse_body(final, repeated, usage))
    assert _events(provider) == [TextDelta("Done"), TokenUsage(1, 1, 2), ResponseEnd("stop")]


@pytest.mark.parametrize("reason,done", [("stop", True), ("length", False), (None, True), (None, False)])
def test_stream_end_diagnostics_record_signals_without_response_text(monkeypatch, caplog, reason, done):
    import logging

    chunk = _delta_chunk({"content": "private words Even", "reasoning_content": "private reasoning"})
    chunk["choices"][0]["finish_reason"] = reason
    body = _sse_body(chunk)
    if not done:
        body = body.removesuffix("data: [DONE]\n\n")
    caplog.set_level(logging.INFO, logger="nurse_scheduling.ai.provider")
    provider = _streaming_provider(monkeypatch, body)
    if reason is None and not done:
        with pytest.raises(ProviderError, match="before completion"):
            _events(provider)
    else:
        assert _events(provider)[-1] == ResponseEnd(reason)
    assert f"finish_reason={reason} done_received={done}" in caplog.text
    assert "text_chars=18 reasoning_chars=17 tool_calls=0" in caplog.text
    assert "private words" not in caplog.text and "private reasoning" not in caplog.text


def test_native_reasoning_metadata_round_trips_through_tool_turns_and_chat_runs(monkeypatch):
    from nurse_scheduling.ai.context import prepare_provider_request, projected_history, retained_entries
    from nurse_scheduling.ai.transcript import UserMessage, entry_from_record, entry_record

    details = [
        {"type": "reasoning.text", "text": "Plan", "signature": "signed", "id": "r", "index": 0},
        {"type": "reasoning.encrypted", "data": "cipher", "id": "secret", "format": "native"},
    ]
    blocks = [
        {"type": "thinking", "thinking": "Plan", "signature": "signature"},
        {"type": "redacted_thinking", "data": "opaque"},
    ]
    bodies = [
        _sse_body(
            _delta_chunk(
                {
                    "reasoning_content": "Plan",
                    "reasoning_details": details[:1],
                    "thinking_blocks": [{"type": "thinking", "thinking": "Plan", "signature": "sig"}],
                }
            ),
            _delta_chunk(
                {
                    "reasoning_details": [{"type": "reasoning.text", "text": " more", "index": 0}, details[1]],
                    "thinking_blocks": [{"type": "thinking", "signature": "nature"}, blocks[1]],
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "read-1",
                            "type": "function",
                            "function": {"name": "schedule_patch", "arguments": "{}"},
                            "extra_content": {"google": {"thought_signature": "tool-signature"}},
                        }
                    ],
                }
            ),
        ),
        _sse_body(_delta_chunk({"content": "Done"})),
        _sse_body(_delta_chunk({"content": "Next"})),
    ]
    requests = []

    def handle(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, text=bodies[len(requests) - 1])

    provider = _transport_provider(monkeypatch, handle)
    messages = []

    async def execute(_name, _arguments):
        return AgentToolOutcome("Saved tool result", True)

    async def run():
        async for _ in agent_loop(
            provider, [{"role": "user", "content": "Read"}], bind_agent_tools(TOOLS, execute), run_messages=messages
        ):
            pass
        entries = [UserMessage("Read"), *retained_entries(messages)]
        restored = [
            entry_from_record(kind, payload)
            for kind, payload in json.loads(json.dumps([entry_record(e) for e in entries]))
        ]
        await _collect(
            provider.stream_events(
                prepare_provider_request(projected_history(restored), [UserMessage("Next")], provider=provider.identity)
            )
        )

    asyncio.run(run())
    for request in (requests[1], requests[2]):
        assistant = next(m for m in request["messages"] if m["role"] == "assistant")
        assert assistant["reasoning_content"] == "Plan"
        assert assistant["reasoning_details"] == [{**details[0], "text": "Plan more"}, details[1]]
        assert assistant["thinking_blocks"] == blocks
        assert assistant["tool_calls"][0]["extra_content"]["google"]["thought_signature"] == "tool-signature"
        assert "Saved tool result" in str(request["messages"])
        assert "_provider" not in str(request)


def test_reasoning_metadata_is_bounded_and_rejected_after_completion(monkeypatch):
    monkeypatch.setattr(provider_module, "MAX_RESPONSE_REASONING_CHARS", 50)
    body = _sse_body(_delta_chunk({"reasoning_details": [{"type": "reasoning.encrypted", "data": "x" * 100}]}))
    with pytest.raises(ProviderResponseLimitError, match="reasoning metadata"):
        _events(_streaming_provider(monkeypatch, body))
    monkeypatch.undo()
    body = _sse_body(
        {"choices": [{"delta": {}, "finish_reason": "stop"}]},
        _delta_chunk({"thinking_blocks": [{"type": "redacted_thinking", "data": "x"}]}),
    )
    with pytest.raises(ProviderError, match="after completion"):
        _events(_streaming_provider(monkeypatch, body))


@pytest.mark.parametrize(
    ("status", "error", "overflow"),
    [
        (400, {"code": "context_length_exceeded"}, True),
        (413, {"message": "prompt is too long"}, True),
        (422, {"message": "maximum context length is 8000 tokens"}, True),
        (400, {"message": "invalid thinking signature"}, False),
        (401, {"code": "context_length_exceeded"}, False),
        (400, {"code": ["invalid"]}, False),
    ],
)
def test_context_overflow_is_distinct_from_other_provider_errors(monkeypatch, status, error, overflow):
    provider = _transport_provider(monkeypatch, lambda _request: httpx.Response(status, json={"error": error}))
    with pytest.raises(ProviderError) as caught:
        _events(provider)
    assert isinstance(caught.value, provider_module.ProviderContextOverflowError) == overflow


def test_preserves_separate_signed_thinking_blocks(monkeypatch):
    blocks = [
        {"type": "thinking", "thinking": "First decision", "signature": "signed-first"},
        {"type": "thinking", "thinking": "Second decision", "signature": "signed-second"},
        {"type": "redacted_thinking", "data": "opaque"},
    ]
    provider = _streaming_provider(monkeypatch, _sse_body(_delta_chunk({"thinking_blocks": blocks})))
    (replay,) = [event for event in _events(provider) if isinstance(event, ReasoningReplay)]
    assert replay.native["thinking_blocks"] == blocks


@pytest.mark.parametrize("blocks", [[{}], [{"type": []}]])
def test_malformed_reasoning_metadata_remains_a_provider_error(monkeypatch, blocks):
    provider = _streaming_provider(monkeypatch, _sse_body(_delta_chunk({"thinking_blocks": blocks})))
    with pytest.raises(ProviderError, match="invalid reasoning metadata"):
        _events(provider)


def test_session_affinity_survives_timeout_retries_without_reusing_attempt_ids(monkeypatch):
    from nurse_scheduling.ai.provider import ProviderCall

    requests = []

    def handle(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, stream=_InterruptedStream(_delta_chunk({"content": "Partial"})))
        return httpx.Response(200, text=_sse_body(_delta_chunk({"content": "Recovered"})))

    original = _transport_provider(monkeypatch, handle, provider_retry_backoff_seconds=0)
    original._include_costs = True
    provider = original.with_session_id("stable-chat-id")
    events = _events(provider)
    assert [request.headers.get("x-session-id") for request in requests] == ["stable-chat-id"] * 2
    calls = [event for event in events if isinstance(event, ProviderCall) and event.status == "pending"]
    assert len({call.id for call in calls}) == 2
    assert all(call.id != "stable-chat-id" for call in calls)


def test_concurrent_session_bindings_leave_the_shared_provider_unchanged(monkeypatch):
    captured = []

    async def handle(request):
        await asyncio.sleep(0)
        captured.append((json.loads(request.content)["messages"][0]["content"], request.headers.get("x-session-id")))
        return httpx.Response(200, text=_sse_body(_delta_chunk({"content": "Done"})))

    original = _transport_provider(monkeypatch, handle)
    original.context_tokens = 32000
    first = original.with_session_id("chat-a")
    second = original.with_session_id("chat-b")
    assert first.context_tokens == second.context_tokens == 32000
    assert first.identity == second.identity == original.identity

    async def run():
        await asyncio.gather(
            *(
                _collect(provider.stream_events([{"role": "user", "content": text}]))
                for provider, text in [(first, "a"), (second, "b"), (original, "unbound")]
            )
        )

    asyncio.run(run())
    assert sorted(captured) == [("a", "chat-a"), ("b", "chat-b"), ("unbound", None)]


def test_chat_uuid_reaches_tools_compaction_and_runs_after_restore(monkeypatch):
    from nurse_scheduling.ai.transcript import AssistantMessage, UserMessage

    from . import test_ai_basic as basic
    from .test_ai_optimizer import FakeOptimizerBackend

    captured = []
    expected_session = None

    def handle(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "test-model", "context_length": 32000}]})
        body = json.loads(request.content)
        summary = str(body["messages"][0].get("content", "")).startswith("You are a context summarization assistant.")
        captured.append(
            (
                request.headers.get("x-session-id"),
                expected_session,
                summary,
                any(message["role"] == "tool" for message in body["messages"]),
            )
        )
        if len(captured) == 1:
            delta = {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "read",
                        "type": "function",
                        "function": {"name": "read", "arguments": '{"path":"/workspace/schedule.yaml"}'},
                    }
                ]
            }
            reason = "tool_calls"
        else:
            delta = {"content": "Goal: inspect the current schedule." if summary else "Done."}
            reason = "stop"
        return httpx.Response(
            200,
            text=_sse_body(
                _delta_chunk(delta),
                {"choices": [{"delta": {}, "finish_reason": reason}]},
                {"choices": [], "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}},
            ),
        )

    provider = _transport_provider(monkeypatch, handle)
    provider._include_usage = True
    settings = basic.make_settings(max_history_messages=1000)
    app = basic.create_test_app(settings=settings, provider=provider, optimizer_backend=FakeOptimizerBackend())
    with basic.AuthenticatedTestClient(app) as client:
        first = basic.create_session(client, basic.schedule_yaml())
        second = basic.create_session(client, basic.schedule_yaml())
        for session_id, question in [(first, "Inspect schedule"), (first, "Follow up"), (second, "New chat")]:
            expected_session = session_id
            response = client.post(f"/sessions/{session_id}/messages", json={"message": question})
            assert basic.parse_sse(response.text)[-1][0] == "done"
        store = app.state.session_store
        session = store._sessions[first]
        # Retained context from an earlier run must also use the chat ID during compaction.
        snapshot = store.begin(first, session.owner_token)
        store.finish(
            first,
            [UserMessage("Earlier constraints " + "x" * 100000), AssistantMessage("Earlier answer")],
            snapshot=snapshot,
        )
        expected_session = first
        response = client.post(f"/sessions/{first}/messages", json={"message": "Continue"})
        events = basic.parse_sse(response.text)
        assert events[-1][0] == "done"
        assert any(kind == "context_usage" and data.get("max_tokens") == 32000 for kind, data in events)
        owner, expires, state = store.recovery_state(first)
        transcript, next_seq = list(session.transcript), session.next_entry_seq

    restarted = basic.create_test_app(settings=settings, provider=provider, optimizer_backend=FakeOptimizerBackend())
    restarted.state.session_store.restore(first, owner, state, expires, entries=transcript, next_entry_seq=next_seq)
    with basic.AuthenticatedTestClient(restarted) as client:
        client.cookies.set(basic.OWNER_COOKIE, owner)
        expected_session = first
        response = client.post(f"/sessions/{first}/messages", json={"message": "After restart"})
        assert basic.parse_sse(response.text)[-1][0] == "done"
    assert len(captured) >= 7
    assert any(summary for _, _, summary, _ in captured)
    assert any(tool for _, _, _, tool in captured)
    assert all(actual == expected for actual, expected, _, _ in captured)

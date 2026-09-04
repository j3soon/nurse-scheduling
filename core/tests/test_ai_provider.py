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
from collections.abc import AsyncIterator

import httpx
import pytest

from nurse_scheduling.ai import provider as provider_module
from nurse_scheduling.ai.config import AiSettings
from nurse_scheduling.ai.provider import (
    ChatMessage,
    OpenAiCompatibleProvider,
    ProviderAttempt,
    ProviderError,
    ReasoningDelta,
    TextDelta,
    TokenUsage,
    ToolCall,
    ToolCallRequest,
)


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
) -> OpenAiCompatibleProvider:
    """Build a provider whose endpoint replies with one prepared stream."""
    real_async_client = httpx.AsyncClient

    def handle(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(request)
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
    }
    settings.update(settings_overrides)
    return OpenAiCompatibleProvider(AiSettings(**settings), include_attempts=include_attempts)


def _events(provider: OpenAiCompatibleProvider, tools: list[dict] | None = None) -> list:
    messages: list[ChatMessage] = [{"role": "user", "content": "Question"}]
    return asyncio.run(_collect(provider.stream_events(messages, tools)))


TOOLS = [{"type": "function", "function": {"name": "schedule_patch", "parameters": {"type": "object"}}}]


def test_retries_pre_stream_timeouts_with_exponential_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
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

    assert _events(provider) == [ProviderAttempt(1), ProviderAttempt(2), ProviderAttempt(3), TextDelta("Recovered")]
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

    with pytest.raises(ProviderError, match="The AI provider timed out"):
        _events(provider)

    assert len(attempts) == 3


class _TimeoutAfterText(httpx.AsyncByteStream):
    """Emit visible output before simulating a stalled response body."""

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b'data: {"choices":[{"delta":{"content":"Partial"}}]}\n\n'
        raise httpx.ReadTimeout("provider stalled")


def test_does_not_retry_after_streaming_has_started(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts: list[httpx.Request] = []
    events: list[object] = []

    def handle(request: httpx.Request) -> httpx.Response:
        attempts.append(request)
        return httpx.Response(200, stream=_TimeoutAfterText())

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

    with pytest.raises(ProviderError, match="The AI provider timed out"):
        asyncio.run(consume())

    assert events == [TextDelta("Partial")]
    assert len(attempts) == 1


def test_reconstructs_one_tool_call_from_streamed_fragments(monkeypatch: pytest.MonkeyPatch) -> None:
    body = _sse_body(
        _delta_chunk({"tool_calls": [{"index": 0, "id": "call_1", "function": {"name": "schedule_patch"}}]}),
        _delta_chunk({"tool_calls": [{"index": 0, "function": {"arguments": '{"operations":'}}]}),
        _delta_chunk({"tool_calls": [{"index": 0, "function": {"arguments": "[]}"}}]}),
    )

    events = _events(_streaming_provider(monkeypatch, body), TOOLS)

    assert events == [ToolCallRequest((ToolCall(id="call_1", name="schedule_patch", arguments='{"operations":[]}'),))]


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

    assert json.loads(requests[0].content)["stream_options"] == {"include_usage": True}
    assert events == [TextDelta("Answer"), TokenUsage(120, 30, 150, 80, 12)]


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

    with pytest.raises(ProviderError, match="more than"):
        _events(_streaming_provider(monkeypatch, body), TOOLS)


def test_rejects_oversized_tool_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    oversized = "x" * (provider_module.MAX_TOOL_ARGUMENT_CHARS + 1)
    body = _sse_body(
        _delta_chunk({"tool_calls": [{"index": 0, "id": "call_1", "function": {"name": "a", "arguments": oversized}}]})
    )

    with pytest.raises(ProviderError, match="too large"):
        _events(_streaming_provider(monkeypatch, body), TOOLS)


def test_rejects_a_tool_call_without_a_name(monkeypatch: pytest.MonkeyPatch) -> None:
    body = _sse_body(_delta_chunk({"tool_calls": [{"index": 0, "id": "call_1", "function": {"arguments": "{}"}}]}))

    with pytest.raises(ProviderError, match="without a name"):
        _events(_streaming_provider(monkeypatch, body), TOOLS)


@pytest.mark.parametrize("field", ["reasoning_content", "reasoning"])
def test_streams_reasoning_separately_from_the_answer(monkeypatch: pytest.MonkeyPatch, field: str) -> None:
    body = _sse_body(
        _delta_chunk({field: "The ward "}),
        _delta_chunk({field: "has 3 nurses."}),
        _delta_chunk({"content": "Yes."}),
    )

    events = _events(_streaming_provider(monkeypatch, body))

    assert events == [ReasoningDelta("The ward "), ReasoningDelta("has 3 nurses."), TextDelta("Yes.")]


def test_rejects_an_answer_longer_than_the_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    body = _sse_body(_delta_chunk({"content": "x" * (provider_module.MAX_RESPONSE_TEXT_CHARS + 1)}))

    with pytest.raises(ProviderError, match="more text than"):
        _events(_streaming_provider(monkeypatch, body))


def test_rejects_reasoning_longer_than_the_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    body = _sse_body(_delta_chunk({"reasoning_content": "x" * (provider_module.MAX_RESPONSE_REASONING_CHARS + 1)}))

    with pytest.raises(ProviderError, match="more reasoning than"):
        _events(_streaming_provider(monkeypatch, body))

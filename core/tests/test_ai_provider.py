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
import logging
import re
from collections.abc import AsyncIterator

import httpx
import pytest

from nurse_scheduling.ai import provider as provider_module
from nurse_scheduling.ai.config import AiSettings
from nurse_scheduling.ai.provider import ChatMessage, OpenAiCompatibleProvider, ProviderError


async def _collect(stream: AsyncIterator[str]) -> list[str]:
    """Consume a provider stream so request errors are raised."""
    return [delta async for delta in stream]


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
            "<html>\n<body>Cloud proxy error 525</body>\n</html>",
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
    assert expected_logged_body in caplog.text
    assert "test-token" not in caplog.text

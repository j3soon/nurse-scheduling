"""OpenAI-compatible streaming provider adapter."""

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

import json
from collections.abc import AsyncIterator, Sequence
from typing import Protocol, TypedDict

import httpx

from .config import AiSettings


class ChatMessage(TypedDict):
    """One OpenAI-compatible chat message."""

    role: str
    content: str


class ChatProvider(Protocol):
    """Minimal provider boundary used by the chat application."""

    def stream_chat(self, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        """Yield text deltas for one assistant response."""
        ...


class ProviderError(RuntimeError):
    """A sanitized provider or protocol failure."""


class OpenAiCompatibleProvider:
    """Stream chat completions from an OpenAI-compatible HTTP endpoint."""

    def __init__(self, settings: AiSettings) -> None:
        self._settings = settings

    async def stream_chat(self, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        """Translate provider SSE chunks into plain text deltas."""
        timeout = httpx.Timeout(self._settings.provider_timeout_seconds, connect=10.0)
        headers = {"Authorization": f"Bearer {self._settings.provider_api_key}"}
        payload = {
            "model": self._settings.provider_model,
            "messages": list(messages),
            "stream": True,
        }

        try:
            async with (
                httpx.AsyncClient(timeout=timeout) as client,
                client.stream(
                    "POST",
                    f"{self._settings.provider_base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                ) as response,
            ):
                if response.status_code != 200:
                    await response.aread()
                    raise ProviderError(f"The AI provider returned HTTP {response.status_code}.")

                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw_data = line.removeprefix("data:").strip()
                    if raw_data == "[DONE]":
                        return
                    if not raw_data:
                        continue
                    try:
                        event = json.loads(raw_data)
                        delta = event["choices"][0]["delta"].get("content")
                    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
                        raise ProviderError("The AI provider returned an invalid stream.") from exc
                    if isinstance(delta, str) and delta:
                        yield delta
        except ProviderError:
            raise
        except httpx.TimeoutException as exc:
            raise ProviderError("The AI provider timed out.") from exc
        except httpx.HTTPError as exc:
            raise ProviderError("The AI provider is unavailable.") from exc

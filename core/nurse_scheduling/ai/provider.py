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
import logging
import re
from collections.abc import AsyncIterator, Sequence
from typing import Literal, Protocol, TypedDict
from uuid import uuid4

import httpx

from .config import AiSettings

logger = logging.getLogger("nurse_scheduling.ai.provider")
BEARER_TOKEN_PATTERN = re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9._~+/=-]+")
SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)(\b(?:api[_-]?key|access[_-]?token|authorization|secret)\b\s*[\"']?\s*[:=]\s*[\"']?)"
    r"([^\"'\s,;<}]+)"
)


class TextContentPart(TypedDict):
    """One text item in a multimodal chat message."""

    type: Literal["text"]
    text: str


# OpenAI-compatible shape: {"type": "image_url", "image_url": {"url": "data:..."}}.
# Separate types describe the outer content part and nested URL object precisely.
class ImageUrl(TypedDict):
    """OpenAI-compatible inline image URL wrapper."""

    url: str


class ImageContentPart(TypedDict):
    """One image item in a multimodal chat message."""

    type: Literal["image_url"]
    image_url: ImageUrl


ChatContentPart = TextContentPart | ImageContentPart
ChatContent = str | list[ChatContentPart]


class ChatMessage(TypedDict):
    """One text or multimodal OpenAI-compatible chat message."""

    role: str
    content: ChatContent


class ChatProvider(Protocol):
    """Minimal provider boundary used by the chat application."""

    def stream_chat(self, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        """Yield text deltas for one assistant response."""
        ...


class ProviderError(RuntimeError):
    """A provider or protocol failure forwarded to the chat client."""


def _redact_provider_error(response_body: str, provider_api_key: str) -> str:
    """Redact known credential forms before writing an upstream error to logs."""
    redacted = response_body.replace(provider_api_key, "[REDACTED]") if provider_api_key else response_body
    redacted = BEARER_TOKEN_PATTERN.sub(r"\1[REDACTED]", redacted)
    return SECRET_ASSIGNMENT_PATTERN.sub(r"\1[REDACTED]", redacted)


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
                    error_id = str(uuid4())
                    response_body = response.text.strip()
                    if response_body:
                        logger.error(
                            "AI provider HTTP error error_id=%s status=%s response_body=%s",
                            error_id,
                            response.status_code,
                            _redact_provider_error(response_body, self._settings.provider_api_key),
                        )
                    else:
                        logger.error(
                            "AI provider HTTP error error_id=%s status=%s empty_response_body=true",
                            error_id,
                            response.status_code,
                        )
                    raise ProviderError(f"The AI provider returned HTTP {response.status_code}. Error ID: {error_id}.")

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

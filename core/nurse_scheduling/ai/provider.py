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
from dataclasses import dataclass
from typing import Any, Literal, Protocol, TypedDict
from uuid import uuid4

import httpx
from typing_extensions import Required

from .config import AiSettings

logger = logging.getLogger("nurse_scheduling.ai.provider")
BEARER_TOKEN_PATTERN = re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9._~+/=-]+")
SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)(\b(?:api[_-]?key|access[_-]?token|authorization|secret)\b\s*[\"']?\s*[:=]\s*[\"']?)"
    r"([^\"'\s,;<}]+)"
)
MAX_TOOL_CALLS_PER_RESPONSE = 8
MAX_TOOL_ARGUMENT_CHARS = 20_000


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


class ChatMessage(TypedDict, total=False):
    """One OpenAI-compatible chat message, optionally carrying tool traffic."""

    role: Required[str]
    content: ChatContent | None
    tool_calls: list[dict[str, Any]]
    tool_call_id: str


@dataclass(frozen=True)
class ToolCall:
    """One complete tool call reconstructed from the response stream."""

    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class TextDelta:
    """One streamed fragment of assistant text."""

    text: str


@dataclass(frozen=True)
class ToolCallRequest:
    """The tool calls an assistant turn ended with."""

    calls: tuple[ToolCall, ...]


ChatStreamEvent = TextDelta | ToolCallRequest


class ChatProvider(Protocol):
    """Minimal provider boundary used by the chat application."""

    def stream_chat(self, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        """Yield text deltas for one assistant response."""
        ...


class ToolCapableChatProvider(ChatProvider, Protocol):
    """Provider boundary used by the tool loop."""

    def stream_events(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[dict[str, Any]] | None = None,
    ) -> AsyncIterator[ChatStreamEvent]:
        """Yield text deltas and any tool calls for one assistant response."""
        ...


def assistant_tool_call_message(calls: Sequence[ToolCall]) -> ChatMessage:
    """Record the assistant turn that requested tools, as the protocol requires."""
    return ChatMessage(
        role="assistant",
        content=None,
        tool_calls=[
            {"id": call.id, "type": "function", "function": {"name": call.name, "arguments": call.arguments}}
            for call in calls
        ],
    )


def tool_result_message(call_id: str, result: str) -> ChatMessage:
    """Return one tool result for the assistant turn that requested it."""
    return ChatMessage(role="tool", tool_call_id=call_id, content=result)


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
        async for event in self.stream_events(messages):
            if isinstance(event, TextDelta):
                yield event.text

    async def stream_events(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[dict[str, Any]] | None = None,
    ) -> AsyncIterator[ChatStreamEvent]:
        """Translate provider SSE chunks into text deltas and reconstructed tool calls."""
        timeout = httpx.Timeout(self._settings.provider_timeout_seconds, connect=10.0)
        headers = {"Authorization": f"Bearer {self._settings.provider_api_key}"}
        payload: dict[str, Any] = {
            "model": self._settings.provider_model,
            "messages": list(messages),
            "stream": True,
        }
        if tools:
            payload["tools"] = list(tools)
            payload["tool_choice"] = "auto"

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

                partial_calls: dict[int, _PartialToolCall] = {}
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw_data = line.removeprefix("data:").strip()
                    if raw_data == "[DONE]":
                        break
                    if not raw_data:
                        continue
                    try:
                        event = json.loads(raw_data)
                        delta = event["choices"][0]["delta"]
                        content = delta.get("content")
                    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
                        raise ProviderError("The AI provider returned an invalid stream.") from exc
                    if isinstance(content, str) and content:
                        yield TextDelta(content)
                    _merge_tool_call_fragments(partial_calls, delta.get("tool_calls"))
                if partial_calls:
                    yield ToolCallRequest(tuple(partial.complete() for _, partial in sorted(partial_calls.items())))
        except ProviderError:
            raise
        except httpx.TimeoutException as exc:
            raise ProviderError("The AI provider timed out.") from exc
        except httpx.HTTPError as exc:
            raise ProviderError("The AI provider is unavailable.") from exc


@dataclass
class _PartialToolCall:
    """One tool call being reassembled from streamed fragments."""

    id: str = ""
    name: str = ""
    arguments: str = ""

    def complete(self) -> ToolCall:
        if not self.name:
            raise ProviderError("The AI provider requested a tool without a name.")
        return ToolCall(id=self.id or str(uuid4()), name=self.name, arguments=self.arguments)


def _merge_tool_call_fragments(partial_calls: dict[int, _PartialToolCall], fragments: object) -> None:
    """Accumulate streamed tool call fragments keyed by their position."""
    if not isinstance(fragments, list):
        return
    for fragment in fragments:
        if not isinstance(fragment, dict):
            raise ProviderError("The AI provider returned an invalid stream.")
        index = _fragment_index(partial_calls, fragment)
        partial = partial_calls.setdefault(index, _PartialToolCall())
        if len(partial_calls) > MAX_TOOL_CALLS_PER_RESPONSE:
            raise ProviderError(f"The AI provider requested more than {MAX_TOOL_CALLS_PER_RESPONSE} tools at once.")
        if isinstance(fragment.get("id"), str):
            partial.id = fragment["id"]
        function = fragment.get("function")
        if not isinstance(function, dict):
            continue
        if isinstance(function.get("name"), str):
            partial.name += function["name"]
        arguments = function.get("arguments")
        if isinstance(arguments, str):
            partial.arguments += arguments
            if len(partial.arguments) > MAX_TOOL_ARGUMENT_CHARS:
                raise ProviderError("The AI provider sent tool arguments that are too large.")


def _fragment_index(partial_calls: dict[int, _PartialToolCall], fragment: dict[str, Any]) -> int:
    """Resolve the slot a fragment belongs to, tolerating providers that omit `index`."""
    index = fragment.get("index")
    if isinstance(index, int) and not isinstance(index, bool):
        return index
    if not partial_calls:
        return 0
    last_index = max(partial_calls)
    fragment_id = fragment.get("id")
    # Without an index, a new id starts the next call and anything else continues
    # the current one.
    if isinstance(fragment_id, str) and fragment_id and fragment_id != partial_calls[last_index].id:
        return last_index + 1
    return last_index

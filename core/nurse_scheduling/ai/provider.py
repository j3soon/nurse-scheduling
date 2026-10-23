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

# This code is mostly AI generated.

import asyncio
import base64
import json
import logging
import re
from collections.abc import AsyncIterator, Sequence
from contextlib import aclosing
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, Protocol, TypedDict
from uuid import uuid4

import httpx
from typing_extensions import Required

from .config import AiSettings
from .transcript import ProviderIdentity, ToolCall, ToolResultImage

logger = logging.getLogger("nurse_scheduling.ai.provider")
BEARER_TOKEN_PATTERN = re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9._~+/=-]+")
SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)(\b(?:api[_-]?key|access[_-]?token|authorization|secret)\b\s*[\"']?\s*[:=]\s*[\"']?)"
    r"([^\"'\s,;<}]+)"
)
MAX_TOOL_CALLS_PER_RESPONSE = 32
MAX_TOOL_ARGUMENT_CHARS = 20_000
MAX_RESPONSE_TEXT_CHARS = 200_000
MAX_RESPONSE_REASONING_CHARS = 400_000
MAX_PROVIDER_ERROR_EXCERPT_CHARS = 1_000
MAX_PROVIDER_CONTENT_TYPE_CHARS = 100
PROVIDER_ERROR_TRUNCATION_MARKER = "...[truncated]"
SUPPORTED_FINISH_REASONS = frozenset({"stop", "end", "length", "tool_calls", "function_call"})


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
    reasoning_content: str
    reasoning: str
    reasoning_text: str
    reasoning_details: list[dict[str, Any]]
    thinking_blocks: list[dict[str, Any]]
    provider_specific_fields: dict[str, Any]


@dataclass(frozen=True)
class TextDelta:
    """One streamed fragment of assistant text."""

    text: str


@dataclass(frozen=True)
class ReasoningDelta:
    """One streamed fragment of the model's reasoning.

    Reasoning arrives in its own field, so it is never mixed into the answer and
    cannot leak into the assistant message. It is shown to the user on request
    separately from native metadata used for provider replay.
    """

    text: str


@dataclass(frozen=True)
class ReasoningReplay:
    """Native reasoning from one successfully completed HTTP attempt."""

    native: dict[str, Any]
    provider: ProviderIdentity


@dataclass(frozen=True)
class ToolCallRequest:
    """The tool calls an assistant turn ended with."""

    calls: tuple[ToolCall, ...]


@dataclass(frozen=True)
class ResponseEnd:
    """The confirmed end of a response, with its reason when the provider reported one.

    `length` means the output token limit cut the response off, so its text and
    any tool call arguments may be incomplete. `None` means the endpoint sent
    `[DONE]` without a finish reason.
    """

    finish_reason: str | None


@dataclass(frozen=True)
class TokenUsage:
    """Provider-reported token usage for one streamed completion."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cached_prompt_tokens: int | None = None
    reasoning_tokens: int = 0

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        """Add usage from consecutive provider turns."""
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            cached_prompt_tokens=(
                self.cached_prompt_tokens + other.cached_prompt_tokens
                if self.cached_prompt_tokens is not None and other.cached_prompt_tokens is not None
                else None
            ),
            reasoning_tokens=self.reasoning_tokens + other.reasoning_tokens,
        )


@dataclass(frozen=True)
class ProviderAttempt:
    """One underlying HTTP attempt for a logical provider turn."""

    number: int


@dataclass(frozen=True)
class ProviderCall:
    """One billable HTTP attempt, including attempts interrupted before usage arrives."""

    id: str
    model: str
    status: Literal["pending", "reported", "unavailable"] = "pending"
    cost_usd: str | None = None
    usage: TokenUsage | None = None
    provider_call_id: str | None = None
    response_model: str | None = None


@dataclass(frozen=True)
class ProviderResponseMetadata:
    provider_call_id: str | None = None
    response_model: str | None = None
    cost_usd: str | None = None


ChatStreamEvent = (
    TextDelta
    | ReasoningDelta
    | ReasoningReplay
    | ToolCallRequest
    | ResponseEnd
    | TokenUsage
    | ProviderAttempt
    | ProviderCall
    | ProviderResponseMetadata
)


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


def assistant_tool_call_message(calls: Sequence[ToolCall], content: str | None = None) -> ChatMessage:
    """Record the assistant turn that requested tools, as the protocol requires."""
    return ChatMessage(
        role="assistant",
        content=content or None,
        tool_calls=[
            {
                **call.native,
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments},
            }
            for call in calls
        ],
    )


def tool_result_message(call_id: str, result: str) -> ChatMessage:
    """Return one tool result for the assistant turn that requested it."""
    return ChatMessage(role="tool", tool_call_id=call_id, content=result)


def tool_result_image_message(call_id: str, image: ToolResultImage) -> ChatMessage:
    """Pass a tool image through a user message after all tool replies."""
    return ChatMessage(
        role="user",
        content=[
            {"type": "text", "text": f"Image returned by tool call {call_id}."},
            {
                "type": "image_url",
                "image_url": {"url": f"data:{image.media_type};base64,{base64.b64encode(image.data).decode('ascii')}"},
            },
        ],
    )


class ProviderError(RuntimeError):
    """A provider or protocol failure reported to the AI service."""

    def __init__(self, message: str, *, user_message: str | None = None) -> None:
        super().__init__(message)
        self.user_message = user_message

    @classmethod
    def for_user(cls, message: str) -> "ProviderError":
        """Mark a known explanation safe for the chat, without exposing SDK errors."""
        return cls(message, user_message=message)


class ProviderResponseLimitError(ProviderError):
    """The model response exceeded an application limit."""


def _redact_provider_error(response_body: str, provider_api_key: str) -> str:
    """Redact known credential forms before writing an upstream error to logs."""
    redacted = response_body.replace(provider_api_key, "[REDACTED]") if provider_api_key else response_body
    redacted = BEARER_TOKEN_PATTERN.sub(r"\1[REDACTED]", redacted)
    return SECRET_ASSIGNMENT_PATTERN.sub(r"\1[REDACTED]", redacted)


def _provider_error_excerpt(response_body: str, provider_api_key: str) -> str:
    """Return one bounded log line from an untrusted provider response."""
    excerpt = " ".join(_redact_provider_error(response_body, provider_api_key).split())
    if len(excerpt) <= MAX_PROVIDER_ERROR_EXCERPT_CHARS:
        return excerpt
    content_chars = MAX_PROVIDER_ERROR_EXCERPT_CHARS - len(PROVIDER_ERROR_TRUNCATION_MARKER)
    return excerpt[:content_chars] + PROVIDER_ERROR_TRUNCATION_MARKER


class OpenAiCompatibleProvider:
    """Stream chat completions from an OpenAI-compatible HTTP endpoint."""

    def __init__(
        self,
        settings: AiSettings,
        *,
        include_usage: bool = False,
        include_attempts: bool = False,
        parameters: dict[str, Any] | None = None,
        include_costs: bool = False,
    ) -> None:
        self._settings = settings
        self._include_usage = include_usage
        self._include_attempts = include_attempts
        self._parameters = parameters or {}
        self._include_costs = include_costs
        self.identity = ProviderIdentity(settings.provider_base_url.rstrip("/"), settings.provider_model)
        self.context_tokens: int | None = None
        self._context_tokens_loaded = False
        self._context_tokens_lock = asyncio.Lock()

    async def _load_context_tokens(self) -> None:
        """Read and cache the configured model's context limit when metadata is available."""
        async with self._context_tokens_lock:
            if self._context_tokens_loaded:
                return
            self._context_tokens_loaded = True
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(
                        f"{self._settings.provider_base_url}/models",
                        headers={"Authorization": f"Bearer {self._settings.provider_api_key}"},
                    )
                    response.raise_for_status()
                    metadata = response.json()
            except (httpx.HTTPError, ValueError):
                return
            models = metadata.get("data") if isinstance(metadata, dict) else None
            if not isinstance(models, list):
                return
            for model in models:
                if not isinstance(model, dict) or model.get("id") != self._settings.provider_model:
                    continue
                for field in ("max_model_len", "context_length"):
                    limit = model.get(field)
                    if type(limit) is int and limit > 0:
                        self.context_tokens = limit
                        return

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
        """Translate SSE chunks and continue interrupted responses after timeouts."""
        if self._include_usage:
            await self._load_context_tokens()
        timeout = httpx.Timeout(self._settings.provider_timeout_seconds, connect=10.0)
        headers = {"Authorization": f"Bearer {self._settings.provider_api_key}"}
        payload: dict[str, Any] = {
            **self._parameters,
            "model": self._settings.provider_model,
            "messages": list(messages),
            "stream": True,
        }
        if self._include_usage:
            payload["stream_options"] = {"include_usage": True}
        if tools:
            payload["tools"] = list(tools)
            payload["tool_choice"] = "auto"

        stream_started = False
        answer: list[str] = []
        text_chars = 0
        reasoning_chars = 0
        for attempt in range(1, self._settings.provider_max_attempts + 1):
            call = ProviderCall(str(uuid4()), self._settings.provider_model)
            if self._include_costs:
                yield call
            if self._include_attempts:
                yield ProviderAttempt(attempt)
            try:
                # Keep tool calls private until the HTTP attempt also closes cleanly.
                completed: list[ToolCallRequest | ResponseEnd | ReasoningReplay] = []
                async with aclosing(self._stream_attempt(timeout, headers, payload)) as events:
                    async for event in events:
                        if isinstance(event, ProviderResponseMetadata):
                            updated = replace(
                                call,
                                provider_call_id=event.provider_call_id or call.provider_call_id,
                                response_model=event.response_model or call.response_model,
                                cost_usd=event.cost_usd if event.cost_usd is not None else call.cost_usd,
                            )
                            if updated != call:
                                call = updated
                                yield call
                            continue
                        if isinstance(event, TokenUsage):
                            call = replace(call, usage=event)
                        if isinstance(event, (ToolCallRequest, ResponseEnd, ReasoningReplay)):
                            completed.append(event)
                            continue
                        stream_started = True
                        if isinstance(event, TextDelta):
                            text_chars += len(event.text)
                            if text_chars > MAX_RESPONSE_TEXT_CHARS:
                                raise ProviderResponseLimitError.for_user(
                                    "The AI provider returned more text than one answer may contain."
                                )
                            answer.append(event.text)
                        elif isinstance(event, ReasoningDelta):
                            reasoning_chars += len(event.text)
                            if reasoning_chars > MAX_RESPONSE_REASONING_CHARS:
                                raise ProviderResponseLimitError.for_user(
                                    "The AI provider returned more reasoning than one answer may contain."
                                )
                        yield event
                for event in completed:
                    yield event
                if self._include_costs:
                    yield replace(call, status="reported" if call.cost_usd is not None else "unavailable")
                return
            except ProviderError:
                if self._include_costs:
                    yield replace(call, status="reported" if call.cost_usd is not None else "unavailable")
                raise
            except httpx.TimeoutException as exc:
                if self._include_costs:
                    yield replace(call, status="reported" if call.cost_usd is not None else "unavailable")
                if attempt == self._settings.provider_max_attempts:
                    message = (
                        "The AI provider timed out while streaming the response."
                        if stream_started
                        else "The AI provider timed out before starting the response."
                    )
                    raise ProviderError.for_user(message) from exc
                if answer:
                    # A fresh completion cannot resume transport state. Keep visible
                    # text as context, but never replay reasoning or partial tool JSON.
                    payload["messages"] = [
                        *messages,
                        ChatMessage(role="assistant", content="".join(answer)),
                        ChatMessage(
                            role="user",
                            content=f"[App event] The response was interrupted after {text_chars} text characters.",
                        ),
                    ]
                delay = self._settings.provider_retry_backoff_seconds * (2 ** (attempt - 1))
                logger.warning(
                    "AI provider timed out stream_started=%s attempt=%s max_attempts=%s retry_in_seconds=%.3f",
                    stream_started,
                    attempt,
                    self._settings.provider_max_attempts,
                    delay,
                    exc_info=True,
                )
                if delay > 0:
                    await asyncio.sleep(delay)
            except httpx.HTTPError as exc:
                if self._include_costs:
                    yield replace(call, status="reported" if call.cost_usd is not None else "unavailable")
                raise ProviderError.for_user("The AI provider is unavailable.") from exc

    async def _stream_attempt(
        self,
        timeout: httpx.Timeout,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> AsyncIterator[ChatStreamEvent]:
        """Run one HTTP stream attempt without replay policy."""
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
                content_type = " ".join(response.headers.get("content-type", "unknown").split())[
                    :MAX_PROVIDER_CONTENT_TYPE_CHARS
                ]
                if response_body:
                    logger.error(
                        "AI provider HTTP error error_id=%s status=%s content_type=%s response_excerpt=%s",
                        error_id,
                        response.status_code,
                        content_type,
                        _provider_error_excerpt(response_body, self._settings.provider_api_key),
                    )
                else:
                    logger.error(
                        "AI provider HTTP error error_id=%s status=%s content_type=%s empty_response_body=true",
                        error_id,
                        response.status_code,
                        content_type,
                    )
                raise ProviderError.for_user(
                    f"The AI provider returned HTTP {response.status_code}. Error ID: {error_id}."
                )

            partial_calls: dict[int, _PartialToolCall] = {}
            native_reasoning: dict[str, Any] = {}
            native_chars = 0
            if self._include_costs:
                yield ProviderResponseMetadata(provider_call_id=response.headers.get("x-litellm-call-id"))
            finish_reason: str | None = None
            done_received = False
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                raw_data = line.removeprefix("data:").strip()
                if raw_data == "[DONE]":
                    done_received = True
                    break
                if not raw_data:
                    continue
                try:
                    event = json.loads(raw_data)
                    if not isinstance(event, dict):
                        raise TypeError
                    choices = event["choices"]
                    if not isinstance(choices, list):
                        raise TypeError
                    usage = event.get("usage")
                    if self._include_costs:
                        yield ProviderResponseMetadata(
                            response_model=event.get("model") if isinstance(event.get("model"), str) else None,
                            cost_usd=_parse_cost(usage.get("cost")) if isinstance(usage, dict) else None,
                        )
                    if usage is not None:
                        yield _parse_token_usage(usage)
                    # A usage-only or filter-only chunk carries no choice, and some
                    # providers omit usage from it.
                    if not choices:
                        continue
                    choice = choices[0]
                    if not isinstance(choice, dict):
                        raise TypeError
                    delta = choice["delta"]
                    if not isinstance(delta, dict):
                        raise TypeError
                    content = delta.get("content")
                    reported_reason = choice.get("finish_reason")
                    if finish_reason is not None:
                        if reported_reason is not None and reported_reason != finish_reason:
                            raise ProviderError.for_user("The AI provider returned conflicting finish reasons.")
                        if any(
                            delta.get(field)
                            for field in (
                                "content",
                                "reasoning_content",
                                "reasoning",
                                "reasoning_text",
                                "reasoning_details",
                                "thinking_blocks",
                                "provider_specific_fields",
                                "tool_calls",
                            )
                        ):
                            raise ProviderError.for_user("The AI provider returned output after completion.")
                    if isinstance(reported_reason, str):
                        finish_reason = reported_reason
                except (json.JSONDecodeError, KeyError, TypeError) as exc:
                    raise ProviderError.for_user("The AI provider returned an invalid stream.") from exc
                if isinstance(content, str) and content:
                    yield TextDelta(content)
                # Providers name this field either way, and llama.cpp uses the first.
                reasoning = delta.get("reasoning_content") or delta.get("reasoning") or delta.get("reasoning_text")
                if isinstance(reasoning, str) and reasoning:
                    yield ReasoningDelta(reasoning)
                native_chars += _merge_reasoning(native_reasoning, delta)
                if native_chars > MAX_RESPONSE_REASONING_CHARS:
                    raise ProviderResponseLimitError.for_user(
                        "The AI provider returned more reasoning metadata than one answer may contain."
                    )
                _merge_tool_call_fragments(partial_calls, delta.get("tool_calls"))
            # Pi checks completion before releasing tools. Accept [DONE] for endpoints
            # that omit finish_reason, but never infer completion from HTTP EOF alone.
            if finish_reason is None and not done_received:
                raise ProviderError.for_user("The AI provider stream ended before completion.")
            if finish_reason is not None and finish_reason not in SUPPORTED_FINISH_REASONS:
                raise ProviderError.for_user(
                    f"The AI provider returned an unsuccessful finish reason: {finish_reason}."
                )
            if native_reasoning:
                yield ReasoningReplay(native_reasoning, self.identity)
            if partial_calls:
                yield ToolCallRequest(tuple(partial.complete() for _, partial in sorted(partial_calls.items())))
            yield ResponseEnd(finish_reason)


def _merge_reasoning(target: dict[str, Any], delta: dict[str, Any]) -> int:
    """Collect native fields without deriving replay data from displayed text."""
    fields = ("reasoning_content", "reasoning", "reasoning_text", "reasoning_details", "thinking_blocks")
    size = 0
    for key in (*fields, "provider_specific_fields"):
        value = delta.get(key)
        if value is None:
            continue
        if key == "provider_specific_fields":
            if not isinstance(value, dict):
                raise ProviderError.for_user("The AI provider returned invalid reasoning metadata.")
            # Preserve the gateway wrapper, but only its documented reasoning fields.
            nested = {name: value[name] for name in fields if name in value}
            size += _merge_reasoning(target.setdefault(key, {}), nested)
            continue
        size += len(value) if isinstance(value, str) else len(json.dumps(value, ensure_ascii=False))
        if key in fields[:3]:
            if not isinstance(value, str):
                raise ProviderError.for_user("The AI provider returned invalid reasoning metadata.")
            target[key] = target.get(key, "") + value
            continue
        if not isinstance(value, list) or any(not isinstance(block, dict) for block in value):
            raise ProviderError.for_user("The AI provider returned invalid reasoning metadata.")
        blocks = target.setdefault(key, [])
        for block in value:
            last = blocks[-1] if blocks else None
            kind = block.get("type")
            field = {"reasoning.text": "text", "reasoning.summary": "summary", "thinking": "thinking"}.get(kind)
            same = (
                last is not None
                and last.get("type") == kind
                and all(
                    last.get(name) == block.get(name) or name not in last or name not in block
                    for name in ("id", "index")
                )
            )
            if field and same:
                for name, part in block.items():
                    if name == field or (key == "thinking_blocks" and name == "signature"):
                        if not isinstance(part, str):
                            raise ProviderError.for_user("The AI provider returned invalid reasoning metadata.")
                        last[name] = last.get(name, "") + part
                    elif name not in last or not last[name]:
                        last[name] = part
            else:
                blocks.append(dict(block))
    return size


def _parse_token_usage(raw_usage: object) -> TokenUsage:
    """Parse the standard Chat Completions usage object from its final chunk."""
    if not isinstance(raw_usage, dict):
        raise ProviderError.for_user("The AI provider returned invalid token usage.")
    prompt_details = raw_usage.get("prompt_tokens_details") or {}
    completion_details = raw_usage.get("completion_tokens_details") or {}
    if not isinstance(prompt_details, dict) or not isinstance(completion_details, dict):
        raise ProviderError.for_user("The AI provider returned invalid token usage.")
    return TokenUsage(
        prompt_tokens=_usage_integer(raw_usage, "prompt_tokens"),
        completion_tokens=_usage_integer(raw_usage, "completion_tokens"),
        total_tokens=_usage_integer(raw_usage, "total_tokens"),
        cached_prompt_tokens=(
            _usage_integer(prompt_details, "cached_tokens") if prompt_details.get("cached_tokens") is not None else None
        ),
        reasoning_tokens=_usage_integer(completion_details, "reasoning_tokens", default=0),
    )


def _usage_integer(values: dict[str, Any], key: str, *, default: int | None = None) -> int:
    """Read one non-negative integer from a provider usage object."""
    value = values.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProviderError.for_user("The AI provider returned invalid token usage.")
    return value


@dataclass
class _PartialToolCall:
    """One tool call being reassembled from streamed fragments."""

    id: str = ""
    name: str = ""
    arguments: str = ""
    native: dict[str, Any] | None = None

    def complete(self) -> ToolCall:
        if not self.name:
            raise ProviderError.for_user("The AI provider requested a tool without a name.")
        return ToolCall(id=self.id or str(uuid4()), name=self.name, arguments=self.arguments, native=self.native or {})


def _merge_tool_call_fragments(partial_calls: dict[int, _PartialToolCall], fragments: object) -> None:
    """Accumulate streamed tool call fragments keyed by their position."""
    if not isinstance(fragments, list):
        return
    for fragment in fragments:
        if not isinstance(fragment, dict):
            raise ProviderError.for_user("The AI provider returned an invalid stream.")
        index = _fragment_index(partial_calls, fragment)
        partial = partial_calls.setdefault(index, _PartialToolCall())
        if len(partial_calls) > MAX_TOOL_CALLS_PER_RESPONSE:
            raise ProviderResponseLimitError.for_user(
                f"The AI provider requested more than {MAX_TOOL_CALLS_PER_RESPONSE} tools at once."
            )
        if isinstance(fragment.get("id"), str):
            partial.id = fragment["id"]
        for key in ("extra_content", "provider_specific_fields"):
            if isinstance(fragment.get(key), dict):
                partial.native = {**(partial.native or {}), key: fragment[key]}
                if len(json.dumps(partial.native)) > MAX_RESPONSE_REASONING_CHARS:
                    raise ProviderResponseLimitError.for_user("The AI provider returned too much tool metadata.")
        function = fragment.get("function")
        if not isinstance(function, dict):
            continue
        if isinstance(function.get("name"), str):
            partial.name += function["name"]
        arguments = function.get("arguments")
        if isinstance(arguments, str):
            partial.arguments += arguments
            if len(partial.arguments) > MAX_TOOL_ARGUMENT_CHARS:
                raise ProviderResponseLimitError.for_user("The AI provider sent tool arguments that are too large.")


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


def _parse_cost(value: object) -> str | None:
    """Normalize LiteLLM's final usage cost. Missing or invalid pricing is unknown."""
    if not isinstance(value, str | int | float) or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        return None
    if not amount.is_finite() or amount < 0 or amount > Decimal("1e12"):
        return None
    if amount == 0:
        return "0"
    # Accept the full float range used by gateway JSON, while bounding decimal output.
    return str(amount) if amount >= Decimal("5e-324") else None

"""Automatic context summaries with recent tool exchanges retained."""

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

# This file is mostly AI generated.

import json
import logging
import math
from collections.abc import AsyncIterator, Sequence
from contextlib import aclosing
from pathlib import Path
from typing import Any

from .agent_types import AgentCompaction
from .context import apply_compaction, history_chars
from .provider import (
    ChatMessage,
    ProviderCall,
    ProviderError,
    ResponseEnd,
    TextDelta,
    ToolCallRequest,
    ToolCapableChatProvider,
)
from .system_prompt import load_system_prompt_entries, load_system_prompt_sections
from .transcript import CompactionEntry

logger = logging.getLogger("nurse_scheduling.ai.compaction")
COMPACTION_MANIFEST = Path(__file__).with_name("prompts") / "compaction.json"


def estimate_tokens(message: dict[str, Any]) -> int:
    """Use Pi's characters/4 fallback, with a fixed allowance for tool images."""
    content = message.get("content")
    if isinstance(content, list):
        chars = sum(len(part.get("text", "")) if part.get("type") == "text" else 4800 for part in content)
    else:
        chars = len(content or "")
    chars += len(json.dumps(message.get("tool_calls", []), ensure_ascii=False))
    # Count opaque state conservatively when provider usage is unavailable.
    chars += sum(
        len(json.dumps(message[key], ensure_ascii=False))
        for key in (
            "reasoning_content",
            "reasoning",
            "reasoning_text",
            "reasoning_details",
            "thinking_blocks",
            "provider_specific_fields",
        )
        if key in message
    )
    return math.ceil(chars / 4) + 4


def estimate_context_tokens(messages: Sequence[ChatMessage], tools: Sequence[dict], identity=None) -> int:
    """Prefer the latest same-model usage plus estimates for messages after it."""
    estimate = sum(estimate_tokens(message) for message in messages) + math.ceil(len(json.dumps(tools)) / 4)
    trailing = 0
    for message in reversed(messages):
        usage = message.get("_usage")
        source = message.get("_provider")
        if usage and source == identity and usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0) > 0:
            return max(estimate, usage["prompt_tokens"] + usage["completion_tokens"] + trailing)
        # A summary invalidates usage from the history it replaced.
        if str(message.get("content", "")).startswith("[Conversation summary]\n"):
            break
        trailing += estimate_tokens(message)
    return estimate


def _conversation(messages: Sequence[ChatMessage]) -> list[ChatMessage]:
    return [message for message in messages if message["role"] != "system" and not message.get("_current_status")]


def _serialize(messages: Sequence[ChatMessage]) -> str:
    """Summarize conversation data, tool arguments, results, and file paths."""
    parts = []
    for message in messages:
        content = message.get("content")
        if isinstance(content, list):
            content = "\n".join(part.get("text", "[image]") for part in content)
        content = content or ""
        if message["role"] == "tool" and len(content) > 2000:
            content = content[:2000] + "\n[Tool result truncated for summary]"
        parts.append(f"[{message['role']}]: {content}")
        for call in message.get("tool_calls", []):
            function = call["function"]
            parts.append(f"[tool call {call['id']}]: {function['name']} {function['arguments']}")
    return "\n\n".join(parts)


def _cut_point(messages: list[ChatMessage], keep_tokens: int) -> int:
    """Keep recent exchanges without starting at a result or its supplemental image."""
    accumulated = 0
    cut = len(messages)
    for index in range(len(messages) - 1, -1, -1):
        accumulated += estimate_tokens(messages[index])
        valid = messages[index]["role"] != "tool" and not messages[index].get("_tool_image")
        if accumulated >= keep_tokens and cut < len(messages):
            break
        if valid:
            cut = index
            if accumulated >= keep_tokens:
                break
    return cut


class ContextCompactor:
    """Prepare summaries without changing context until every summary call succeeds."""

    def __init__(self, provider: ToolCapableChatProvider, *, history_limit: int = 200_000, message_limit: int = 1000):
        self.provider = provider
        self.history_limit = history_limit
        self.message_limit = message_limit
        self.failed = False

    async def prepare(self) -> None:
        prepare = getattr(self.provider, "prepare_context", None)
        if prepare is not None:
            await prepare()

    @property
    def window(self) -> int | None:
        value = getattr(self.provider, "context_tokens", None)
        return value if type(value) is int and value > 0 else None

    def tokens(self, messages, tools) -> int:
        from dataclasses import asdict

        identity = getattr(self.provider, "identity", None)
        return estimate_context_tokens(messages, tools, asdict(identity) if identity else None)

    def needed(self, messages, tools) -> bool:
        if self.window is None or self.failed:
            return False
        body = _conversation(messages)
        reserve = min(16384, self.window // 4)
        return (
            self.tokens(messages, tools) > self.window - reserve
            or history_chars(body) > self.history_limit * 0.8
            or len(body) > max(2, self.message_limit * 0.8)
        )

    async def compact(
        self, messages: Sequence[ChatMessage], tools: Sequence[dict], *, force: bool = False
    ) -> AsyncIterator[ProviderCall | AgentCompaction]:
        if not force and not self.needed(messages, tools):
            return
        body = _conversation(messages)
        if len(body) < 2:
            return
        window = self.window or 32768
        reserve = min(16384, window // 4)
        recent_tokens = min(
            20000,
            window // 3,
            max(1, self.history_limit // 12),
            max(1, sum(estimate_tokens(message) for message in body) // 2),
        )
        cut = _cut_point(body, recent_tokens)
        if cut < 1:
            cut = len(body)
        # If a single recent tool batch fills the window, summarize that batch too.
        candidate_keep = sum(not message.get("_tool_image", False) for message in body[cut:])
        candidate = apply_compaction(messages, CompactionEntry("", candidate_keep, 0))
        if sum(estimate_tokens(message) for message in candidate) > window - reserve:
            cut = len(body)
        older, recent = body[:cut], body[cut:]
        keep = sum(not message.get("_tool_image", False) for message in recent)
        prompt = "\n\n".join(load_system_prompt_sections(load_system_prompt_entries(COMPACTION_MANIFEST)))
        max_summary_chars = min(16000, max(256, reserve * 2), max(256, self.history_limit // 4))
        input_chars = (window - reserve) * 4 - len(prompt) - max_summary_chars - 512
        if input_chars < 256:
            return
        serialized = _serialize(older)
        summary = ""
        try:
            # Incremental summaries also handle a very large tool result or a provider
            # overflow. Each request stays below the discovered input budget.
            for offset in range(0, len(serialized), input_chars):
                chunk = serialized[offset : offset + input_chars]
                text, finish, ended, text_chars = [], None, False, 0
                request = [
                    ChatMessage(role="system", content=prompt),
                    ChatMessage(
                        role="user",
                        content=(
                            f"Summary character limit: {max_summary_chars}.\n"
                            f"<previous-summary>\n{summary}\n</previous-summary>\n"
                            f"<conversation>\n{chunk}\n</conversation>"
                        ),
                    ),
                ]
                events = self.provider.stream_events(request, [])
                async with aclosing(events):
                    async for event in events:
                        if isinstance(event, ProviderCall):
                            yield event
                        elif isinstance(event, TextDelta):
                            text.append(event.text)
                            text_chars += len(event.text)
                            if text_chars > max_summary_chars:
                                raise ProviderError("Compaction summary exceeded its size limit")
                        elif isinstance(event, ToolCallRequest) and event.calls:
                            raise ProviderError("Compaction requested a tool")
                        elif isinstance(event, ResponseEnd):
                            finish = event.finish_reason
                            ended = True
                summary = "".join(text).strip()
                if not summary or not ended or finish == "length":
                    raise ProviderError("Compaction returned an empty or incomplete summary")
            entry = CompactionEntry(summary, keep, self.tokens(messages, tools))
            if history_chars(apply_compaction(messages, entry)) >= history_chars(messages):
                raise ProviderError("Compaction did not reduce context")
        except ProviderError:
            self.failed = True
            logger.warning("AI context compaction failed. Original context retained.", exc_info=True)
            return
        yield AgentCompaction(entry)

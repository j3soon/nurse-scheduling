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

import logging
from collections.abc import AsyncIterator, Sequence
from contextlib import aclosing
from pathlib import Path

from .agent_types import AgentCompaction, AgentCompactionEnd, AgentCompactionStart
from .context import STATUS_PREFIX, SUMMARY_PREFIX, apply_compaction, history_chars
from .context_tokens import context_safety_tokens, estimate_context_tokens, estimate_tokens
from .provider import (
    ChatMessage,
    ProviderCall,
    ProviderError,
    ProviderRetry,
    ResponseEnd,
    TextDelta,
    ToolCallRequest,
    ToolCapableChatProvider,
)
from .system_prompt import load_system_prompt_entries, load_system_prompt_sections
from .transcript import CompactionEntry

logger = logging.getLogger("nurse_scheduling.ai.compaction")
COMPACTION_MANIFEST = Path(__file__).with_name("prompts") / "compaction.json"


def _conversation(messages: Sequence[ChatMessage]) -> list[ChatMessage]:
    return [message for message in messages if message["role"] != "system"]


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


def _is_cut_point(message: ChatMessage) -> bool:
    return (
        message["role"] != "tool"
        and not message.get("_tool_image")
        and not str(message.get("content", "")).startswith(STATUS_PREFIX)
    )


def _cut_point(messages: list[ChatMessage], keep_tokens: int) -> int:
    """Use Pi's backwards token budget and keep tool calls with their results."""
    cut_points = [index for index, message in enumerate(messages) if _is_cut_point(message)]
    if not cut_points:
        return 0
    accumulated = 0
    for index in range(len(messages) - 1, -1, -1):
        accumulated += estimate_tokens(messages[index])
        if accumulated >= keep_tokens:
            return next((cut for cut in cut_points if cut >= index), cut_points[-1])
    return 0


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
        if self.failed:
            return False
        body = _conversation(messages)
        window = self.window
        token_limit_reached = window is not None and self.tokens(messages, tools) > window - min(16384, window // 4)
        return (
            token_limit_reached
            or history_chars(body) > self.history_limit * 0.8
            or len(body) > max(2, self.message_limit * 0.8)
        )

    async def compact(
        self, messages: Sequence[ChatMessage], tools: Sequence[dict], *, force: bool = False, manual: bool = False
    ) -> AsyncIterator[ProviderCall | AgentCompaction | AgentCompactionStart | AgentCompactionEnd]:
        if not force and not self.needed(messages, tools):
            return
        body = _conversation(messages)
        previous_summary = ""
        if body and body[0].get("_compaction_summary"):
            previous_summary = body.pop(0)["content"].removeprefix(SUMMARY_PREFIX + "\n")
        if len(body) < 2:
            if manual:
                yield AgentCompactionEnd("manual", False, self.tokens(messages, tools), skipped=True)
            return
        window = self.window or 32768
        reserve = min(16384, window // 4)
        recent_tokens = min(
            20000,
            window // 3,
            max(1, self.history_limit // 12),
            sum(estimate_tokens(message) for message in body[-max(1, self.message_limit // 3) :]),
        )
        cut = _cut_point(body, recent_tokens)
        if cut == 0:
            if manual:
                yield AgentCompactionEnd("manual", False, self.tokens(messages, tools), skipped=True)
            return
        # Smaller model windows can require a later safe boundary. Summarize the
        # whole tail only when even its final tool batch cannot fit.
        while cut < len(body):
            candidate_keep = sum(not message.get("_tool_image", False) for message in body[cut:])
            candidate = apply_compaction(messages, CompactionEntry("", candidate_keep, 0))
            if sum(estimate_tokens(message) for message in candidate) <= window - reserve:
                break
            cut = next((index for index in range(cut + 1, len(body)) if _is_cut_point(body[index])), len(body))
        older, recent = body[:cut], body[cut:]
        keep = sum(not message.get("_tool_image", False) for message in recent)
        entries = load_system_prompt_entries(COMPACTION_MANIFEST)
        prompts = dict(zip((entry["id"] for entry in entries), load_system_prompt_sections(entries), strict=True))
        instruction_chars = max(len(prompt) for key, prompt in prompts.items() if key != "compaction-system")
        summary_space = (
            (window - max(1, int(0.8 * reserve)) - context_safety_tokens(window)) * 4
            - len(prompts["compaction-system"])
            - instruction_chars
            - 512
        )
        max_summary_chars = min(
            16000, max(256, reserve * 2), max(256, self.history_limit // 4), max(256, summary_space // 2)
        )
        input_chars = summary_space - max_summary_chars
        if input_chars < 256:
            return
        turn_start = None
        if cut < len(body) and body[cut]["role"] == "assistant":
            turn_start = next(
                (
                    index
                    for index in range(cut - 1, -1, -1)
                    if body[index]["role"] == "user"
                    and not body[index].get("_tool_image")
                    and not str(body[index].get("content", "")).startswith(STATUS_PREFIX)
                ),
                None,
            )
        history = older if turn_start is None else body[:turn_start]
        summary = previous_summary
        reason = "manual" if manual else "overflow" if force else "threshold"
        tokens_before = self.tokens(messages, tools)
        yield AgentCompactionStart(reason, tokens_before)
        try:
            if history:
                events = self._summarize(history, prompts, input_chars, max_summary_chars, summary)
                async with aclosing(events):
                    async for event in events:
                        if isinstance(event, ProviderCall):
                            yield event
                        else:
                            summary = event
            if turn_start is not None:
                # Pi summarizes older history and the active turn prefix separately.
                history_text = summary or "No prior history."
                events = self._summarize(
                    body[turn_start:cut],
                    prompts,
                    input_chars,
                    max_summary_chars,
                    initial_prompt="compaction-turn-prefix",
                )
                async with aclosing(events):
                    async for event in events:
                        if isinstance(event, ProviderCall):
                            yield event
                        else:
                            summary = f"{history_text}\n\n---\n\n**Turn Context (split turn):**\n\n{event}"
            entry = CompactionEntry(summary, keep, self.tokens(messages, tools))
            if history_chars(apply_compaction(messages, entry)) >= history_chars(messages):
                self.failed = True
                yield AgentCompactionEnd(reason, False, tokens_before, skipped=True)
                return
        except ProviderError:
            self.failed = True
            logger.warning("AI context compaction failed. Original context retained.", exc_info=True)
            yield AgentCompactionEnd(reason, False, tokens_before)
            return
        yield AgentCompaction(entry)
        after = apply_compaction(messages, entry)
        yield AgentCompactionEnd(
            reason,
            True,
            tokens_before,
            self.tokens(after, tools),
            min(self.history_limit, history_chars(_conversation(after))),
            summary=entry.summary,
            keep_messages=entry.keep_messages,
        )

    async def _summarize(
        self,
        messages: Sequence[ChatMessage],
        prompts: dict[str, str],
        input_chars: int,
        max_summary_chars: int,
        summary: str = "",
        *,
        initial_prompt: str = "context-compaction",
    ) -> AsyncIterator[ProviderCall | str]:
        """Use Pi's initial or update instructions with explicit conversation data."""
        serialized = _serialize(messages)
        # Retain bounded chunking when a history cannot fit in one request.
        offset = 0
        while offset < len(serialized):
            # A split-turn checkpoint can contain both history and turn summaries.
            chunk_chars = input_chars - max(0, len(summary) - max_summary_chars)
            if chunk_chars < 256:
                raise ProviderError("Compaction has no room for the previous summary")
            chunk = serialized[offset : offset + chunk_chars]
            offset += len(chunk)
            instruction = prompts["compaction-update" if summary else initial_prompt]
            content = f"<conversation>\n{chunk}\n</conversation>\n\n"
            if summary:
                content += f"<previous-summary>\n{summary}\n</previous-summary>\n\n"
            content += instruction + f"\n\nSummary character limit: {max_summary_chars}."
            request = [
                ChatMessage(role="system", content=prompts["compaction-system"]),
                ChatMessage(role="user", content=content),
            ]
            text, finish, ended, text_chars = [], None, False, 0
            bind_limit = getattr(self.provider, "with_output_limit", None)
            reserve = min(16384, (self.window or 32768) // 4)
            summary_provider = bind_limit(max(1, int(0.8 * reserve))) if bind_limit is not None else self.provider
            events = summary_provider.stream_events(request, [])
            async with aclosing(events):
                async for event in events:
                    if isinstance(event, ProviderCall):
                        yield event
                    elif isinstance(event, ProviderRetry):
                        # Pi's completeSummarization accepts only the completed attempt.
                        text, finish, ended, text_chars = [], None, False, 0
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
        yield summary

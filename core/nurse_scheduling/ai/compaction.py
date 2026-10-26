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
from collections.abc import AsyncIterator, Sequence
from contextlib import aclosing
from pathlib import Path

from .agent_types import AgentCompaction, AgentCompactionEnd, AgentCompactionStart, AgentGenerationProgress
from .context import STATUS_PREFIX, SUMMARY_PREFIX, apply_compaction, history_chars
from .context_tokens import estimate_context_tokens, estimate_tokens, reasoning_text
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
        if message["role"] == "assistant":
            reasoning = reasoning_text(message)
            if reasoning:
                parts.append(f"[Assistant thinking]: {reasoning}")
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

    def __init__(
        self, provider: ToolCapableChatProvider, *, reserve_tokens: int = 16384, keep_recent_tokens: int = 20000
    ):
        self.provider = provider
        self.reserve_tokens = reserve_tokens
        self.keep_recent_tokens = keep_recent_tokens
        self._summary_step = 0

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
        window = self.window
        return window is not None and self.tokens(messages, tools) > window - self.reserve_tokens

    async def compact(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[dict],
        *,
        force: bool = False,
        manual: bool = False,
        already_compacted: bool = False,
        after_omitted_attempt: bool = False,
    ) -> AsyncIterator[
        ProviderCall | AgentCompaction | AgentCompactionStart | AgentCompactionEnd | AgentGenerationProgress
    ]:
        if not force and not self.needed(messages, tools):
            return
        body = _conversation(messages)
        previous_summary = None
        previous_files = {}
        if body and body[0].get("_compaction_summary"):
            previous_files = body[0].get("_compaction_files", {})
            previous_summary = body.pop(0)["content"].removeprefix(SUMMARY_PREFIX + "\n")
        cut = _cut_point(body, self.keep_recent_tokens)
        if (
            after_omitted_attempt
            and body
            and cut == len(body) - 1
            and _is_cut_point(body[cut])
            and estimate_tokens(body[cut]) >= self.keep_recent_tokens
        ):
            # Pi can keep only the omitted attempt after an oversized final input.
            # Its visible context is empty, so summarize that input too.
            cut = len(body)
        if already_compacted or cut == 0:
            if manual:
                yield AgentCompactionEnd("manual", False, self.tokens(messages, tools), skipped=True)
            return
        if self.window is None:
            raise ProviderError.for_user(
                "The selected model has no valid context window. Configure its model metadata."
            )
        older, recent = body[:cut], body[cut:]
        keep = sum(not message.get("_tool_image", False) for message in recent)
        entries = load_system_prompt_entries(COMPACTION_MANIFEST)
        prompts = dict(zip((entry["id"] for entry in entries), load_system_prompt_sections(entries), strict=True))
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
        self._summary_step = 0
        try:
            if history:
                events = self._summarize(history, prompts, summary)
                async with aclosing(events):
                    async for event in events:
                        if isinstance(event, (ProviderCall, AgentGenerationProgress)):
                            yield event
                        else:
                            summary = event
            if turn_start is not None:
                # Pi summarizes older history and the active turn prefix separately.
                history_text = summary if summary is not None else "No prior history."
                events = self._summarize(
                    body[turn_start:cut],
                    prompts,
                    initial_prompt="compaction-turn-prefix",
                )
                async with aclosing(events):
                    async for event in events:
                        if isinstance(event, (ProviderCall, AgentGenerationProgress)):
                            yield event
                        else:
                            summary = f"{history_text}\n\n---\n\n**Turn Context (split turn):**\n\n{event}"
            read_files = set(previous_files.get("read", ()))
            modified_files = set(previous_files.get("modified", ()))
            for message in older:
                for call in message.get("tool_calls", ()):
                    function = call["function"]
                    try:
                        arguments = json.loads(function["arguments"])
                    except (ValueError, TypeError):
                        continue
                    path = arguments.get("path") if isinstance(arguments, dict) else None
                    if not isinstance(path, str) or not path:
                        continue
                    if function["name"] == "read":
                        read_files.add(path)
                    elif function["name"] in {"write", "edit"}:
                        modified_files.add(path)
            read = tuple(sorted(read_files - modified_files))
            modified = tuple(sorted(modified_files))
            for tag, paths in (("read-files", read), ("modified-files", modified)):
                if paths:
                    summary += f"\n\n<{tag}>\n" + "\n".join(paths) + f"\n</{tag}>"
            entry = CompactionEntry(
                summary, keep, self.tokens(messages, tools), read_files=read, modified_files=modified
            )
        except ProviderError:
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
            history_chars(_conversation(after)),
            summary=entry.summary,
            keep_messages=entry.keep_messages,
        )

    async def _summarize(
        self,
        messages: Sequence[ChatMessage],
        prompts: dict[str, str],
        summary: str | None = None,
        *,
        initial_prompt: str = "context-compaction",
    ) -> AsyncIterator[ProviderCall | AgentGenerationProgress | str]:
        """Use Pi's summary prompts and token budgets without local text ceilings."""
        serialized = _serialize(messages)
        turn_prefix = initial_prompt == "compaction-turn-prefix"
        if turn_prefix:
            content = f"# Conversation\n{serialized}\n\n# Instructions\n{prompts[initial_prompt]}"
        else:
            content = f"<conversation>\n{serialized}\n</conversation>\n\n"
            if summary:
                content += f"<previous-summary>\n{summary}\n</previous-summary>\n\n"
            content += prompts["compaction-update" if summary else initial_prompt]
        request = [
            ChatMessage(role="system", content=prompts["compaction-system"]),
            ChatMessage(role="user", content=content),
        ]
        text, finish, ended, text_chars = [], None, False, 0
        self._summary_step += 1
        yield AgentGenerationProgress("compaction", 0, self._summary_step)
        bind_limit = getattr(self.provider, "with_output_limit", None)
        output_tokens = int((0.5 if turn_prefix else 0.8) * self.reserve_tokens)
        summary_provider = bind_limit(output_tokens) if bind_limit is not None else self.provider
        events = summary_provider.stream_events(request, [])
        async with aclosing(events):
            async for event in events:
                if isinstance(event, ProviderCall):
                    yield event
                elif isinstance(event, ProviderRetry):
                    text, finish, ended, text_chars = [], None, False, 0
                    yield AgentGenerationProgress("compaction", 0, self._summary_step)
                elif isinstance(event, TextDelta):
                    text.append(event.text)
                    text_chars += len(event.text)
                    yield AgentGenerationProgress("compaction", text_chars, self._summary_step)
                elif isinstance(event, ToolCallRequest) and event.calls:
                    raise ProviderError("Compaction requested a tool")
                elif isinstance(event, ResponseEnd):
                    finish = event.finish_reason
                    ended = True
        summary = "".join(text)
        if not ended or finish == "length":
            raise ProviderError("Compaction returned an incomplete summary")
        yield summary

"""The provider and tool loop behind one assistant answer."""

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

import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from .provider import (
    ChatMessage,
    ReasoningDelta,
    TextDelta,
    ToolCallRequest,
    ToolCapableChatProvider,
    assistant_tool_call_message,
    tool_result_message,
)

logger = logging.getLogger("nurse_scheduling.ai.agent")


@dataclass(frozen=True)
class AgentText:
    """One streamed fragment of the answer shown to the user."""

    text: str


@dataclass(frozen=True)
class AgentReasoning:
    """One streamed fragment of the model's reasoning, for the reader only."""

    text: str


@dataclass(frozen=True)
class AgentToolStart:
    """One tool request recorded before execution begins."""

    name: str
    arguments: str


@dataclass(frozen=True)
class AgentToolUse:
    """One tool call the assistant made, with what it sent and received."""

    name: str
    arguments: str
    result: str
    ok: bool


@dataclass(frozen=True)
class AgentProposal:
    """The schedule the run ended with, waiting for the user to approve it."""

    text: str
    diff: str


AgentEvent = AgentText | AgentReasoning | AgentToolStart | AgentToolUse | AgentProposal
ToolExecutor = Callable[[str, str], Awaitable["AgentToolOutcome"]]


@dataclass(frozen=True)
class AgentToolOutcome:
    """One provider-neutral result produced by an agent-facing tool."""

    text: str
    ok: bool


async def run_tool_agent(
    provider: ToolCapableChatProvider,
    messages: Sequence[ChatMessage],
    tools: Sequence[dict[str, Any]],
    execute: ToolExecutor,
) -> AsyncIterator[AgentText | AgentReasoning | AgentToolStart | AgentToolUse]:
    """Run the model/tool loop shared by agent capability layers."""
    conversation = list(messages)
    while True:
        answer, calls = [], ()
        async for event in provider.stream_events(conversation, tools):
            if isinstance(event, TextDelta):
                answer.append(event.text)
                yield AgentText(event.text)
            elif isinstance(event, ReasoningDelta):
                yield AgentReasoning(event.text)
            elif isinstance(event, ToolCallRequest):
                calls = event.calls
        if not calls:
            break

        conversation.append(assistant_tool_call_message(calls, "".join(answer)))
        for call in calls:
            yield AgentToolStart(call.name, call.arguments)
            outcome = await execute(call.name, call.arguments)
            logger.info(
                "agent tool call name=%s ok=%s result_chars=%s",
                call.name,
                outcome.ok,
                len(outcome.text),
            )
            yield AgentToolUse(call.name, call.arguments, outcome.text, outcome.ok)
            conversation.append(tool_result_message(call.id, outcome.text))

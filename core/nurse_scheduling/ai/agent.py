"""The bounded provider and tool loop behind one assistant answer."""

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
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass

from .editor import ScheduleEditor, execute_tool, tool_definitions
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


AgentEvent = AgentText | AgentReasoning | AgentToolUse | AgentProposal


async def run_agent(
    provider: ToolCapableChatProvider,
    editor: ScheduleEditor,
    messages: Sequence[ChatMessage],
    max_turns: int,
) -> AsyncIterator[AgentEvent]:
    """Answer one question, letting the assistant read and edit the schedule.

    The loop ends when the assistant replies without calling a tool, or when the
    turn budget runs out. A run that fails or is abandoned leaves no proposal
    behind, so the user is never offered a schedule from an incomplete answer.
    """
    conversation = list(messages)
    completed = False
    try:
        for turn in range(max_turns):
            # The final turn offers no tools, which forces an answer in text
            # rather than a loop that spends the budget on more tool calls.
            offer_tools = turn < max_turns - 1
            answer, calls = [], ()
            async for event in provider.stream_events(conversation, tool_definitions(editor) if offer_tools else None):
                if isinstance(event, TextDelta):
                    answer.append(event.text)
                    yield AgentText(event.text)
                elif isinstance(event, ReasoningDelta):
                    yield AgentReasoning(event.text)
                elif isinstance(event, ToolCallRequest):
                    calls = event.calls
            if not calls or not offer_tools:
                break

            conversation.append(assistant_tool_call_message(calls, "".join(answer)))
            for call in calls:
                outcome = execute_tool(editor, call.name, call.arguments)
                logger.info("agent tool call name=%s ok=%s result_chars=%s", call.name, outcome.ok, len(outcome.text))
                yield AgentToolUse(call.name, call.arguments, outcome.text, outcome.ok)
                conversation.append(tool_result_message(call.id, outcome.text))
        completed = True
    finally:
        if not completed:
            editor.proposal = None

    if editor.proposal is not None:
        yield AgentProposal(editor.proposal.text, editor.proposal.diff.render())

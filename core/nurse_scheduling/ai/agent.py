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
import re
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
RAW_TOOL_CALL_PATTERN = re.compile(r"<\s*tool_call\b", re.IGNORECASE)
FINALIZATION_FAILURE = (
    "I could not complete this request within the available tool-call budget. "
    "Please ask me to continue or narrow the request."
)


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
    executed: bool = True


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
    max_tool_calls: int,
) -> AsyncIterator[AgentEvent]:
    """Answer one question, letting the assistant read and edit the schedule.

    The loop ends when the assistant replies without calling a tool. Calls past
    the execution budget receive an error, followed by one tool-free response.
    A run that fails or is abandoned leaves no proposal behind, so the user is
    never offered a schedule from an incomplete answer.
    """
    if max_tool_calls < 0:
        raise ValueError("max_tool_calls must be non-negative")

    conversation = list(messages)
    tool_calls_used = 0
    completed = False
    try:
        while True:
            answer, calls = [], ()
            async for event in provider.stream_events(conversation, tool_definitions(editor)):
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
            rejected_call = False
            for call in calls:
                if tool_calls_used >= max_tool_calls:
                    result = _tool_budget_error(tool_calls_used, max_tool_calls)
                    logger.info("agent tool call name=%s rejected=budget_exhausted", call.name)
                    yield AgentToolUse(call.name, call.arguments, result, False, executed=False)
                    conversation.append(tool_result_message(call.id, result))
                    rejected_call = True
                    continue

                tool_calls_used += 1
                outcome = execute_tool(editor, call.name, call.arguments)
                logger.info(
                    "agent tool call name=%s ok=%s result_chars=%s",
                    call.name,
                    outcome.ok,
                    len(outcome.text),
                )
                yield AgentToolUse(call.name, call.arguments, outcome.text, outcome.ok)
                conversation.append(tool_result_message(call.id, outcome.text))

            if rejected_call:
                async for event in _finalize_after_tool_budget(provider, conversation):
                    yield event
                break
        completed = True
    finally:
        if not completed:
            editor.proposal = None

    if editor.proposal is not None:
        yield AgentProposal(editor.proposal.text, editor.proposal.diff.render())


def _tool_budget_error(used: int, limit: int) -> str:
    """Tell the model that an excess tool call was not executed."""
    return (
        f"Tool call budget exhausted for this request: {used} of {limit} calls have already been executed. "
        "This call was not executed. Do not call another tool. Answer the user using the information already "
        "collected, or explain what remains unresolved."
    )


async def _finalize_after_tool_budget(
    provider: ToolCapableChatProvider,
    conversation: Sequence[ChatMessage],
) -> AsyncIterator[AgentEvent]:
    """Give the model one tool-free response after rejecting an excess call."""
    chunks: list[str] = []
    attempted_call = False
    async for event in provider.stream_events(conversation):
        if isinstance(event, TextDelta):
            chunks.append(event.text)
        elif isinstance(event, ReasoningDelta):
            yield AgentReasoning(event.text)
        elif isinstance(event, ToolCallRequest):
            attempted_call = True

    answer = "".join(chunks)
    raw_call = RAW_TOOL_CALL_PATTERN.search(answer)
    if not attempted_call and raw_call is None and answer:
        for chunk in chunks:
            yield AgentText(chunk)
        return

    safe_prefix = answer[: raw_call.start()].rstrip() if raw_call is not None else answer.rstrip()
    if safe_prefix:
        yield AgentText(f"{safe_prefix}\n\n")
    yield AgentText(FINALIZATION_FAILURE)

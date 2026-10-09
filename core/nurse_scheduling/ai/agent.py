"""Observable agent execution state above the model loop."""

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

import asyncio
from collections.abc import AsyncIterator, Sequence
from contextlib import aclosing
from dataclasses import dataclass, field

from .agent_loop import agent_loop
from .agent_types import (
    AgentEvent,
    AgentTool,
    AgentToolStart,
    AgentToolUse,
    SteeringSource,
    ToolBatchObserver,
    ToolBatchScope,
)
from .provider import ChatMessage, ToolCapableChatProvider
from .transcript import AgentMessage, AssistantMessage


@dataclass
class AgentState:
    """Observable model-loop state, independent of session storage."""

    is_streaming: bool = False
    pending_tool_calls: set[str] = field(default_factory=set)
    messages: list[AgentMessage] = field(default_factory=list)


class Agent:
    """Run a model loop while its caller owns cancellation and cleanup."""

    def __init__(self) -> None:
        self.state = AgentState()

    def reset(self) -> None:
        """Release recorded run data after its caller finishes using it."""
        if self.state.is_streaming:
            raise RuntimeError("Agent is already running. Wait for cleanup before resetting.")
        self.state.messages.clear()
        self.state.pending_tool_calls.clear()

    async def prompt(
        self,
        provider: ToolCapableChatProvider,
        messages: Sequence[ChatMessage],
        tools: Sequence[AgentTool],
        *,
        activity_batch: ToolBatchScope | None = None,
        observe_tool_batch: ToolBatchObserver | None = None,
        take_steering: SteeringSource | None = None,
        max_tool_rounds: int | None = None,
        max_tool_calls: int | None = None,
    ) -> AsyncIterator[AgentEvent]:
        if self.state.is_streaming:
            raise RuntimeError("Agent is already running. Queue steering instead.")
        self.state.is_streaming = True
        self.state.messages.clear()
        events = agent_loop(
            provider,
            messages,
            tools,
            activity_batch=activity_batch,
            observe_tool_batch=observe_tool_batch,
            take_steering=take_steering,
            max_tool_rounds=max_tool_rounds,
            max_tool_calls=max_tool_calls,
            run_messages=self.state.messages,
        )
        try:
            async with aclosing(events):
                async for event in events:
                    if isinstance(event, AgentToolStart):
                        self.state.pending_tool_calls.add(event.tool_call_id)
                    elif isinstance(event, AgentToolUse):
                        self.state.pending_tool_calls.discard(event.tool_call_id)
                    yield event
        except BaseException as exc:
            reason = "aborted" if isinstance(exc, (asyncio.CancelledError, GeneratorExit)) else "error"
            last = self.state.messages[-1] if self.state.messages else None
            if not isinstance(last, AssistantMessage) or last.stop_reason not in {"aborted", "error"}:
                self.state.messages.append(AssistantMessage("", reason))
            raise
        finally:
            self.state.is_streaming = False
            self.state.pending_tool_calls.clear()

"""Stateful agent over the provider-neutral model and tool loop."""

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
    SteeringSource,
    ToolBatchObserver,
    ToolBatchScope,
    ToolExecutionEnd,
    ToolExecutionStart,
)
from .lifecycle import AgentRun
from .provider import ChatMessage, ToolCapableChatProvider


@dataclass
class AgentState:
    """Observable execution state, independent of session persistence."""

    is_streaming: bool = False
    pending_tool_calls: set[str] = field(default_factory=set)


class Agent:
    """Stateful model-loop owner with boundary-consumed steering and cancellation."""

    def __init__(self) -> None:
        self.state = AgentState()
        self.active_run: AgentRun | None = None
        self.accepting_steering = False
        self.steering_queue: list[tuple[str, str]] = []
        self.steering_ids: set[str] = set()
        self._task: asyncio.Task | None = None

    def open_steering(self, accepting: bool) -> None:
        self.close_steering()
        self.accepting_steering = accepting

    def close_steering(self) -> None:
        self.accepting_steering = False
        self.steering_queue.clear()
        self.steering_ids.clear()

    def steer(self, message_id: str, text: str) -> None:
        """Queue already admitted input. The session enforces ownership and limits."""
        if not self.accepting_steering:
            raise RuntimeError("The active run is no longer accepting messages.")
        if message_id not in self.steering_ids:
            self.steering_queue.append((message_id, text))
            self.steering_ids.add(message_id)

    def take_steering(self, close_if_empty: bool) -> list[tuple[str, str]]:
        queued = list(self.steering_queue)
        self.steering_queue.clear()
        if close_if_empty and not queued:
            self.accepting_steering = False
        return queued

    def abort(self) -> None:
        if self.active_run is not None:
            self.active_run.cancel()
        elif self._task is not None and not self._task.cancelling():
            self._task.cancel()

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
        self._task = asyncio.current_task()

        try:
            events = agent_loop(
                provider,
                messages,
                tools,
                activity_batch=activity_batch,
                observe_tool_batch=observe_tool_batch,
                take_steering=take_steering or self.take_steering,
                max_tool_rounds=max_tool_rounds,
                max_tool_calls=max_tool_calls,
            )
            async with aclosing(events):
                async for event in events:
                    if isinstance(event, ToolExecutionStart):
                        self.state.pending_tool_calls.add(event.tool_call_id)
                    elif isinstance(event, ToolExecutionEnd):
                        self.state.pending_tool_calls.discard(event.tool_call_id)
                    yield event
        finally:
            self.state.is_streaming = False
            self.state.pending_tool_calls.clear()
            self._task = None

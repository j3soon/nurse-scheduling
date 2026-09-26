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

from collections.abc import AsyncIterator, Sequence
from contextlib import aclosing
from dataclasses import dataclass, field

from .agent_loop import agent_loop
from .agent_types import (
    AgentEvent,
    AgentTool,
    RequestPreparer,
    SteeringSource,
    ToolBatchObserver,
    ToolBatchScope,
    ToolExecutionEnd,
    ToolExecutionStart,
)
from .context import prepare_provider_request
from .provider import ChatMessage, ToolCapableChatProvider
from .transcript import AgentMessage


@dataclass
class AgentState:
    """Observable execution state, independent of session persistence."""

    is_streaming: bool = False
    pending_tool_calls: set[str] = field(default_factory=set)
    messages: list[AgentMessage] = field(default_factory=list)


class Agent:
    """Stateful model-loop owner with boundary-consumed steering.

    Unlike Pi's Agent, cancellation belongs to the `AgentRun` whose task consumes
    `prompt`, because Stop must also cancel queued runs and must not interrupt
    cleanup. Closing or cancelling that consumer resets this state.
    """

    def __init__(self) -> None:
        self.state = AgentState()
        self._accepting_steering = False
        self._steering_queue: list[tuple[str, str]] = []
        # Every ID steered this run, kept after draining so a retried POST stays idempotent.
        self._steering_ids: set[str] = set()

    @property
    def accepting_steering(self) -> bool:
        return self._accepting_steering

    @property
    def steered_count(self) -> int:
        """Messages admitted during this run, including those already delivered."""
        return len(self._steering_ids)

    @property
    def queued_steering(self) -> tuple[str, ...]:
        """Texts waiting for the next model boundary."""
        return tuple(text for _message_id, text in self._steering_queue)

    def has_steered(self, message_id: str) -> bool:
        return message_id in self._steering_ids

    def open_steering(self, accepting: bool) -> None:
        self.close_steering()
        self._accepting_steering = accepting

    def close_steering(self) -> None:
        self._accepting_steering = False
        self._steering_queue.clear()
        self._steering_ids.clear()
        self.state.messages.clear()

    def steer(self, message_id: str, text: str) -> None:
        """Queue already admitted input. The session enforces ownership and limits."""
        if not self._accepting_steering:
            raise RuntimeError("The active run is no longer accepting messages.")
        if message_id not in self._steering_ids:
            self._steering_queue.append((message_id, text))
            self._steering_ids.add(message_id)

    def take_steering(self, close_if_empty: bool) -> list[tuple[str, str]]:
        queued = list(self._steering_queue)
        self._steering_queue.clear()
        if close_if_empty and not queued:
            self._accepting_steering = False
        return queued

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
        prepare_request: RequestPreparer = prepare_provider_request,
    ) -> AsyncIterator[AgentEvent]:
        if self.state.is_streaming:
            raise RuntimeError("Agent is already running. Queue steering instead.")
        self.state.is_streaming = True
        self.state.messages.clear()

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
                prepare_request=prepare_request,
                run_messages=self.state.messages,
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

"""Public session event projection and per-run text batching."""

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
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Literal

from .agent_types import (
    AgentEvent,
    AgentProposal,
    AgentSteering,
    MessageEnd,
    MessageReasoningDelta,
    MessageTextDelta,
    ToolExecutionEnd,
    ToolExecutionStart,
)
from .provider import TokenUsage
from .session_events import AgentSessionEvent, AgentSessionRunEvent, AgentSessionTerminalEvent, TextEvent
from .transcript import AgentMessage, AssistantMessage
from .workspace import AgentDownload, AgentScheduleChange


@dataclass
class RunOutput:
    """Project agent events onto the public session contract and track interrupted output."""

    # Output of the model response in progress, which only an interruption can leave open.
    pending_text: list[str] = field(default_factory=list)
    pending_reasoning: list[str] = field(default_factory=list)
    proposal: AgentProposal | None = None
    download: AgentDownload | None = None
    usage: TokenUsage | None = None
    # The latest provider call holds the whole request, so it shows how full the context window is.
    last_call: TokenUsage | None = None

    def interrupted_entries(
        self, entries: Sequence[AgentMessage], stop_reason: Literal["aborted", "error"]
    ) -> list[AgentMessage]:
        """End the run with Pi's interrupted assistant message, holding any partial response."""
        interrupted = AssistantMessage("".join(self.pending_text), stop_reason, "".join(self.pending_reasoning))
        return [*entries, interrupted]

    def consume(self, event: AgentEvent | AgentScheduleChange | AgentDownload) -> AgentSessionRunEvent | None:
        if isinstance(event, MessageTextDelta):
            self.pending_text.append(event.text)
            return {"type": "delta", "text": event.text}
        if isinstance(event, MessageReasoningDelta):
            self.pending_reasoning.append(event.text)
            return {"type": "reasoning", "text": event.text}
        if isinstance(event, MessageEnd):
            self.pending_text.clear()
            self.pending_reasoning.clear()
            return {"type": "truncated"} if event.message.stop_reason == "length" else None
        if isinstance(event, TokenUsage):
            self.usage = event if self.usage is None else self.usage + event
            self.last_call = event
        elif isinstance(event, ToolExecutionStart):
            return {
                "type": "tool_start",
                "tool_call_id": event.tool_call_id,
                "name": event.name,
                "arguments": event.arguments,
            }
        elif isinstance(event, ToolExecutionEnd):
            return {
                "type": "tool",
                "tool_call_id": event.tool_call_id,
                "name": event.name,
                "arguments": event.arguments,
                "result": event.result,
                "ok": event.ok,
            }
        elif isinstance(event, AgentSteering):
            return {"type": "steering", "message_id": event.message_id, "message": event.text}
        elif isinstance(event, AgentScheduleChange):
            return {"type": "schedule_change", "schedule_yaml": event.schedule_yaml}
        elif isinstance(event, AgentDownload):
            self.download = event
        elif isinstance(event, AgentProposal):
            self.proposal = event
        return None


class RunEvents:
    """Batch text for one run and defer its terminal event until finalization."""

    def __init__(self, run_id: str, publish: Callable[[AgentSessionEvent], None]) -> None:
        self.run_id = run_id
        self._publish = publish
        self._pending: TextEvent | None = None
        self._timer: asyncio.TimerHandle | None = None
        self._terminal: AgentSessionTerminalEvent | None = None

    def flush(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        if self._pending is not None:
            self._publish(self._pending)
            self._pending = None

    def emit(self, event: AgentSessionRunEvent) -> None:
        # Every replayable fragment identifies its run, even after run_start expires.
        event = event.copy()
        event["run_id"] = self.run_id
        if (
            event["type"] == "done"
            or event["type"] == "stopped"
            or event["type"] == "stale"
            or event["type"] == "error"
        ):
            self._terminal = event
        elif event["type"] == "delta" or event["type"] == "reasoning":
            # Batch tiny provider fragments before the stream assigns publication IDs.
            if self._pending is not None and self._pending["type"] != event["type"]:
                self.flush()
            text = self._pending["text"] if self._pending is not None else ""
            self._pending = {"type": event["type"], "run_id": self.run_id, "text": text + event["text"]}
            if len(self._pending["text"]) >= 2048:
                self.flush()
            elif self._timer is None:
                self._timer = asyncio.get_running_loop().call_later(0.025, self.flush)
        else:
            self.flush()
            self._publish(event)

    def finish(self) -> None:
        self.flush()
        if self._terminal is not None:
            self._publish(self._terminal)
            self._terminal = None

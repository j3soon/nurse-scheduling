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
    AgentCompactionEnd,
    AgentCompactionStart,
    AgentContextUsage,
    AgentEvent,
    AgentGenerationProgress,
    AgentMessageEnd,
    AgentProposal,
    AgentReasoning,
    AgentSteering,
    AgentText,
    AgentToolStart,
    AgentToolUse,
)
from .context import interrupted_entries
from .costs import CostTotals
from .provider import ProviderCall, ProviderRetry, TokenUsage
from .session_event_stream import SessionEvent
from .session_events import AgentSessionEvent, AgentSessionRunEvent, AgentSessionTerminalEvent, TextEvent, ToolEndEvent
from .transcript import AgentMessage
from .workspace import AgentAnalysis, AgentDownload, AgentScheduleChange


@dataclass
class RunOutput:
    """Project agent events onto the public session contract and track interrupted output."""

    # Output of the model response in progress, which only an interruption can leave open.
    pending_text: list[str] = field(default_factory=list)
    pending_reasoning: list[str] = field(default_factory=list)
    proposal: AgentProposal | None = None
    download: AgentDownload | None = None
    analysis: AgentAnalysis | None = None
    usage: TokenUsage | None = None
    # The latest provider call holds the whole request, so it shows how full the context window is.
    last_call: TokenUsage | None = None
    context_estimate: int | None = None
    compaction: AgentCompactionStart | None = None
    compaction_progress: AgentGenerationProgress | None = None
    calls: dict[str, ProviderCall] = field(default_factory=dict)
    costs: CostTotals = field(default_factory=CostTotals)

    def interrupted_entries(
        self, entries: Sequence[AgentMessage], stop_reason: Literal["aborted", "error"]
    ) -> list[AgentMessage]:
        """End the run with Pi's interrupted assistant message, holding any partial response."""
        return interrupted_entries(entries, stop_reason)

    def consume(
        self, event: AgentEvent | AgentScheduleChange | AgentDownload | AgentAnalysis
    ) -> AgentSessionRunEvent | None:
        if isinstance(event, AgentText):
            self.pending_text.append(event.text)
            return {"type": "delta", "text": event.text}
        if isinstance(event, AgentReasoning):
            self.pending_reasoning.append(event.text)
            return {"type": "reasoning", "text": event.text}
        if isinstance(event, AgentMessageEnd):
            self.pending_text.clear()
            self.pending_reasoning.clear()
            if not event.message.tool_calls and event.message.stop_reason in {"stop", "length"}:
                # Validation and workspace cleanup can still reject the final answer.
                return {"type": "truncated"} if event.message.stop_reason == "length" else None
            return {"type": "response_end", "stop_reason": event.message.stop_reason}
        if isinstance(event, ProviderRetry):
            return {"type": "provider_retry", "message": event.message}
        if isinstance(event, AgentContextUsage):
            self.context_estimate = event.used_tokens
            return None
        if isinstance(event, AgentCompactionStart):
            self.compaction = event
            self.compaction_progress = None
            return {"type": "compaction_start", "reason": event.reason, "tokens_before": event.tokens_before}
        if isinstance(event, AgentGenerationProgress):
            if event.kind == "compaction":
                self.compaction_progress = event
            return {
                "type": "generation_progress",
                "kind": event.kind,
                "characters": event.characters,
                "step": event.step,
            }
        if isinstance(event, AgentCompactionEnd):
            self.compaction = None
            if event.success:
                self.last_call = None
                self.context_estimate = event.estimated_tokens_after
            result = {
                "type": "compaction_end",
                "reason": event.reason,
                "success": event.success,
                "aborted": event.aborted,
                "tokens_before": event.tokens_before,
            }
            if event.estimated_tokens_after is not None:
                result["estimated_tokens_after"] = event.estimated_tokens_after
            if event.skipped:
                result["skipped"] = True
            if self.compaction_progress is not None:
                result["characters"] = self.compaction_progress.characters
                result["step"] = self.compaction_progress.step
                self.compaction_progress = None
            if event.success and event.summary is not None:
                result["summary"] = event.summary
                result["keep_messages"] = event.keep_messages
            return result
        if isinstance(event, TokenUsage):
            self.context_estimate = None
            self.usage = event if self.usage is None else self.usage + event
            self.last_call = event
        elif isinstance(event, AgentToolStart):
            return {
                "type": "tool_start",
                "tool_call_id": event.tool_call_id,
                "name": event.name,
                "arguments": event.arguments,
            }
        elif isinstance(event, AgentToolUse):
            tool_event: ToolEndEvent = {
                "type": "tool",
                "tool_call_id": event.tool_call_id,
                "name": event.name,
                "arguments": event.arguments,
                "result": event.result,
                "ok": event.ok,
            }
            if event.details and "schedule_check" in event.details:
                tool_event["schedule_check"] = event.details["schedule_check"]
            if event.details and "replay_arguments" in event.details:
                tool_event["replay_arguments"] = event.details["replay_arguments"]
            return tool_event
        elif isinstance(event, AgentSteering):
            return {"type": "steering", "message_id": event.message_id, "message": event.text}
        elif isinstance(event, AgentScheduleChange):
            return {"type": "schedule_change", "schedule_yaml": event.schedule_yaml}
        elif isinstance(event, AgentAnalysis):
            self.analysis = event
        elif isinstance(event, AgentDownload):
            self.download = event
        elif isinstance(event, AgentProposal):
            self.proposal = event
        return None


class RunEvents:
    """Batch text for one run and defer its terminal event until finalization."""

    def __init__(self, run_id: str, publish: Callable[[AgentSessionEvent], SessionEvent | None]) -> None:
        self.run_id = run_id
        self._publish = publish
        self._pending: TextEvent | None = None
        self._pending_usage: AgentSessionRunEvent | None = None
        self._pending_progress: AgentSessionRunEvent | None = None
        self._timer: asyncio.TimerHandle | None = None
        self._terminal: AgentSessionTerminalEvent | None = None

    def flush(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        if self._pending is not None:
            self._publish(self._pending)
            self._pending = None
        if self._pending_usage is not None:
            self._publish(self._pending_usage)
            self._pending_usage = None
        if self._pending_progress is not None:
            self._publish(self._pending_progress)
            self._pending_progress = None

    def emit(self, event: AgentSessionRunEvent) -> SessionEvent | None:
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
            if self._pending_progress is not None:
                self.flush()
            # Batch tiny provider fragments before the stream assigns publication IDs.
            if self._pending is not None and self._pending["type"] != event["type"]:
                self.flush()
            text = self._pending["text"] if self._pending is not None else ""
            self._pending = {"type": event["type"], "run_id": self.run_id, "text": text + event["text"]}
            if len(self._pending["text"]) >= 2048:
                self.flush()
            elif self._timer is None:
                self._timer = asyncio.get_running_loop().call_later(0.025, self.flush)
        elif event["type"] == "generation_progress":
            if self._pending is not None or (
                self._pending_progress is not None
                and (self._pending_progress["kind"], self._pending_progress["step"]) != (event["kind"], event["step"])
            ):
                self.flush()
            self._pending_progress = event
            if self._timer is None:
                self._timer = asyncio.get_running_loop().call_later(0.025, self.flush)
        elif event["type"] == "context_usage" and self._pending is not None:
            # Publish the latest estimate with the same batch as its streamed text.
            self._pending_usage = event
        else:
            self.flush()
            return self._publish(event)
        return None

    def finish(self) -> None:
        self.flush()
        if self._terminal is not None:
            self._publish(self._terminal)
            self._terminal = None

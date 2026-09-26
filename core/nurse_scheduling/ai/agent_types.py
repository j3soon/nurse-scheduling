"""Provider-neutral agent events and executable tool contracts."""

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

from collections.abc import Awaitable, Callable, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Any

from .provider import ChatMessage, TokenUsage, ToolResultImage
from .transcript import AssistantMessage


@dataclass(frozen=True)
class MessageTextDelta:
    """One streamed fragment of the answer shown to the user."""

    text: str


@dataclass(frozen=True)
class MessageReasoningDelta:
    """One streamed fragment of the model's reasoning, for the reader only."""

    text: str


@dataclass(frozen=True)
class MessageEnd:
    """One complete model response, as Pi's message_end, with its stop reason."""

    message: AssistantMessage


@dataclass(frozen=True)
class ToolExecutionStart:
    """One tool request recorded before execution begins."""

    name: str
    arguments: str
    tool_call_id: str


@dataclass(frozen=True)
class ToolExecutionEnd:
    """One tool call the assistant made, with what it sent and received."""

    name: str
    arguments: str
    result: str
    ok: bool
    tool_call_id: str
    details: dict[str, Any] | None = None


@dataclass(frozen=True)
class AgentSteering:
    """One queued user message injected at a model turn boundary."""

    message_id: str
    text: str


@dataclass(frozen=True)
class AgentProposal:
    """The schedule the run ended with, waiting for the user to approve it."""

    text: str
    diff: str


AgentEvent = (
    MessageTextDelta
    | MessageReasoningDelta
    | MessageEnd
    | ToolExecutionStart
    | ToolExecutionEnd
    | AgentSteering
    | AgentProposal
    | TokenUsage
)
ToolBatchScope = Callable[[], AbstractAsyncContextManager[None]]
SteeringSource = Callable[[bool], Sequence[tuple[str, str]]]
# Derive one provider request from the run's conversation without changing it.
RequestPreparer = Callable[[Sequence[ChatMessage]], list[ChatMessage]]


@dataclass(frozen=True)
class AgentToolResult:
    """One provider-neutral result produced by an agent-facing tool."""

    text: str
    ok: bool
    image: ToolResultImage | None = None
    details: dict[str, Any] | None = None


@dataclass(frozen=True)
class AgentToolBatchMetrics:
    """Execution timing for one model-issued tool batch."""

    call_count: int
    parallel: bool
    execution_seconds: float


ToolBatchObserver = Callable[[AgentToolBatchMetrics], None]


@dataclass(frozen=True)
class AgentTool:
    """A model-facing definition bound to its execution and concurrency policy."""

    definition: dict[str, Any]
    execute: Callable[[str], Awaitable[AgentToolResult]]
    read_only: bool = False

    @property
    def name(self) -> str:
        return self.definition["function"]["name"]

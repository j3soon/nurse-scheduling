"""Typed public session events, following Pi v1.0.0 AgentSessionEvent."""

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

from typing import Any, Literal, NotRequired, TypedDict


class RunFields(TypedDict):
    # RunOutput emits before the owning run attaches its identity at publication.
    run_id: NotRequired[str]


class RunStartEvent(RunFields):
    type: Literal["run_start"]
    trigger: Literal["user", "optimizer"]


class TextEvent(RunFields):
    type: Literal["delta", "reasoning"]
    text: str


class TruncatedEvent(RunFields):
    type: Literal["truncated"]


class RunStoppedEvent(RunFields):
    type: Literal["stopped"]


class RunDoneEvent(RunFields):
    type: Literal["done"]
    history_saved: NotRequired[bool]


class RunErrorEvent(RunFields):
    type: Literal["stale", "error"]
    message: str


class ToolFields(RunFields):
    tool_call_id: str
    name: str
    arguments: str


class ToolStartEvent(ToolFields):
    type: Literal["tool_start"]


class ToolEndEvent(ToolFields):
    type: Literal["tool"]
    result: str
    ok: bool


class SteeringEvent(RunFields):
    type: Literal["steering"]
    message_id: str
    message: str


class ScheduleChangeEvent(RunFields):
    type: Literal["schedule_change"]
    schedule_yaml: str


class ProposalEvent(RunFields):
    type: Literal["proposal"]
    diff: str


class DownloadEvent(RunFields):
    type: Literal["download"]
    download_id: str


class WarningEvent(RunFields):
    type: Literal["warning"]
    message: str


class ModelInputMessage(TypedDict):
    kind: Literal["app", "question", "optimizer", "status"]
    content: str
    # Absolute history position of an app event, so a retried run does not show it twice.
    index: NotRequired[int]
    title: NotRequired[str]


class ModelInputEvent(RunFields):
    """The system message and the request messages added since the last assistant reply."""

    type: Literal["model_input"]
    system: str
    messages: list[ModelInputMessage]
    schedule_yaml: NotRequired[str]


class ContextUsageEvent(RunFields):
    type: Literal["context_usage"]
    used_chars: int
    max_chars: int
    # Tokens of the latest provider request. The limit is absent without model metadata.
    used_tokens: NotRequired[int]
    max_tokens: NotRequired[int]


class HistoryTrimmedEvent(RunFields):
    type: Literal["history_trimmed"]
    dropped: int


class OptimizerStateUpdate(TypedDict):
    """Job state shared by the optimizer callback and the public session event."""

    job_id: str
    state: str
    terminal: bool
    backend: dict[str, Any]
    request: dict[str, Any]
    result: dict[str, Any] | None
    error: dict[str, Any] | None
    downloadable: bool


class OptimizerProgressUpdate(TypedDict):
    job_id: str
    progress: dict[str, Any]


OptimizerUpdate = OptimizerStateUpdate | OptimizerProgressUpdate


class OptimizationEvent(OptimizerStateUpdate):
    type: Literal["optimization"]


class OptimizationProgressEvent(OptimizerProgressUpdate):
    type: Literal["optimization_progress"]


AgentSessionTerminalEvent = RunDoneEvent | RunErrorEvent | RunStoppedEvent
AgentSessionRunEvent = (
    RunStartEvent
    | TextEvent
    | TruncatedEvent
    | RunStoppedEvent
    | RunDoneEvent
    | RunErrorEvent
    | ToolStartEvent
    | ToolEndEvent
    | SteeringEvent
    | ScheduleChangeEvent
    | ProposalEvent
    | DownloadEvent
    | WarningEvent
    | ModelInputEvent
    | ContextUsageEvent
    | HistoryTrimmedEvent
)
AgentSessionEvent = AgentSessionRunEvent | OptimizationEvent | OptimizationProgressEvent

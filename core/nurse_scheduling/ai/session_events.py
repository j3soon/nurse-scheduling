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


class ModelSelectionEvent(RunFields):
    type: Literal["model_selection"]
    model: str
    reasoning: str


class ProviderCallEvent(RunFields):
    type: Literal["provider_call"]
    call_id: str
    model: str
    reasoning: str
    status: Literal["pending", "reported", "unavailable"]
    cost_usd: str | None
    usage: dict[str, Any] | None
    provider_call_id: str | None
    response_model: str | None


class CostSummaryEvent(RunFields):
    type: Literal["cost_summary"]
    conversation: dict[str, Any]
    run: dict[str, Any]


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


class ProviderRetryEvent(RunFields):
    type: Literal["provider_retry"]
    message: str


class ResponseEndEvent(RunFields):
    type: Literal["response_end"]
    stop_reason: Literal["stop", "tool_use", "length", "error", "aborted"]
    context_note: NotRequired[str]


class ToolFields(RunFields):
    tool_call_id: str
    name: str
    arguments: str


class ToolStartEvent(ToolFields):
    type: Literal["tool_start"]


class ScheduleCheck(TypedDict):
    ok: bool
    text: str


class ToolEndEvent(ToolFields):
    type: Literal["tool"]
    result: str
    ok: bool
    replay_arguments: NotRequired[str]
    # The trusted schedule check included in `result`, when the tool changed the working copy.
    schedule_check: NotRequired[ScheduleCheck]


class SteeringEvent(RunFields):
    type: Literal["steering"]
    message_id: str
    message: str


class ScheduleChangeEvent(RunFields):
    type: Literal["schedule_change"]
    schedule_yaml: str


class ScheduleAppliedEvent(RunFields):
    type: Literal["schedule_applied"]
    schedule_yaml: str
    diff: str
    # The run's schedule replaced a browser update queued during the run.
    replaced_queued_schedule: bool


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


class CompactionFields(RunFields):
    reason: Literal["threshold", "overflow"]
    tokens_before: int


class CompactionStartEvent(CompactionFields):
    type: Literal["compaction_start"]


class CompactionEndEvent(CompactionFields):
    type: Literal["compaction_end"]
    success: bool
    aborted: bool
    estimated_tokens_after: NotRequired[int]
    summary: NotRequired[str]
    keep_messages: NotRequired[int]


class ContextUsageEvent(RunFields):
    type: Literal["context_usage"]
    used_chars: int
    max_chars: int
    # Latest request tokens, or an estimate after compaction. The limit needs model metadata.
    used_tokens: NotRequired[int]
    max_tokens: NotRequired[int]
    estimated: NotRequired[bool]


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
    | ModelSelectionEvent
    | ProviderCallEvent
    | CostSummaryEvent
    | TextEvent
    | TruncatedEvent
    | RunStoppedEvent
    | RunDoneEvent
    | RunErrorEvent
    | ToolStartEvent
    | ToolEndEvent
    | SteeringEvent
    | ProviderRetryEvent
    | ResponseEndEvent
    | ScheduleChangeEvent
    | ScheduleAppliedEvent
    | DownloadEvent
    | WarningEvent
    | ModelInputEvent
    | ContextUsageEvent
    | CompactionStartEvent
    | CompactionEndEvent
    | HistoryTrimmedEvent
)
AgentSessionEvent = AgentSessionRunEvent | OptimizationEvent | OptimizationProgressEvent

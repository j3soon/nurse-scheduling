"""Application session state and transactional agent run finalization."""

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
import hashlib
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable, Sequence
from contextlib import aclosing
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Literal, Protocol, TypeVar

from fastapi import HTTPException
from ruamel.yaml.error import YAMLError

from ..loader import _load_yaml
from .agent import Agent
from .agent_types import AgentCompaction, AgentCompactionEnd, AgentContextUsage
from .compaction import ContextCompactor
from .config import AiSettings
from .context import (
    SCHEDULE_CHANGED_EVENT,
    QuestionKind,
    build_provider_messages,
    context_usage,
    model_input,
    project_history,
    removal_event,
    retained_entries,
)
from .costs import CostTotals
from .history import RECOVERY_UNAVAILABLE, EntryRow, RunKind, RunStatus
from .lifecycle import AgentRun, RunSnapshot, SessionRuns
from .optimizer import OptimizerArtifact, SessionOptimizer
from .optimizer_tool import execute_optimizer_tool, optimizer_tool_definition
from .provider import ChatMessage, ProviderCall, ProviderError, TokenUsage, ToolCapableChatProvider
from .sandbox import SandboxError, SandboxFactory
from .sandbox_tools import SandboxPiTools
from .session_event_projection import RunEvents, RunOutput
from .session_event_stream import SessionEvent, SessionEventStream
from .session_events import (
    AgentSessionEvent,
    AgentSessionTerminalEvent,
    OptimizationEvent,
    OptimizationProgressEvent,
    OptimizerUpdate,
    RunDoneEvent,
)
from .transcript import (
    AgentMessage,
    AppEventEntry,
    AssistantMessage,
    ToolResultMessage,
    UserMessage,
)
from .workspace import (
    AgentAnalysis,
    SandboxAttachment,
    SandboxAttachmentUnavailableError,
    SandboxCandidateError,
    SandboxCommandTimeoutError,
    SandboxDownloadError,
    SandboxTurnTimeoutError,
    WorkspaceLimits,
    attachment_path,
)
from .workspace_tools import run_workspace

CANDIDATE_VALIDATION_ERROR = (
    "The candidate schedule failed trusted validation. All schedule changes made during this agent run were "
    "discarded. The current schedule was not changed."
)
PROVIDER_ERROR = "The AI provider failed. Please try again."
SANDBOX_COMMAND_TIMEOUT_ERROR = (
    "An AI shell command timed out. The temporary workspace was discarded. Please try again."
)
DOWNLOAD_RETENTION_WARNING = (
    "The generated ZIP could not be retained because a chat or service storage limit was reached."
)
SANDBOX_RUN_TIMEOUT_ERROR = "The AI response timed out. Please try again."
STALE_RUN_ERROR = "The schedule changed while this response was generated, so the response was discarded."
BACKGROUND_RECOVERY_ERROR = "AI message recovery is unavailable, so the optimizer result was not reviewed."
RECOVERY_SAVE_WARNING = "This response could not be saved for recovery after a service restart."
logger = logging.getLogger("nurse_scheduling.ai")
_Result = TypeVar("_Result")


def schedule_revision(schedule_yaml: str) -> str:
    """Identify one exact schedule snapshot, so the browser applies a run's schedule only over its base."""
    return hashlib.sha256(schedule_yaml.encode("utf-8")).hexdigest()


def _schedule_data(schedule_yaml: str) -> object:
    """Parse a schedule for comparison, so a formatting-only change is not reported as an edit."""
    try:
        return _load_yaml(schedule_yaml.encode(), reject_aliases=True)
    except (ValueError, YAMLError):
        return schedule_yaml


def schedule_data_changed(before: str, after: str) -> bool:
    """Report whether a schedule change is more than formatting. Callers may run it off the event loop."""
    return before != after and _schedule_data(before) != _schedule_data(after)


@dataclass(frozen=True)
class RunCompletion:
    """Whether a completed run and its optional schedule change were retained."""

    run_saved: bool
    schedule_applied: bool
    history_trimmed_count: int = 0
    context_used_chars: int = 0
    # The run's schedule replaced a browser update queued during the run.
    replaced_queued_schedule: bool = False


@dataclass(frozen=True)
class QueuedSchedule:
    """The latest browser schedule received during a run, applied after the run ends."""

    schedule_yaml: str
    # Whether its data differs from the session schedule, when the update request compared them.
    data_changed: bool | None


@dataclass(frozen=True)
class RunOutcome:
    """One execution result, finalized after workspace cleanup and before releasing the run."""

    status: Literal["completed", "stale", "cancelled", "failed"] = "cancelled"
    completion: RunCompletion | None = None
    error_code: str | None = None
    terminal: AgentSessionTerminalEvent | None = None


@dataclass
class AcceptedMessage:
    """The newest client message ID of a session, so a retried POST reattaches to its run."""

    message_id: str
    question: str
    run: AgentRun | None
    run_id: str


@dataclass(frozen=True)
class MessageReceipt:
    """The run that answers a client message. `run` is set only when this request started it."""

    run_id: str
    run: AgentRun | None = None


class SessionPersistence(Protocol):
    """Session operations needed by a foreground or background run."""

    def begin(self, session_id: str, owner_token: str | None, *, run_id: str | None = None) -> RunSnapshot: ...

    def remember_message(self, session_id: str, message: AcceptedMessage) -> None: ...

    def take_steering(self, session_id: str, close_if_empty: bool) -> list[tuple[str, str]]: ...

    def begin_background(self, session_id: str, *, run_id: str | None = None) -> RunSnapshot | None: ...

    def finish(
        self,
        session_id: str,
        entries: Sequence[AgentMessage],
        schedule_yaml: str | None = None,
        *,
        snapshot: RunSnapshot,
    ) -> RunCompletion: ...

    def abort(self, session_id: str, snapshot: RunSnapshot) -> None: ...

    def apply_queued_schedule(self, session_id: str) -> None: ...

    def save_download(self, session_id: str, download_id: str, content: bytes) -> bool: ...


class RunRecorder(Protocol):
    """Run records, Stop requests, and session state saved for restart recovery."""

    @property
    def enabled(self) -> bool: ...

    async def save_provider_call(self, session_id: str, event: SessionEvent | None) -> bool: ...

    async def find_message(self, session_id: str, message_id: str) -> tuple[str, str] | None: ...

    async def message_stopped(self, session_id: str, message_id: str) -> bool: ...

    async def stop_message(self, session_id: str, message_id: str) -> None: ...

    async def read_upload(self, session_id: str, owner: str, upload: SandboxAttachment) -> bytes: ...

    async def save(self, session_id: str, credential_id: str | None = None) -> bool: ...

    async def start_run(
        self,
        session_id: str,
        run_id: str,
        prompt: str | None,
        prompt_seq: int,
        *,
        model: str,
        attachment_count: int,
        kind: RunKind,
        message_id: str | None,
        credential_id: str | None,
    ) -> bool: ...

    async def finish_run(
        self,
        session_id: str,
        run_id: str,
        status: RunStatus,
        error_code: str | None,
        usage: TokenUsage | None,
        committed: bool,
        *,
        schedule_change: dict[str, Any] | None = None,
    ) -> bool: ...


@dataclass(frozen=True)
class SessionRuntime:
    """Shared service dependencies for foreground and optimizer-triggered runs."""

    settings: AiSettings
    store: SessionPersistence
    concurrency_limit: asyncio.Semaphore
    recorder: RunRecorder
    provider: ToolCapableChatProvider
    sandbox_factory: SandboxFactory
    session_optimizer: SessionOptimizer
    selection: dict[str, str] | None = None


async def _complete(write: Awaitable[_Result]) -> _Result:
    """Finish a recovery write even when the caller is cancelled.

    asyncio cancellation and ASGI cancel scopes both wait for the write.
    """
    task = asyncio.ensure_future(write)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        raise


@dataclass
class AgentSession:
    """Process-local conversation state owned by one browser cookie."""

    id: str
    owner_token: str
    expires_at: float
    schedule_yaml: str
    revision: str
    transcript: list[AgentMessage] = field(default_factory=list)
    dropped_history_messages: int = 0
    # Conversation entries that retention trimmed from the front, which a restore skips.
    dropped_entries: int = 0
    # Saved entries are numbered in session order, as Pi's session entries.
    next_entry_seq: int = 0
    version: int = 0
    snapshot: RunSnapshot | None = None
    queued_schedule: QueuedSchedule | None = None
    agent: Agent = field(default_factory=Agent)
    # Retained source files keyed by upload ID, in upload order, and generated ZIPs keyed by run ID.
    uploads: dict[str, SandboxAttachment] = field(default_factory=dict)
    pending_upload_removals: set[str] = field(default_factory=set)
    removed_upload_paths: set[str] = field(default_factory=set)
    downloads: dict[str, bytes | None] = field(default_factory=dict)
    pending_download_removals: set[str] = field(default_factory=set)
    pending_archive_files: dict[tuple[str, str], dict] = field(default_factory=dict)
    # Bytes of every file version that recovery storage keeps for this session, including removed files.
    archive_bytes: int = 0
    analysis: AgentAnalysis | None = None
    latest_message: AcceptedMessage | None = None
    frontend_version: str | None = None
    frontend_timezone: str = "UTC"
    # Latest browser address, forwarded to the optimizer's per-address job limit. Never saved.
    client_address: str | None = None
    reported_version_mismatch: bool = False
    export_metadata: dict[str, Any] = field(default_factory=dict)
    model_selection: dict[str, str] | None = None
    locked_model: str | None = None
    provider_credential_id: str | None = None
    cost_totals: CostTotals = field(default_factory=CostTotals)
    cost_totals_version: int = 0
    pending_provider_calls: dict[str, ProviderCall] = field(default_factory=dict)
    accepted_messages: dict[str, AcceptedMessage] = field(default_factory=dict)
    # Named Stop requests, including those for messages that have not arrived yet.
    stopped_message_ids: set[str] = field(default_factory=set)
    event_stream: SessionEventStream | None = field(default=None, repr=False)
    # Recovery storage, which receives each new entry as Pi's SessionManager does.
    entry_log: Callable[[str, EntryRow], None] | None = field(default=None, repr=False)
    _saved_run_messages: int = field(default=0, repr=False)
    _listeners: list[Callable[[AgentSessionEvent], None]] = field(default_factory=list, repr=False)
    _events_closed: bool = False
    _admission_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    def observe_frontend_version(self, version: str | None, backend_version: str) -> None:
        """Keep the browser build available and report a mismatch once per loaded session."""
        if version is not None:
            self.frontend_version = version
        self.export_metadata["backend_version"] = backend_version
        if self.frontend_version is None or self.reported_version_mismatch:
            return
        if self.frontend_version == backend_version and not backend_version.endswith("-dirty"):
            return
        self.reported_version_mismatch = True
        logger.error(
            "AI frontend and backend versions do not match session_id=%s frontend_version=%s backend_version=%s",
            self.id,
            self.frontend_version,
            backend_version,
            extra={"frontend_version": self.frontend_version, "backend_version": backend_version},
        )

    @property
    def history(self) -> list[ChatMessage]:
        """Render the retained transcript for callers that inspect conversation text."""
        from .context import projected_history

        return projected_history(self.transcript)

    def recovery_state(self) -> dict[str, Any]:
        """Return the schedule and retention counts that a restored session continues.

        The conversation itself is rebuilt from saved entries.
        """
        return {
            "schedule_yaml": self.schedule_yaml,
            "queued_schedule": asdict(self.queued_schedule) if self.queued_schedule else None,
            "model_selection": self.model_selection,
            "locked_model": self.locked_model,
            "provider_credential_id": self.provider_credential_id,
            "cost_totals": self.cost_totals.public(),
            "cost_totals_version": self.cost_totals_version,
            "pending_provider_calls": [
                {"id": call.id, "model": call.model, "status": call.status, "cost_usd": call.cost_usd}
                for call in self.pending_provider_calls.values()
            ],
            "frontend_version": self.frontend_version,
            "frontend_timezone": self.frontend_timezone,
            "downloads": list(self.downloads),
            "uploads": [
                {
                    "id": upload.id,
                    "filename": upload.filename,
                    "media_type": upload.media_type,
                    "size_bytes": upload.byte_count,
                    "request_sha256": upload.request_sha256,
                }
                for upload in self.uploads.values()
            ],
            "export_metadata": {
                **self.export_metadata,
                "uploaded_files": [
                    {"filename": upload.filename, "bytes": upload.byte_count} for upload in self.uploads.values()
                ],
            },
            "dropped_history_messages": self.dropped_history_messages,
            "dropped_entries": self.dropped_entries,
        }

    @classmethod
    def restored(
        cls,
        session_id: str,
        owner_token: str,
        expires_at: float,
        state: dict[str, Any],
        *,
        entries: Sequence[AgentMessage],
        next_entry_seq: int,
        uploads: Sequence[SandboxAttachment] = (),
        removed_upload_paths: Sequence[str] = (),
        archive_bytes: int = 0,
        event_stream: SessionEventStream | None,
        entry_log: Callable[[str, EntryRow], None] | None,
    ) -> "AgentSession":
        """Rebuild a session from `recovery_state` and its saved conversation entries.

        File bytes are loaded separately from their persisted references. Analysis notes are not saved.
        """
        return cls(
            id=session_id,
            owner_token=owner_token,
            expires_at=expires_at,
            schedule_yaml=state["schedule_yaml"],
            revision=schedule_revision(state["schedule_yaml"]),
            queued_schedule=QueuedSchedule(**state["queued_schedule"]) if state.get("queued_schedule") else None,
            model_selection=state.get("model_selection"),
            locked_model=state.get("locked_model"),
            provider_credential_id=state.get("provider_credential_id"),
            cost_totals=CostTotals.restored(state.get("cost_totals")),
            cost_totals_version=state.get("cost_totals_version", 0),
            pending_provider_calls={
                call["id"]: ProviderCall(**call) for call in state.get("pending_provider_calls", [])
            },
            frontend_version=state.get("frontend_version"),
            frontend_timezone=state.get("frontend_timezone", "UTC"),
            export_metadata=state.get("export_metadata", {}),
            transcript=retained_entries(entries),
            uploads={upload.id: upload for upload in uploads},
            removed_upload_paths=set(removed_upload_paths),
            archive_bytes=archive_bytes,
            downloads=dict.fromkeys(state.get("downloads", [])),
            dropped_history_messages=state["dropped_history_messages"],
            dropped_entries=state["dropped_entries"],
            next_entry_seq=next_entry_seq,
            event_stream=event_stream,
            entry_log=entry_log,
        )

    def _append_entries(self, run_id: str | None, entries: Sequence[AgentMessage]) -> None:
        """Number new entries in session order and hand them to recovery storage."""
        for entry in entries:
            if self.entry_log is not None:
                self.entry_log(self.id, (self.next_entry_seq, run_id, entry))
            self.next_entry_seq += 1

    def _add_entry(self, entry: AgentMessage, run_id: str | None = None) -> None:
        """Add an app event to the conversation and save it."""
        self.transcript.append(entry)
        self._append_entries(run_id, [entry])

    def _save_run_messages(self, run_id: str | None, messages: Sequence[AgentMessage]) -> None:
        """Save the run messages that ended since the last call, as Pi saves each one on `message_end`."""
        self._append_entries(run_id, messages[self._saved_run_messages :])
        self._saved_run_messages = len(messages)

    def subscribe(self, listener: Callable[[AgentSessionEvent], None]) -> Callable[[], None]:
        """Observe public session events. HTTP serialization belongs to the caller."""
        self._listeners.append(listener)
        removed = False

        def unsubscribe() -> None:
            nonlocal removed
            if not removed:
                removed = True
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return unsubscribe

    def publish(self, event: AgentSessionEvent) -> SessionEvent | None:
        if self._events_closed:
            return
        publication = self.event_stream.publish(self.id, event) if self.event_stream is not None else None
        for listener in tuple(self._listeners):
            listener(event)
        return publication

    async def events(self, after_id: int, *, force_reset: bool = False) -> AsyncGenerator[SessionEvent | None]:
        if self._events_closed:
            return
        assert self.event_stream is not None
        async with aclosing(self.event_stream.stream(self.id, after_id, force_reset=force_reset)) as reader:
            async for event in reader:
                yield event

    def close_events(self) -> None:
        self._events_closed = True
        self._listeners.clear()
        if self.event_stream is not None:
            self.event_stream.forget_session(self.id)

    def _accepted_message(self, message_id: str) -> AcceptedMessage | None:
        """Return the newest message when it has this ID and its run has not failed to start."""
        accepted = self.accepted_messages.get(message_id) or self.latest_message
        if accepted is None or accepted.message_id != message_id:
            return None
        if accepted.run is None:
            return accepted
        ready = accepted.run.ready
        return None if ready.done() and not ready.result() else accepted

    async def select_model(
        self, prepare_runtime: Callable[[], Awaitable[SessionRuntime]], *, runtime: SessionRuntime
    ) -> dict[str, str]:
        """Save the current choice without changing any accepted run's runtime."""
        async with self._admission_lock:
            selected = await prepare_runtime()
            assert selected.selection is not None
            self.check_model(selected.selection["model"])
            previous = self.model_selection
            self.model_selection = selected.selection
            if not await _complete(runtime.recorder.save(self.id, self.provider_credential_id)):
                self.model_selection = previous
                raise HTTPException(503, "The model choice could not be saved yet. Please try again.")
            return self.model_selection

    def check_model(self, model: str) -> None:
        if self.locked_model is not None and model != self.locked_model:
            raise HTTPException(
                409, "The model is fixed for this conversation. Start a new conversation to choose another model."
            )

    async def accept_message(
        self,
        question: str,
        message_id: str | None,
        *,
        runtime: SessionRuntime,
        runs: SessionRuns,
        owner: str | None,
        credential_id: str | None,
        prepare_runtime: Callable[[], Awaitable[SessionRuntime]] | None = None,
        requested_model: str | None = None,
        compact_only: bool = False,
    ) -> MessageReceipt:
        """Start a run for a client message, or return the run that already answers it.

        A repeated message ID returns its run without calling the provider or tools again,
        even after a restart. A Stop saved before the message arrived keeps its question
        from running.

        Raises:
            HTTPException: With status 409 when the message ID belongs to another question or
                a run is active, or 503 when recovery storage is unavailable.
        """
        async with self._admission_lock:
            if message_id is not None:
                accepted = self._accepted_message(message_id)
                if accepted is not None:
                    if accepted.question != question:
                        raise HTTPException(status_code=409, detail="This message ID belongs to a different question.")
                    accepted_run = accepted.run
                    if accepted_run is None or await asyncio.shield(accepted_run.ready):
                        return MessageReceipt(accepted.run_id)
                found = None if accepted is not None else await runtime.recorder.find_message(self.id, message_id)
                if found is not None:
                    run_id, accepted_question = found
                    if accepted_question != question:
                        raise HTTPException(status_code=409, detail="This message ID belongs to a different question.")
                    return MessageReceipt(run_id)
                if await runtime.recorder.message_stopped(self.id, message_id):
                    self.stopped_message_ids.add(message_id)

            model = requested_model or (self.model_selection or {}).get("model", runtime.settings.provider_model)
            self.check_model(model)
            previous_lock = self.locked_model

            async def execute(run: AgentRun) -> None:
                selected_runtime = await prepare_runtime() if prepare_runtime is not None else runtime
                self.check_model(selected_runtime.settings.provider_model)
                if selected_runtime.selection is not None and (self.model_selection or {}).get("model") != model:
                    self.model_selection = selected_runtime.selection
                await self.run(
                    run,
                    question,
                    runtime=selected_runtime,
                    owner=owner,
                    credential_id=credential_id,
                    compact_only=compact_only,
                )

            run = runs.start(
                self.id,
                execute,
                message_id=message_id,
            )
            self.locked_model = model
            if message_id is not None:
                accepted = AcceptedMessage(message_id, question, run, run.id)
                if not runtime.recorder.enabled:
                    try:
                        runtime.store.remember_message(self.id, accepted)
                    except HTTPException:
                        run.cancel()
                        await asyncio.shield(run.done)
                        raise
                self.latest_message = accepted
        if not await asyncio.shield(run.ready):
            if previous_lock is None:
                self.locked_model = None
            if run.cancelled and not run.shutdown:
                # A Stop arrived before the run reported its start. A run cancelled before
                # it began never reaches finalization, so its stopped outcome is published here.
                if not run.begun:
                    self.publish({"type": "stopped", "run_id": run.id})
                return MessageReceipt(run.id)
            await run.wait()
        return MessageReceipt(run.id, run)

    async def stop(self, message_id: str | None, *, runtime: SessionRuntime, runs: SessionRuns) -> None:
        """Cancel the named message's run, or every run of the session.

        A named Stop is saved first, so a message that arrives later, even after a
        restart, does not run. A delayed Stop cannot cancel a later message's run.

        Raises:
            HTTPException: With status 503 when storage cannot save a named Stop.
        """
        if message_id is not None:
            await runtime.recorder.stop_message(self.id, message_id)
            self.stopped_message_ids.add(message_id)
        runs.stop(self.id, message_id)

    def publish_optimizer_update(self, update: OptimizerUpdate) -> None:
        """Project independent job updates onto the same stream as agent output."""
        if "progress" in update:
            self.publish(OptimizationProgressEvent(type="optimization_progress", **update))
        else:
            self.publish(OptimizationEvent(type="optimization", **update))

    @property
    def active(self) -> bool:
        return self.snapshot is not None

    def begin_run(self, *, run_id: str | None = None) -> RunSnapshot:
        """Reserve this conversation version and open its steering queue."""
        if self.active:
            raise HTTPException(status_code=409, detail="This chat session already has an active response.")
        self.agent.reset()
        self.agent.open_steering()
        self._saved_run_messages = 0
        self.snapshot = RunSnapshot(
            list(self.transcript),
            self.schedule_yaml,
            self.version,
            previously_dropped=self.dropped_history_messages,
            run_id=run_id,
            uploads=tuple(self.uploads.values()),
            frontend_timezone=self.frontend_timezone,
            analysis=self.analysis,
            transcript_offset=self.dropped_entries,
        )
        return self.snapshot

    def finish_run(
        self,
        snapshot: RunSnapshot,
        entries: Sequence[AgentMessage],
        schedule_yaml: str | None,
    ) -> RunCompletion:
        """Commit only the current reservation, releasing it even when its version is stale.

        A committed run's validated schedule becomes the current schedule.
        """
        if not self.abort_run(snapshot):
            return RunCompletion(False, False)
        if self.version != snapshot.version:
            return RunCompletion(False, False)
        self.transcript.extend(entries)
        self.analysis = snapshot.analysis if snapshot.analysis and snapshot.analysis.content else None
        replaced_queued_schedule = False
        if schedule_yaml is not None:
            # The run's schedule replaces an update queued during the run, as it replaces newer browser work.
            replaced_queued_schedule = self.queued_schedule is not None
            self.queued_schedule = None
            self.analysis = None
            self.schedule_yaml = schedule_yaml
            self.revision = schedule_revision(schedule_yaml)
        return RunCompletion(True, schedule_yaml is not None, replaced_queued_schedule=replaced_queued_schedule)

    def abort_run(self, snapshot: RunSnapshot) -> bool:
        """Only the owner of a reservation may release it."""
        if self.snapshot is not snapshot:
            return False
        self.snapshot = None
        self.agent.reset()
        return True

    def check_steering(self, message_id: str, max_messages: int) -> bool:
        """Check a queued message against the active run. False means a retried duplicate."""
        if not self.active or not self.agent.accepting_steering:
            raise HTTPException(status_code=409, detail="The active response is no longer accepting messages.")
        if self.agent.has_steered(message_id):
            return False
        # Counted over the whole run, not the drained queue, so retries stay idempotent.
        if self.agent.steered_count >= max_messages:
            raise HTTPException(status_code=429, detail="Too many messages are already queued.")
        return True

    def steer(self, message_id: str, text: str) -> None:
        self.agent.steer(message_id, text)

    def take_steering(self, close_if_empty: bool) -> list[tuple[str, str]]:
        """Drain queued messages, closing the queue if the answer is ending without any."""
        return self.agent.take_steering(close_if_empty) if self.active else []

    @property
    def queued_steering(self) -> tuple[str, ...]:
        return self.agent.queued_steering if self.active else ()

    def update_schedule(self, schedule_yaml: str, compared: tuple[str, bool] | None = None) -> None:
        """Replace the session schedule, invalidate in-flight results, and record the change.

        `compared` holds a base schedule and its `schedule_data_changed` result. It is reused
        only while that base is still the session schedule. During a run, keep only the latest
        update until the run ends, so a browser update never discards the run.
        """
        known_change = compared[1] if compared is not None and compared[0] == self.schedule_yaml else None
        if self.active:
            changed = schedule_yaml != self.schedule_yaml
            self.queued_schedule = QueuedSchedule(schedule_yaml, known_change) if changed else None
            return
        if self.schedule_yaml == schedule_yaml:
            return
        if known_change is not None:
            data_changed = known_change
        else:
            data_changed = schedule_data_changed(self.schedule_yaml, schedule_yaml)
        self.version += 1
        self.analysis = None
        self.schedule_yaml = schedule_yaml
        self.revision = schedule_revision(schedule_yaml)
        if data_changed:
            self._add_entry(AppEventEntry(SCHEDULE_CHANGED_EVENT))

    def apply_queued_schedule(self) -> bool:
        """Apply the schedule update received during the last run. Return whether one was applied."""
        queued = self.queued_schedule
        if queued is None or self.active:
            return False
        self.queued_schedule = None
        compared = None if queued.data_changed is None else (self.schedule_yaml, queued.data_changed)
        self.update_schedule(queued.schedule_yaml, compared)
        return True

    def require_idle(self, action: str) -> None:
        """Refuse a file change while a run may still read the session files."""
        if self.active:
            raise HTTPException(status_code=409, detail=f"Wait for the active response before {action}.")

    def add_uploads(self, uploads: Sequence[SandboxAttachment], event: str) -> None:
        """Retain uploads with their IDs assigned and record their `upload_event` once in history."""
        self.analysis = None
        self.uploads.update((upload.id, upload) for upload in uploads)
        self._add_entry(AppEventEntry(event))

    def remove_upload(self, upload_id: str) -> SandboxAttachment:
        """Drop one retained source file and record its removal in history."""
        if upload_id not in self.uploads:
            raise HTTPException(status_code=404, detail="The uploaded file is no longer available.")
        index = list(self.uploads).index(upload_id) + 1
        upload = self.uploads.pop(upload_id)
        self.analysis = None
        self.pending_upload_removals.add(upload_id)
        self.removed_upload_paths.add(attachment_path(upload, index))
        self._add_entry(AppEventEntry(removal_event(upload, index)))
        return upload

    def _prepare_run(
        self,
        snapshot: RunSnapshot,
        question: str,
        settings: AiSettings,
        events: RunEvents,
        question_kind: QuestionKind,
    ) -> tuple[list[ChatMessage], int, int]:
        """Project the reserved transcript and report the model input and its context usage."""
        history = project_history(snapshot.transcript, settings.max_history_chars)
        dropped_history = snapshot.previously_dropped + history.dropped_messages
        messages = build_provider_messages(
            history,
            snapshot.schedule_yaml,
            question,
            max_download_bytes=settings.max_download_bytes,
        )
        events.emit(
            {
                "type": "model_input",
                "schedule_yaml": snapshot.schedule_yaml,
                **model_input(
                    messages,
                    [snapshot.transcript_offset + index for index in history.source_indices],
                    question_kind,
                    app_indices={
                        snapshot.transcript_offset + index
                        for index, entry in enumerate(snapshot.transcript)
                        if isinstance(entry, AppEventEntry)
                    },
                ),
            }
        )
        events.emit({"type": "context_usage", **context_usage(history.used_chars, settings)})
        if dropped_history:
            events.emit({"type": "history_trimmed", "dropped": dropped_history})
        return messages, dropped_history, history.used_chars

    async def _report_provider_call(
        self,
        call: ProviderCall,
        runtime: SessionRuntime,
        output: RunOutput,
        events: RunEvents,
    ) -> None:
        previous = output.calls.get(call.id)
        if call == previous:
            return
        data = asdict(call)
        data["call_id"] = data.pop("id")
        publication = events.emit(
            {"type": "provider_call", **data, "reasoning": (runtime.selection or {}).get("reasoning", "default")}
        )
        try:
            saved = await runtime.recorder.save_provider_call(self.id, publication)
        finally:
            # A rejected attempt must not reappear in totals when its event is retried.
            if publication is not None:
                self.cost_totals_version = publication.id
        if not saved:
            events.emit(
                {
                    "type": "warning",
                    "message": "Provider cost details could not be saved yet. Recovery storage will retry.",
                }
            )
            if previous is None and call.status == "pending":
                # Do not incur a new provider charge without a durable attempt record.
                raise ProviderError.for_user(
                    "Cost recovery storage is unavailable, so the provider request was not started. Please try again."
                )
        output.calls[call.id] = call
        output.costs.update(call, previous)
        self.cost_totals.update(call, previous)
        if call.status == "pending":
            self.pending_provider_calls[call.id] = call
        else:
            self.pending_provider_calls.pop(call.id, None)
        events.emit(
            {
                "type": "cost_summary",
                "conversation": {**self.cost_totals.public(), "version": publication.id if publication else 0},
                "run": output.costs.public(),
            }
        )

    async def _compact_context(
        self,
        run: AgentRun,
        snapshot: RunSnapshot,
        runtime: SessionRuntime,
        output: RunOutput,
        events: RunEvents,
    ) -> None:
        """Summarize retained context without a user question or workspace."""
        settings = runtime.settings
        history = project_history(snapshot.transcript, settings.max_history_chars)
        messages = build_provider_messages(
            history, snapshot.schedule_yaml, "", max_download_bytes=settings.max_download_bytes
        )[:-1]
        async with runtime.concurrency_limit:
            compactor = ContextCompactor(
                runtime.provider,
                history_limit=settings.max_history_chars,
                message_limit=settings.max_history_messages,
            )
            await compactor.prepare()
            definitions = SandboxPiTools.tool_definitions(settings.sandbox_command_timeout_seconds)
            definitions.append(optimizer_tool_definition(settings.optimizer_default_timeout_seconds))
            summary_events = compactor.compact(messages, definitions, force=True, manual=True)
            async with aclosing(summary_events):
                async for event in summary_events:
                    if isinstance(event, ProviderCall):
                        await self._report_provider_call(event, runtime, output, events)
                        continue
                    if isinstance(event, AgentCompaction):
                        self.agent.state.messages.append(event.entry)
                        self._save_run_messages(run.id, self.agent.state.messages)
                    wire = output.consume(event)
                    if wire is not None:
                        events.emit(wire)
                    if isinstance(event, AgentCompactionEnd) and event.success:
                        events.emit(
                            {
                                "type": "context_usage",
                                **context_usage(
                                    event.used_chars,
                                    settings,
                                    provider=runtime.provider,
                                    estimated_tokens=event.estimated_tokens_after,
                                ),
                            }
                        )
        if not self.agent.state.messages:
            events.emit(
                {
                    "type": "warning",
                    "message": "Context was not compacted. The original conversation context was kept.",
                }
            )

    async def _execute_run(
        self,
        snapshot: RunSnapshot,
        messages: Sequence[ChatMessage],
        artifact: OptimizerArtifact | None,
        runtime: SessionRuntime,
        output: RunOutput,
        events: RunEvents,
        context_chars: int,
    ) -> None:
        """Execute the agent and await workspace cleanup before returning."""
        try:
            async with runtime.concurrency_limit:
                agent_events = run_workspace(
                    runtime.provider,
                    runtime.sandbox_factory,
                    snapshot.schedule_yaml,
                    messages,
                    WorkspaceLimits.from_settings(runtime.settings),
                    take_steering=lambda close: runtime.store.take_steering(self.id, close),
                    execute_optimizer=lambda current_yaml, arguments: execute_optimizer_tool(
                        runtime.session_optimizer,
                        self.id,
                        current_yaml,
                        arguments,
                        self.client_address,
                        runtime.selection,
                    ),
                    attachments=snapshot.uploads,
                    load_attachment=lambda upload: runtime.recorder.read_upload(self.id, self.owner_token, upload),
                    analysis=snapshot.analysis,
                    optimizer_result=artifact.content if artifact is not None else None,
                    optimizer_context=artifact.schedule_context if artifact is not None else None,
                    agent=self.agent,
                    timezone=snapshot.frontend_timezone,
                )
                async with aclosing(agent_events):
                    async for event in agent_events:
                        if isinstance(event, ProviderCall):
                            report = self._report_provider_call(event, runtime, output, events)
                            if event.status == "pending" and event.id not in output.calls:
                                # Stop during admission must not count an unstarted HTTP request.
                                await report
                            else:
                                # Retain received prices and totals before Stop finalizes the run.
                                await _complete(report)
                            continue
                        self._save_run_messages(snapshot.run_id, self.agent.state.messages)
                        wire_event = output.consume(event)
                        if wire_event is not None:
                            events.emit(wire_event)
                        if isinstance(event, AgentContextUsage) or (
                            isinstance(event, AgentCompactionEnd) and event.success
                        ):
                            context_chars = event.used_chars
                            events.emit(
                                {
                                    "type": "context_usage",
                                    **context_usage(
                                        context_chars,
                                        runtime.settings,
                                        provider=runtime.provider,
                                        estimated_tokens=output.context_estimate,
                                    ),
                                }
                            )
                        elif isinstance(event, TokenUsage):
                            events.emit(
                                {
                                    "type": "context_usage",
                                    **context_usage(context_chars, runtime.settings, event, runtime.provider),
                                }
                            )
        finally:
            for call in tuple(output.calls.values()):
                if call.status == "pending":
                    final = replace(call, status="reported" if call.cost_usd is not None else "unavailable")
                    await _complete(self._report_provider_call(final, runtime, output, events))

    def _commit_run(
        self,
        run: AgentRun,
        snapshot: RunSnapshot,
        entries: Sequence[AgentMessage],
        output: RunOutput,
        store: SessionPersistence,
    ) -> RunCompletion:
        # The outcome is fixed once cleanup has finished and the session commit
        # begins. Stop must not turn a committed answer into a stopped response
        # while its history write is still pending.
        run.finishing = True
        if output.analysis is not None:
            snapshot.analysis = output.analysis
        completion = store.finish(
            self.id,
            retained_entries(entries),
            output.proposal.text if output.proposal is not None else None,
            snapshot=snapshot,
        )
        return completion

    async def _publish_completion(
        self,
        run: AgentRun,
        schedule_change: dict[str, Any] | None,
        completion: RunCompletion,
        output: RunOutput,
        events: RunEvents,
        runtime: SessionRuntime,
        dropped_history: int,
        history_saved: bool | None,
        background: bool,
    ) -> None:
        """Publish the committed result after its history write finishes."""
        if not completion.run_saved:
            events.emit({"type": "stale", "message": STALE_RUN_ERROR})
            return
        if completion.history_trimmed_count and completion.history_trimmed_count != dropped_history:
            events.emit({"type": "history_trimmed", "dropped": completion.history_trimmed_count})
        if schedule_change is not None:
            events.emit(schedule_change)
        if output.download is not None:
            # A ZIP that does not fit the session memory budget leaves the answer intact.
            if runtime.store.save_download(self.id, run.id, output.download.content):
                saved = await runtime.recorder.save(self.id)
                events.emit({"type": "download", "download_id": run.id})
                if not saved:
                    events.emit({"type": "warning", "message": RECOVERY_SAVE_WARNING})
            else:
                events.emit({"type": "warning", "message": DOWNLOAD_RETENTION_WARNING})
        done: RunDoneEvent = {"type": "done"}
        if history_saved is not None and not background:
            done["history_saved"] = history_saved
        events.emit(
            {
                "type": "context_usage",
                **context_usage(
                    completion.context_used_chars,
                    runtime.settings,
                    output.last_call,
                    runtime.provider,
                    estimated_tokens=output.context_estimate,
                ),
            }
        )
        events.emit(done)

    async def _finalize_run(
        self,
        run: AgentRun,
        snapshot: RunSnapshot,
        entries: Sequence[AgentMessage],
        output: RunOutput,
        outcome: RunOutcome,
        events: RunEvents,
        runtime: SessionRuntime,
        history_started: bool,
        dropped_history: int,
        background: bool,
        compact_only: bool = False,
    ) -> None:
        """Resolve the transcript, save the run record once, then publish the terminal outcome."""
        run.finishing = True
        stopped = outcome.terminal is not None and outcome.terminal["type"] == "stopped"
        committed = outcome.status == "completed"
        if outcome.completion is not None:
            final = next((entry for entry in reversed(entries) if isinstance(entry, AssistantMessage)), None)
            if final is not None:
                events.emit({"type": "response_end", "stop_reason": final.stop_reason})
        if outcome.completion is None and compact_only:
            runtime.store.abort(self.id, snapshot)
        elif outcome.completion is None:
            stop_reason = "aborted" if outcome.status == "cancelled" else "error"
            entries = output.interrupted_entries([entries[0], *self.agent.state.messages], stop_reason)
            completed_tools = {id(entry) for entry in self.agent.state.messages if isinstance(entry, ToolResultMessage)}
            calls = {
                call.id: call for entry in entries if isinstance(entry, AssistantMessage) for call in entry.tool_calls
            }
            for entry in entries:
                if isinstance(entry, ToolResultMessage) and id(entry) not in completed_tools:
                    events.emit(
                        {
                            "type": "tool",
                            "tool_call_id": entry.tool_call_id,
                            "name": entry.tool_name,
                            "arguments": calls[entry.tool_call_id].arguments,
                            "result": entry.text,
                            "ok": False,
                        }
                    )
            history_unavailable = runtime.recorder.enabled and not history_started
            if not run.shutdown and not history_unavailable and outcome.status in {"cancelled", "failed"}:
                # Keep the prompt so a follow-up can refer to it. Workspace changes were
                # discarded with the sandbox, which context.py accounts for.
                committed = runtime.store.finish(self.id, retained_entries(entries), snapshot=snapshot).run_saved
            else:
                runtime.store.abort(self.id, snapshot)
            events.emit(
                {
                    "type": "response_end",
                    "stop_reason": stop_reason,
                    **({"context_note": entries[-1].text} if committed else {}),
                }
            )
        if history_started:
            # Messages the run loop has not saved yet, including an interrupted response.
            self._save_run_messages(run.id, entries if compact_only else entries[1:])
        # A schedule update received during the run is recorded after the run's own entries.
        runtime.store.apply_queued_schedule(self.id)
        if stopped and run.shutdown:
            # The run stays running in recovery storage, so the restarted service reports
            # a restart instead of a user Stop.
            events.finish()
            return
        if output.compaction is not None:
            event = output.consume(
                AgentCompactionEnd(output.compaction.reason, False, output.compaction.tokens_before, aborted=stopped)
            )
            events.emit(event)
        if outcome.terminal is not None:
            events.emit(outcome.terminal)
        try:
            history_saved = None
            schedule_change = None
            if outcome.completion is not None and outcome.completion.schedule_applied and output.proposal is not None:
                schedule_change = {
                    "type": "schedule_applied",
                    "run_id": run.id,
                    "schedule_yaml": output.proposal.text,
                    "diff": output.proposal.diff,
                    "replaced_queued_schedule": outcome.completion.replaced_queued_schedule,
                }
            if history_started:
                history_saved = await _complete(
                    runtime.recorder.finish_run(
                        self.id,
                        run.id,
                        outcome.status,
                        outcome.error_code,
                        output.usage,
                        committed,
                        schedule_change=schedule_change,
                    )
                )
                if not history_saved:
                    events.emit({"type": "warning", "message": RECOVERY_SAVE_WARNING})
            if outcome.completion is not None:
                await self._publish_completion(
                    run,
                    schedule_change,
                    outcome.completion,
                    output,
                    events,
                    runtime,
                    dropped_history,
                    history_saved,
                    background,
                )
        finally:
            events.finish()

    async def run(
        self,
        run: AgentRun,
        question: str,
        *,
        runtime: SessionRuntime,
        background: bool = False,
        compact_only: bool = False,
        owner: str | None = None,
        credential_id: str | None = None,
        artifact: OptimizerArtifact | None = None,
        prepare_runtime: Callable[[], Awaitable[SessionRuntime]] | None = None,
    ) -> None:
        """Own every run phase and finalize once, regardless of trigger or transport."""
        run.begun = True
        session_id = self.id
        settings, store, recorder = runtime.settings, runtime.store, runtime.recorder
        snapshot = (
            store.begin_background(session_id, run_id=run.id)
            if background
            else store.begin(session_id, owner, run_id=run.id)
        )
        if snapshot is None:
            return
        if compact_only:
            self.agent.close_steering()
        # History keeps the question as typed. Upload and removal events are separate history entries.
        output = RunOutput()
        run_entries: list[AgentMessage] = [] if compact_only else [UserMessage(question)]
        history_started = False
        outcome = RunOutcome()
        dropped_history = 0
        events = RunEvents(run.id, self.publish)

        try:
            preparation_error = None
            if prepare_runtime is not None:
                try:
                    runtime = await prepare_runtime()
                    settings = runtime.settings
                except HTTPException as exc:
                    # Record the failed review before publishing its terminal error.
                    preparation_error = ProviderError.for_user(str(exc.detail))
            bind_session = getattr(runtime.provider, "with_session_id", None)
            if preparation_error is None:
                self.check_model(runtime.settings.provider_model)
                self.locked_model = runtime.settings.provider_model
            if bind_session is not None:
                runtime = replace(runtime, provider=bind_session(session_id))
            if recorder.enabled:
                prompt_seq = self.next_entry_seq
                if not compact_only:
                    self.next_entry_seq += 1
                start = asyncio.ensure_future(
                    recorder.start_run(
                        session_id,
                        run.id,
                        None if compact_only else question,
                        prompt_seq,
                        model=(runtime.selection or {}).get("model", settings.provider_model),
                        attachment_count=len(snapshot.uploads),
                        kind="compaction" if compact_only else "background" if background else "foreground",
                        message_id=run.message_id,
                        credential_id=credential_id,
                    )
                )
                try:
                    history_started = await _complete(start)
                except asyncio.CancelledError:
                    # Cancellation during start still waits for the run record. Its
                    # messages and outcome are saved only after a saved record.
                    history_started = start.result()
                    raise
                if not history_started:
                    raise HTTPException(status_code=503, detail=RECOVERY_UNAVAILABLE)
            events.emit(
                {
                    "type": "run_start",
                    "trigger": "compaction" if compact_only else "optimizer" if background else "user",
                }
            )
            run.ready.set_result(True)
            if preparation_error is not None:
                raise preparation_error
            if run.message_id is not None and run.message_id in self.stopped_message_ids:
                # A Stop for this message arrived first, so its question never runs.
                outcome = RunOutcome(terminal={"type": "stopped"})
                return
            if compact_only:
                await self._compact_context(run, snapshot, runtime, output, events)
                run_entries = list(self.agent.state.messages)
            else:
                if not background:
                    artifact = await runtime.session_optimizer.latest_result_artifact(session_id)
                messages, dropped_history, context_chars = self._prepare_run(
                    snapshot,
                    question,
                    settings,
                    events,
                    "optimizer" if background else "question",
                )
                if runtime.selection is not None:
                    events.emit({"type": "model_selection", **runtime.selection})
                await self._execute_run(snapshot, messages, artifact, runtime, output, events, context_chars)
                run_entries = [run_entries[0], *self.agent.state.messages]
            completion = self._commit_run(run, snapshot, run_entries, output, store)
            outcome = RunOutcome("completed" if completion.run_saved else "stale", completion=completion)
        except asyncio.CancelledError:
            outcome = RunOutcome(terminal={"type": "stopped"})
            raise
        except HTTPException:
            if not background:
                raise
            outcome = RunOutcome(
                "failed",
                error_code="history_unavailable",
                terminal={"type": "error", "message": BACKGROUND_RECOVERY_ERROR},
            )
        except (ProviderError, SandboxError) as exc:
            if isinstance(exc, ProviderError):
                error_code, message = "provider_error", exc.user_message or PROVIDER_ERROR
            elif isinstance(exc, SandboxDownloadError):
                error_code, message = "download_error", str(exc)
            elif isinstance(exc, SandboxAttachmentUnavailableError):
                error_code, message = "attachment_unavailable", str(exc)
            elif isinstance(exc, SandboxCommandTimeoutError):
                error_code, message = "sandbox_command_timeout", SANDBOX_COMMAND_TIMEOUT_ERROR
            elif isinstance(exc, SandboxTurnTimeoutError):
                error_code, message = "sandbox_timeout", SANDBOX_RUN_TIMEOUT_ERROR
            elif isinstance(exc, SandboxCandidateError):
                error_code = "candidate_validation"
                message = CANDIDATE_VALIDATION_ERROR + (f"\n\n{exc.user_message}" if exc.user_message else "")
            else:
                error_code, message = "sandbox_error", "The temporary AI sandbox failed. Please try again."
                logger.exception("AI sandbox run failed session_id=%s", session_id)
            outcome = RunOutcome("failed", error_code=error_code, terminal={"type": "error", "message": message})
        except Exception:
            logger.exception("Unexpected AI run failure session_id=%s", session_id)
            outcome = RunOutcome(
                "failed",
                error_code="internal_error",
                terminal={"type": "error", "message": "The AI response failed unexpectedly."},
            )
        finally:
            try:
                await self._finalize_run(
                    run,
                    snapshot,
                    run_entries,
                    output,
                    outcome,
                    events,
                    runtime,
                    history_started,
                    dropped_history,
                    background,
                    compact_only,
                )
            finally:
                self.agent.reset()

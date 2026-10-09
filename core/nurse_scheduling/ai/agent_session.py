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
import time
from collections.abc import AsyncGenerator, Awaitable, Callable, Sequence
from contextlib import aclosing
from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Protocol, TypeVar

from fastapi import HTTPException
from ruamel.yaml.error import YAMLError

from ..loader import _load_yaml
from .agent import Agent
from .candidate import PendingProposal
from .config import AiSettings
from .context import (
    SCHEDULE_CHANGED_DISCARDED_EVENT,
    SCHEDULE_CHANGED_EVENT,
    build_provider_messages,
    context_usage,
    model_input,
    project_history,
    removal_event,
    retained_entries,
)
from .history import RECOVERY_UNAVAILABLE, EntryRow, RunKind, RunStatus
from .lifecycle import AgentRun, RunSnapshot, SessionRuns
from .optimizer import OptimizerArtifact, SessionOptimizer
from .optimizer_tool import execute_optimizer_tool
from .provider import ChatMessage, ProviderError, TokenUsage, ToolCapableChatProvider
from .sandbox import SandboxError, SandboxFactory
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
    ProposalDecision,
    ProposalDecisionEntry,
    UserMessage,
)
from .validation import new_schedule_issues, validate_frontend_schedule_yaml
from .workspace import (
    SandboxAttachment,
    SandboxCandidateError,
    SandboxCommandTimeoutError,
    SandboxDownloadError,
    SandboxTurnTimeoutError,
    WorkspaceLimits,
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
DOWNLOAD_RETENTION_WARNING = "The generated ZIP could not be retained because the service memory limit was reached."
SANDBOX_RUN_TIMEOUT_ERROR = "The AI response timed out. Please try again."
STALE_RUN_ERROR = "The schedule changed while this response was generated, so the response was discarded."
BACKGROUND_RECOVERY_ERROR = "AI message recovery is unavailable, so the optimizer result was not reviewed."
RECOVERY_SAVE_WARNING = "This response could not be saved for recovery after a service restart."
logger = logging.getLogger("nurse_scheduling.ai")
_Result = TypeVar("_Result")


def schedule_revision(schedule_yaml: str) -> str:
    """Identify one exact schedule snapshot, so a stale proposal cannot be applied."""
    return hashlib.sha256(schedule_yaml.encode("utf-8")).hexdigest()


def _schedule_data(schedule_yaml: str) -> object:
    """Parse a schedule for comparison, so a formatting-only change is not reported as an edit."""
    try:
        return _load_yaml(schedule_yaml.encode(), reject_aliases=True)
    except (ValueError, YAMLError):
        return schedule_yaml


@dataclass(frozen=True)
class RunCompletion:
    """Whether a completed run and its optional proposal were retained."""

    run_saved: bool
    proposal_saved: bool
    history_trimmed_count: int = 0
    context_used_chars: int = 0


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
        proposal: tuple[str, str] | None = None,
        *,
        snapshot: RunSnapshot,
    ) -> RunCompletion: ...

    def abort(self, session_id: str, snapshot: RunSnapshot) -> None: ...

    def save_download(self, session_id: str, download_id: str, content: bytes) -> bool: ...


class RunRecorder(Protocol):
    """Run records, Stop requests, and session state saved for restart recovery."""

    @property
    def enabled(self) -> bool: ...

    async def find_message(self, session_id: str, message_id: str) -> tuple[str, str] | None: ...

    async def message_stopped(self, session_id: str, message_id: str) -> bool: ...

    async def stop_message(self, session_id: str, message_id: str) -> None: ...

    async def start_run(
        self,
        session_id: str,
        run_id: str,
        prompt: str,
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
    agent: Agent = field(default_factory=Agent)
    pending_proposal: PendingProposal | None = None
    # Retained source files keyed by upload ID, in upload order, and generated ZIPs keyed by run ID.
    uploads: dict[str, SandboxAttachment] = field(default_factory=dict)
    downloads: dict[str, bytes] = field(default_factory=dict)
    # Last owner access, which orders eviction. A restored session keeps its stored expiry.
    last_used: float = field(default_factory=time.monotonic)
    latest_message: AcceptedMessage | None = None
    accepted_messages: dict[str, AcceptedMessage] = field(default_factory=dict)
    # Named Stop requests, including those for messages that have not arrived yet.
    stopped_message_ids: set[str] = field(default_factory=set)
    event_stream: SessionEventStream | None = field(default=None, repr=False)
    # Recovery storage, which receives each new entry as Pi's SessionManager does.
    entry_log: Callable[[str, EntryRow], None] | None = field(default=None, repr=False)
    _saved_run_messages: int = field(default=0, repr=False)
    _listeners: list[Callable[[AgentSessionEvent], None]] = field(default_factory=list, repr=False)
    _events_closed: bool = False

    @property
    def history(self) -> list[ChatMessage]:
        """Render the retained transcript for callers that inspect conversation text."""
        from .context import projected_history

        return projected_history(self.transcript)

    def recovery_state(self) -> dict[str, Any]:
        """Return the schedule, proposal, and retention counts that a restored session continues.

        The conversation itself is rebuilt from saved entries.
        """
        return {
            "schedule_yaml": self.schedule_yaml,
            "pending_proposal": None if self.pending_proposal is None else asdict(self.pending_proposal),
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
        event_stream: SessionEventStream | None,
        entry_log: Callable[[str, EntryRow], None] | None,
    ) -> "AgentSession":
        """Rebuild a session from `recovery_state` and its saved conversation entries.

        Uploads, downloads, and optimizer results are not saved.
        """
        proposal = state["pending_proposal"]
        return cls(
            id=session_id,
            owner_token=owner_token,
            expires_at=expires_at,
            schedule_yaml=state["schedule_yaml"],
            revision=schedule_revision(state["schedule_yaml"]),
            transcript=retained_entries(entries),
            dropped_history_messages=state["dropped_history_messages"],
            dropped_entries=state["dropped_entries"],
            next_entry_seq=next_entry_seq,
            pending_proposal=None if proposal is None else PendingProposal(**proposal),
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
        """Add an app event or proposal decision to the conversation and save it."""
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

    def publish(self, event: AgentSessionEvent) -> None:
        if self._events_closed:
            return
        if self.event_stream is not None:
            self.event_stream.publish(self.id, event)
        for listener in tuple(self._listeners):
            listener(event)

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

    async def accept_message(
        self,
        question: str,
        message_id: str | None,
        *,
        runtime: SessionRuntime,
        runs: SessionRuns,
        owner: str | None,
        credential_id: str | None,
    ) -> MessageReceipt:
        """Start a run for a client message, or return the run that already answers it.

        A repeated message ID returns its run without calling the provider or tools again,
        even after a restart. A Stop saved before the message arrived keeps its question
        from running.

        Raises:
            HTTPException: With status 409 when the message ID belongs to another question or
                a run is active, or 503 when recovery storage is unavailable.
        """
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
        run = runs.start(
            self.id,
            lambda run: self.run(run, question, runtime=runtime, owner=owner, credential_id=credential_id),
            message_id=message_id,
        )
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

    def begin_run(self, *, accepting_steering: bool, run_id: str | None = None) -> RunSnapshot:
        """Reserve this conversation version and open its steering queue."""
        if self.active:
            raise HTTPException(status_code=409, detail="This chat session already has an active response.")
        self.agent.reset()
        self.agent.open_steering(accepting_steering)
        self._saved_run_messages = 0
        self.snapshot = RunSnapshot(
            list(self.transcript),
            self.schedule_yaml,
            self.version,
            self.pending_proposal,
            previously_dropped=self.dropped_history_messages,
            run_id=run_id,
            uploads=tuple(self.uploads.values()),
        )
        return self.snapshot

    def finish_run(
        self,
        snapshot: RunSnapshot,
        entries: Sequence[AgentMessage],
        proposal: tuple[str, str] | None,
    ) -> RunCompletion:
        """Commit only the current reservation, releasing it even when its version is stale."""
        if not self.abort_run(snapshot):
            return RunCompletion(False, False)
        if self.version != snapshot.version:
            return RunCompletion(False, False)
        self.transcript.extend(entries)
        if proposal is not None:
            self.pending_proposal = PendingProposal(proposal[0], proposal[1], snapshot.run_id)
        return RunCompletion(True, proposal is not None)

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

    def update_schedule(self, schedule_yaml: str) -> None:
        """Replace the session schedule, invalidate proposals and in-flight results, and record the change."""
        if self.schedule_yaml == schedule_yaml:
            return
        data_changed = _schedule_data(self.schedule_yaml) != _schedule_data(schedule_yaml)
        had_proposal = self.pending_proposal is not None
        self.version += 1
        self.schedule_yaml = schedule_yaml
        self.revision = schedule_revision(schedule_yaml)
        self.pending_proposal = None
        if data_changed or had_proposal:
            self._add_entry(AppEventEntry(SCHEDULE_CHANGED_DISCARDED_EVENT if had_proposal else SCHEDULE_CHANGED_EVENT))

    def require_idle(self, action: str) -> None:
        """Refuse a file change while a run may still read the session files."""
        if self.active:
            raise HTTPException(status_code=409, detail=f"Wait for the active response before {action}.")

    def add_uploads(self, uploads: Sequence[SandboxAttachment], event: str) -> None:
        """Retain uploads with their IDs assigned and record their `upload_event` once in history."""
        self.uploads.update((upload.id, upload) for upload in uploads)
        self._add_entry(AppEventEntry(event))

    def remove_upload(self, upload_id: str) -> SandboxAttachment:
        """Drop one retained source file and record its removal in history."""
        if upload_id not in self.uploads:
            raise HTTPException(status_code=404, detail="The uploaded file is no longer available.")
        index = list(self.uploads).index(upload_id) + 1
        upload = self.uploads.pop(upload_id)
        self._add_entry(AppEventEntry(removal_event(upload, index)))
        return upload

    def require_proposal(self, base_sha256: str) -> PendingProposal:
        """Reject a missing or stale proposal before it can be applied."""
        if self.pending_proposal is None:
            raise HTTPException(status_code=404, detail="No proposal is waiting for approval.")
        if self.revision != base_sha256:
            self.version += 1
            self.pending_proposal = None
            raise HTTPException(
                status_code=409,
                detail="The schedule changed after this proposal was created, so it was discarded.",
            )
        return self.pending_proposal

    def approve_proposal(self, base_sha256: str, max_schedule_bytes: int) -> str | None:
        """Revalidate, then adopt or discard the proposal in one synchronous operation.

        Returns the adopted schedule, or None when trusted validation refused the proposal.
        """
        proposal = self.require_proposal(base_sha256)
        approved = proposal.schedule_yaml
        # Revalidate before adopting, so a refused proposal never becomes the
        # session schedule that later runs are hydrated from.
        validation = validate_frontend_schedule_yaml(approved, max_schedule_bytes)
        if not validation.valid:
            # A user can approve while their schedule is still incomplete, so only
            # a problem this proposal introduces blocks it.
            replaced_validation = validate_frontend_schedule_yaml(self.schedule_yaml, max_schedule_bytes)
            if new_schedule_issues(replaced_validation, validation):
                logger.error("Approved proposal failed revalidation session_id=%s", self.id)
                self.discard_proposal("invalid")
                return None
        self.pending_proposal = None
        self.version += 1
        self.schedule_yaml = approved
        self.revision = schedule_revision(approved)
        self._add_entry(ProposalDecisionEntry("approved"), proposal.run_id)
        return approved

    def discard_proposal(self, decision: ProposalDecision = "rejected") -> None:
        """Record a proposal decision once under the proposing run and invalidate results based on it."""
        proposal = self.pending_proposal
        if proposal is None:
            return
        self.pending_proposal = None
        self.version += 1
        self._add_entry(ProposalDecisionEntry(decision), proposal.run_id)

    def _prepare_run(
        self,
        snapshot: RunSnapshot,
        question: str,
        artifact: OptimizerArtifact | None,
        settings: AiSettings,
        events: RunEvents,
        background: bool,
    ) -> tuple[list[ChatMessage], int, int]:
        """Project the reserved transcript and report the model input and its context usage."""
        history = project_history(snapshot.transcript, settings.max_history_chars)
        dropped_history = snapshot.previously_dropped + history.dropped_messages
        messages = build_provider_messages(
            history,
            snapshot.schedule_yaml,
            question,
            snapshot.uploads,
            pending_proposal=snapshot.pending_proposal is not None,
            optimizer_result_available=artifact is not None,
            max_download_bytes=settings.max_download_bytes,
        )
        events.emit(
            {
                "type": "model_input",
                **model_input(
                    messages, len(history.messages), dropped_history, "optimizer" if background else "question"
                ),
            }
        )
        events.emit({"type": "context_usage", **context_usage(history.used_chars, settings)})
        if dropped_history:
            events.emit({"type": "history_trimmed", "dropped": dropped_history})
        return messages, dropped_history, history.used_chars

    async def _execute_run(
        self,
        snapshot: RunSnapshot,
        messages: Sequence[ChatMessage],
        artifact: OptimizerArtifact | None,
        runtime: SessionRuntime,
        background: bool,
        output: RunOutput,
        events: RunEvents,
        context_chars: int,
    ) -> None:
        """Execute the agent and await workspace cleanup before returning."""
        async with runtime.concurrency_limit:
            agent_events = run_workspace(
                runtime.provider,
                runtime.sandbox_factory,
                snapshot.schedule_yaml,
                messages,
                WorkspaceLimits.from_settings(runtime.settings),
                take_steering=None if background else lambda close: runtime.store.take_steering(self.id, close),
                execute_optimizer=lambda current_yaml, arguments: execute_optimizer_tool(
                    runtime.session_optimizer, self.id, current_yaml, arguments
                ),
                pending_proposal_yaml=snapshot.pending_proposal.schedule_yaml if snapshot.pending_proposal else "",
                pending_proposal_diff=snapshot.pending_proposal.diff if snapshot.pending_proposal else "",
                attachments=snapshot.uploads,
                optimizer_result=artifact.content if artifact is not None else None,
                optimizer_context=artifact.schedule_context if artifact is not None else None,
                agent=self.agent,
            )
            async with aclosing(agent_events):
                async for event in agent_events:
                    self._save_run_messages(snapshot.run_id, self.agent.state.messages)
                    wire_event = output.consume(event)
                    if wire_event is not None:
                        events.emit(wire_event)
                    elif isinstance(event, TokenUsage):
                        events.emit(
                            {
                                "type": "context_usage",
                                **context_usage(context_chars, runtime.settings, event, runtime.provider),
                            }
                        )

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
        completion = store.finish(
            self.id,
            retained_entries(entries),
            (output.proposal.text, output.proposal.diff) if output.proposal is not None else None,
            snapshot=snapshot,
        )
        return completion

    def _publish_completion(
        self,
        run: AgentRun,
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
        if completion.proposal_saved and output.proposal is not None:
            events.emit({"type": "proposal", "diff": output.proposal.diff})
        if output.download is not None:
            # A ZIP that does not fit the session memory budget leaves the answer intact.
            if runtime.store.save_download(self.id, run.id, output.download.content):
                events.emit({"type": "download", "download_id": run.id})
            else:
                events.emit({"type": "warning", "message": DOWNLOAD_RETENTION_WARNING})
        done: RunDoneEvent = {"type": "done"}
        if history_saved is not None and not background:
            done["history_saved"] = history_saved
        events.emit(
            {
                "type": "context_usage",
                **context_usage(completion.context_used_chars, runtime.settings, output.last_call, runtime.provider),
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
    ) -> None:
        """Resolve the transcript, save the run record once, then publish the terminal outcome."""
        run.finishing = True
        stopped = outcome.terminal is not None and outcome.terminal["type"] == "stopped"
        committed = outcome.status == "completed"
        if outcome.completion is None:
            stop_reason = "aborted" if outcome.status == "cancelled" else "error"
            entries = output.interrupted_entries([entries[0], *self.agent.state.messages], stop_reason)
            if not run.shutdown and outcome.status in {"cancelled", "failed"}:
                # Keep the prompt so a follow-up can refer to it. Workspace changes and any
                # proposal were discarded with the sandbox, which context.py accounts for.
                committed = runtime.store.finish(self.id, retained_entries(entries), snapshot=snapshot).run_saved
            else:
                runtime.store.abort(self.id, snapshot)
        if history_started:
            # Messages the run loop has not saved yet, including an interrupted response.
            self._save_run_messages(run.id, entries[1:])
        if stopped and run.shutdown:
            # The run stays running in recovery storage, so the restarted service reports
            # a restart instead of a user Stop.
            events.finish()
            return
        if outcome.terminal is not None:
            events.emit(outcome.terminal)
        try:
            history_saved = None
            if history_started:
                history_saved = await _complete(
                    runtime.recorder.finish_run(
                        self.id, run.id, outcome.status, outcome.error_code, output.usage, committed
                    )
                )
                if not history_saved:
                    events.emit({"type": "warning", "message": RECOVERY_SAVE_WARNING})
            if outcome.completion is not None:
                self._publish_completion(
                    run, outcome.completion, output, events, runtime, dropped_history, history_saved, background
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
        owner: str | None = None,
        credential_id: str | None = None,
        artifact: OptimizerArtifact | None = None,
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
        # History keeps the question as typed. Upload and removal events are separate history entries.
        output = RunOutput()
        run_entries: list[AgentMessage] = [UserMessage(question)]
        history_started = False
        outcome = RunOutcome()
        dropped_history = 0
        events = RunEvents(run.id, self.publish)

        try:
            if recorder.enabled:
                prompt_seq = self.next_entry_seq
                self.next_entry_seq += 1
                start = asyncio.ensure_future(
                    recorder.start_run(
                        session_id,
                        run.id,
                        question,
                        prompt_seq,
                        model=settings.provider_model,
                        attachment_count=len(snapshot.uploads),
                        kind="background" if background else "foreground",
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
            events.emit({"type": "run_start", "trigger": "optimizer" if background else "user"})
            run.ready.set_result(True)
            if run.message_id is not None and run.message_id in self.stopped_message_ids:
                # A Stop for this message arrived first, so its question never runs.
                outcome = RunOutcome(terminal={"type": "stopped"})
                return
            if not background:
                artifact = await runtime.session_optimizer.latest_result_artifact(session_id)
            messages, dropped_history, context_chars = self._prepare_run(
                snapshot, question, artifact, settings, events, background
            )
            await self._execute_run(snapshot, messages, artifact, runtime, background, output, events, context_chars)
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
                )
            finally:
                self.agent.reset()

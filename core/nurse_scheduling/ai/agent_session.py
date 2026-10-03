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
import json
import logging
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import aclosing
from dataclasses import dataclass, field
from typing import Literal, Protocol

from fastapi import HTTPException

from .agent import Agent
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
from .config import AiSettings
from .context import build_provider_messages, history_context_chars, projected_history, recent_history, retained_entries
from .history import ChatHistory
from .lifecycle import TERMINAL_EVENTS, AgentRun, RunSnapshot, SessionRuns
from .optimizer import OptimizerArtifact, SessionOptimizer
from .provider import ChatMessage, ProviderError, TokenUsage, ToolCapableChatProvider
from .sandbox import SandboxError, SandboxFactory
from .session_event_stream import SessionEvent, SessionEventStream
from .transcript import (
    AgentMessage,
    AssistantMessage,
    ProposalDecision,
    ProposalDecisionEntry,
    UserMessage,
)
from .workspace import (
    AgentScheduleChange,
    SandboxAttachment,
    SandboxCandidateError,
    SandboxRunTimeoutError,
    WorkspaceLimits,
)
from .workspace_tools import run_workspace

CANDIDATE_VALIDATION_ERROR = (
    "The candidate schedule failed trusted validation. All schedule changes made during this agent run were "
    "discarded. The current schedule was not changed."
)
PROVIDER_ERROR = "The AI provider failed. Please try again."
SANDBOX_RUN_TIMEOUT_ERROR = "The AI response timed out. Please try again."
STALE_RUN_ERROR = "The schedule changed while this response was generated, so the response was discarded."
logger = logging.getLogger("nurse_scheduling.ai")


def schedule_revision(schedule_yaml: str) -> str:
    """Identify one exact schedule snapshot, so a stale proposal cannot be applied."""
    return hashlib.sha256(schedule_yaml.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RunCompletion:
    """Whether a completed run and its optional proposal were retained."""

    run_saved: bool
    proposal_saved: bool
    history_trimmed_count: int = 0
    context_used_chars: int = 0


class SessionPersistence(Protocol):
    """Session operations needed by a foreground or background run."""

    def begin(self, session_id: str, owner_token: str | None, *, run_id: str | None = None) -> RunSnapshot: ...

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


@dataclass(frozen=True)
class SessionRuntime:
    """Shared service dependencies for foreground and optimizer-triggered runs."""

    settings: AiSettings
    store: SessionPersistence
    concurrency_limit: asyncio.Semaphore
    history_log: ChatHistory | None
    provider: ToolCapableChatProvider
    sandbox_factory: SandboxFactory
    session_optimizer: SessionOptimizer


@dataclass
class RunOutput:
    """Project agent events onto the SSE contract and track interrupted output."""

    assistant_parts: list[str] = field(default_factory=list)
    # Output of the model response in progress, which only an interruption can leave open.
    pending_text: list[str] = field(default_factory=list)
    pending_reasoning: list[str] = field(default_factory=list)
    proposal: AgentProposal | None = None
    usage: TokenUsage | None = None

    @property
    def text(self) -> str:
        return "".join(self.assistant_parts)

    def interrupted_entries(
        self, entries: Sequence[AgentMessage], stop_reason: Literal["aborted", "error"]
    ) -> list[AgentMessage]:
        """End the run with Pi's interrupted assistant message, holding any partial response."""
        interrupted = AssistantMessage("".join(self.pending_text), stop_reason, "".join(self.pending_reasoning))
        return [*entries, interrupted]

    def consume(self, event: AgentEvent | AgentScheduleChange) -> tuple[str, dict[str, object]] | None:
        if isinstance(event, MessageTextDelta):
            self.assistant_parts.append(event.text)
            self.pending_text.append(event.text)
            return "delta", {"text": event.text}
        if isinstance(event, MessageReasoningDelta):
            self.pending_reasoning.append(event.text)
            return "reasoning", {"text": event.text}
        if isinstance(event, MessageEnd):
            self.pending_text.clear()
            self.pending_reasoning.clear()
            return ("truncated", {}) if event.message.stop_reason == "length" else None
        if isinstance(event, TokenUsage):
            self.usage = event if self.usage is None else self.usage + event
        elif isinstance(event, ToolExecutionStart):
            return "tool_start", {"tool_call_id": event.tool_call_id, "name": event.name, "arguments": event.arguments}
        elif isinstance(event, ToolExecutionEnd):
            return "tool", {
                "tool_call_id": event.tool_call_id,
                "name": event.name,
                "arguments": event.arguments,
                "result": event.result,
                "ok": event.ok,
            }
        elif isinstance(event, AgentSteering):
            return "steering", {"message_id": event.message_id, "message": event.text}
        elif isinstance(event, AgentScheduleChange):
            return "schedule_change", {"schedule_yaml": event.schedule_yaml}
        elif isinstance(event, AgentProposal):
            self.proposal = event
        return None


class _RunEvents:
    """Batch text for one run and defer its terminal event until finalization."""

    def __init__(self, run_id: str, publish: Callable[[str, dict[str, object]], None]) -> None:
        self.run_id = run_id
        self._publish = publish
        self._pending: tuple[str, dict[str, object]] | None = None
        self._timer: asyncio.TimerHandle | None = None
        self._terminal: tuple[str, dict[str, object]] | None = None

    def flush(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        if self._pending is not None:
            self._publish(*self._pending)
            self._pending = None

    def emit(self, event_type: str, data: dict[str, object]) -> None:
        # Every replayable fragment identifies its run, even after run_start expires.
        data = {**data, "run_id": self.run_id}
        if event_type in TERMINAL_EVENTS:
            self._terminal = event_type, data
        elif event_type in {"delta", "reasoning"}:
            # Batch tiny provider fragments before the stream assigns publication IDs.
            if self._pending is not None and self._pending[0] != event_type:
                self.flush()
            text = str(self._pending[1]["text"]) if self._pending is not None else ""
            self._pending = event_type, {**data, "text": text + str(data["text"])}
            if len(str(self._pending[1]["text"])) >= 2048:
                self.flush()
            elif self._timer is None:
                self._timer = asyncio.get_running_loop().call_later(0.025, self.flush)
        else:
            self.flush()
            self._publish(event_type, data)

    def finish(self) -> None:
        self.flush()
        if self._terminal is not None:
            self._publish(*self._terminal)
            self._terminal = None


async def _write_history(history: ChatHistory, operation: str, *args) -> bool:
    # asyncio cancellation and ASGI cancel scopes both wait for the history write.
    task = asyncio.create_task(history.write(operation, *args))
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
    version: int = 0
    snapshot: RunSnapshot | None = None
    agent: Agent = field(default_factory=Agent)
    proposal_yaml: str = ""
    proposal_diff: str = ""
    # The run that produced the pending proposal, so its decision joins that run's history.
    proposal_run_id: str | None = None
    event_stream: SessionEventStream | None = field(default=None, repr=False)
    _listeners: list[Callable[[str, dict[str, object]], None]] = field(default_factory=list, repr=False)
    _events_closed: bool = False

    def subscribe(self, listener: Callable[[str, dict[str, object]], None]) -> Callable[[], None]:
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

    def publish(self, event_type: str, data: dict[str, object]) -> None:
        if self._events_closed:
            return
        if self.event_stream is not None:
            self.event_stream.publish(self.id, event_type, data)
        for listener in tuple(self._listeners):
            listener(event_type, data)

    async def events(self, after_id: int) -> AsyncIterator[SessionEvent | None]:
        if self._events_closed:
            return
        assert self.event_stream is not None
        async with aclosing(self.event_stream.stream(self.id, after_id)) as reader:
            async for event in reader:
                yield event

    def close_events(self) -> None:
        self._events_closed = True
        self._listeners.clear()
        if self.event_stream is not None:
            self.event_stream.forget_session(self.id)

    async def review_optimizer_result(
        self,
        prompt: str,
        artifact: OptimizerArtifact | None,
        *,
        runtime: SessionRuntime,
        runs: SessionRuns,
    ) -> None:
        """Queue a fresh review after prior runs finish, using the latest snapshot."""
        run = runs.start(
            self.id,
            lambda run: self.run(run, prompt, runtime=runtime, background=True, artifact=artifact),
            background=True,
        )
        try:
            await run.wait()
        finally:
            run.cancel()

    def publish_optimizer_update(self, update: dict[str, object]) -> None:
        """Project independent job updates onto the same stream as agent output."""
        self.publish("optimization_progress" if "progress" in update else "optimization", update)

    @property
    def active(self) -> bool:
        return self.snapshot is not None

    def begin_run(self, *, accepting_steering: bool, run_id: str | None = None) -> RunSnapshot:
        """Reserve this conversation version and open its steering queue."""
        if self.active:
            raise HTTPException(status_code=409, detail="This chat session already has an active response.")
        self.agent.reset()
        self.agent.open_steering(accepting_steering)
        self.snapshot = RunSnapshot(
            list(self.transcript),
            self.schedule_yaml,
            self.version,
            self.proposal_yaml,
            self.proposal_diff,
            previously_dropped=self.dropped_history_messages,
            run_id=run_id,
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
            self.proposal_yaml, self.proposal_diff = proposal
            self.proposal_run_id = snapshot.run_id
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
        """Replace the session schedule and invalidate proposals and in-flight results."""
        if self.schedule_yaml == schedule_yaml:
            return
        self.version += 1
        self.schedule_yaml = schedule_yaml
        self.revision = schedule_revision(schedule_yaml)
        self._clear_proposal()

    def _clear_proposal(self) -> str | None:
        """Drop the pending proposal and return the run that produced it."""
        run_id = self.proposal_run_id
        self.proposal_yaml = ""
        self.proposal_diff = ""
        self.proposal_run_id = None
        return run_id

    def require_proposal(self, base_sha256: str) -> None:
        """Reject a missing or stale proposal before it can be applied."""
        if not self.proposal_yaml:
            raise HTTPException(status_code=404, detail="No proposal is waiting for approval.")
        if self.revision != base_sha256:
            self.version += 1
            self._clear_proposal()
            raise HTTPException(
                status_code=409,
                detail="The schedule changed after this proposal was created, so it was discarded.",
            )

    def adopt_proposal(self, base_sha256: str) -> tuple[str, str | None]:
        """Adopt a revalidated proposal and record the user's decision.

        Returns the approved YAML and the run that proposed it.
        """
        self.require_proposal(base_sha256)
        approved = self.proposal_yaml
        run_id = self._clear_proposal()
        self.version += 1
        self.schedule_yaml = approved
        self.revision = schedule_revision(approved)
        self.transcript.append(ProposalDecisionEntry("approved"))
        return approved, run_id

    def discard_proposal(self, decision: ProposalDecision = "rejected") -> str | None:
        """Record a proposal decision once and invalidate results based on it.

        Returns the run that proposed the discarded proposal, if one was pending.
        """
        had_proposal = bool(self.proposal_yaml)
        run_id = self._clear_proposal()
        if not had_proposal:
            return None
        self.version += 1
        self.transcript.append(ProposalDecisionEntry(decision))
        return run_id

    def _prepare_run(
        self,
        snapshot: RunSnapshot,
        question: str,
        attachments: Sequence[SandboxAttachment],
        artifact: OptimizerArtifact | None,
        settings: AiSettings,
        events: _RunEvents,
    ) -> tuple[list[ChatMessage], int]:
        """Project the reserved transcript and report its context usage."""
        retained_history = recent_history(snapshot.transcript, settings.max_history_chars)
        events.emit(
            "context_usage",
            {
                "used_chars": history_context_chars(snapshot.transcript, settings.max_history_chars),
                "max_chars": settings.max_history_chars,
            },
        )
        dropped_history = (
            snapshot.previously_dropped + len(projected_history(snapshot.transcript)) - len(retained_history)
        )
        if dropped_history:
            events.emit("history_trimmed", {"dropped": dropped_history})
        messages = build_provider_messages(
            snapshot.transcript,
            snapshot.schedule_yaml,
            question,
            attachments,
            pending_proposal=bool(snapshot.proposal_yaml),
            optimizer_result_available=artifact is not None,
            max_history_chars=settings.max_history_chars,
        )
        return messages, dropped_history

    async def _execute_run(
        self,
        snapshot: RunSnapshot,
        messages: Sequence[ChatMessage],
        attachments: Sequence[SandboxAttachment],
        artifact: OptimizerArtifact | None,
        runtime: SessionRuntime,
        background: bool,
        output: RunOutput,
        events: _RunEvents,
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
                pending_proposal_yaml=snapshot.proposal_yaml,
                pending_proposal_diff=snapshot.proposal_diff,
                execute_optimizer=lambda current_yaml, arguments: runtime.session_optimizer.execute(
                    self.id, current_yaml, arguments
                ),
                attachments=attachments,
                optimizer_result=artifact.content if artifact is not None else None,
                agent=self.agent,
            )
            async with aclosing(agent_events):
                async for event in agent_events:
                    wire_event = output.consume(event)
                    if wire_event is not None:
                        events.emit(*wire_event)

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
        completion: RunCompletion,
        output: RunOutput,
        events: _RunEvents,
        settings: AiSettings,
        dropped_history: int,
        history_saved: bool | None,
        background: bool,
    ) -> None:
        """Publish the committed result after its history write finishes."""
        if not completion.run_saved:
            events.emit("stale", {"message": STALE_RUN_ERROR})
            return
        if completion.history_trimmed_count and completion.history_trimmed_count != dropped_history:
            events.emit("history_trimmed", {"dropped": completion.history_trimmed_count})
        if completion.proposal_saved and output.proposal is not None:
            events.emit("proposal", {"diff": output.proposal.diff})
        done: dict[str, object] = {}
        if history_saved is not None and not background:
            done["history_saved"] = history_saved
        events.emit(
            "context_usage",
            {"used_chars": completion.context_used_chars, "max_chars": settings.max_history_chars},
        )
        events.emit("done", done)

    async def run(
        self,
        run: AgentRun,
        question: str,
        *,
        runtime: SessionRuntime,
        background: bool = False,
        owner: str | None = None,
        credential_id: str | None = None,
        attachments: Sequence[SandboxAttachment] = (),
        artifact: OptimizerArtifact | None = None,
    ) -> None:
        """Own every run phase and finalize once, regardless of trigger or transport."""
        session_id = self.id
        settings, store = runtime.settings, runtime.store
        history_log = runtime.history_log
        snapshot = (
            store.begin_background(session_id, run_id=run.id)
            if background
            else store.begin(session_id, owner, run_id=run.id)
        )
        if snapshot is None:
            return
        history_question = question
        if attachments:
            filenames = json.dumps([attachment.filename for attachment in attachments], ensure_ascii=False)
            history_question += f"\n[Files were attached: {filenames}.]"
        output = RunOutput()
        run_entries: list[AgentMessage] = [UserMessage(history_question)]
        completed = False
        logged = False
        outcome = "cancelled"
        error_code = None
        events = _RunEvents(run.id, self.publish)

        try:
            if history_log is not None:
                logged = True
                logged = await _write_history(
                    history_log,
                    "start_run",
                    run.id,
                    session_id,
                    credential_id,
                    history_question,
                    settings.provider_model,
                    len(attachments),
                )
                if not logged:
                    raise HTTPException(status_code=503, detail="AI chat history is temporarily unavailable.")
            events.emit("run_start", {"trigger": "optimizer" if background else "user"})
            run.ready.set_result(True)
            if not background:
                artifact = await runtime.session_optimizer.latest_result_artifact(session_id)
            messages, dropped_history = self._prepare_run(snapshot, question, attachments, artifact, settings, events)
            await self._execute_run(snapshot, messages, attachments, artifact, runtime, background, output, events)
            run_entries = [run_entries[0], *self.agent.state.messages]
            completion = self._commit_run(run, snapshot, run_entries, output, store)
            completed = True
            outcome = "completed" if completion.run_saved else "stale"
            history_saved = None
            if logged:
                # The history result is part of foreground done. Do not write it again in finally.
                logged = False
                # The prompt entry, including attachment filenames, was written at run start.
                history_saved = await _write_history(
                    history_log, "finish_run", run.id, outcome, None, output.usage, run_entries[1:]
                )
            self._publish_completion(completion, output, events, settings, dropped_history, history_saved, background)
        except asyncio.CancelledError:
            if not completed:
                # Keep the prompt so a follow-up can refer to it. Workspace changes and any
                # proposal were discarded with the sandbox, which context.py accounts for.
                run_entries = output.interrupted_entries([run_entries[0], *self.agent.state.messages], "aborted")
                store.finish(session_id, retained_entries(run_entries), snapshot=snapshot)
                completed = True
            events.emit("stopped", {})
            raise
        except HTTPException:
            if not background:
                raise
            outcome, error_code = "failed", "history_unavailable"
            events.emit(
                "error", {"message": "AI chat history is unavailable, so the optimizer result was not reviewed."}
            )
        except (ProviderError, SandboxRunTimeoutError, SandboxCandidateError, SandboxError) as exc:
            outcome = "failed"
            if isinstance(exc, ProviderError):
                error_code, message = "provider_error", PROVIDER_ERROR
            elif isinstance(exc, SandboxRunTimeoutError):
                error_code, message = "sandbox_timeout", SANDBOX_RUN_TIMEOUT_ERROR
            elif isinstance(exc, SandboxCandidateError):
                error_code, message = "candidate_validation", CANDIDATE_VALIDATION_ERROR
            else:
                error_code, message = "sandbox_error", "The temporary AI sandbox failed. Please try again."
                logger.exception("AI sandbox run failed session_id=%s", session_id)
            events.emit("error", {"message": message})
        except Exception:
            outcome, error_code = "failed", "internal_error"
            logger.exception("Unexpected AI run failure session_id=%s", session_id)
            events.emit("error", {"message": "The AI response failed unexpectedly."})
        finally:
            run.finishing = True
            if not completed:
                stop_reason = "aborted" if outcome == "cancelled" else "error"
                run_entries = output.interrupted_entries([run_entries[0], *self.agent.state.messages], stop_reason)
                store.abort(session_id, snapshot)
            if logged:
                await _write_history(
                    history_log,
                    "finish_run",
                    run.id,
                    outcome,
                    error_code,
                    output.usage,
                    run_entries[1:],
                )
            events.finish()

"""Replayable events and agent turns triggered by background work."""

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

# This code is mostly AI generated.

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import aclosing
from dataclasses import dataclass
from typing import Protocol

from fastapi import HTTPException

from .agent import AgentProposal, AgentReasoning, AgentSteering, AgentText, AgentToolStart, AgentToolUse
from .config import DEFAULT_MAX_HISTORY_CHARS, AiSettings
from .history import ChatHistory
from .lifecycle import Turn, TurnSnapshot
from .optimizer import WORKSPACE_OPTIMIZER_RESULT, OptimizerArtifact, SessionOptimizer
from .provider import ChatMessage, ProviderError, TokenUsage, ToolCapableChatProvider
from .sandbox import SandboxError, SandboxFactory
from .sandbox_agent import (
    SANDBOX_SYSTEM_PROMPT,
    AgentScheduleChange,
    SandboxAgentLimits,
    SandboxAttachment,
    SandboxCandidateError,
    SandboxTurnTimeoutError,
    run_sandbox_agent,
)
from .schedule_context import describe_schedule

CANDIDATE_VALIDATION_ERROR = (
    "The candidate schedule failed trusted validation. All schedule changes made during this agent turn were "
    "discarded. The canonical schedule was not changed."
)
PROVIDER_ERROR = "The AI provider failed. Please try again."
SANDBOX_TURN_TIMEOUT_ERROR = "The AI response timed out. Please try again."
STALE_TURN_ERROR = "The schedule changed while this response was generated, so the response was discarded."
logger = logging.getLogger("nurse_scheduling.ai")


class TurnCompletion(Protocol):
    """Result fields used by background turn finalization."""

    turn_saved: bool
    proposal_saved: bool


class BackgroundSessionStore(Protocol):
    """Session operations needed by a trusted background turn."""

    def begin(self, session_id: str, owner_token: str | None) -> TurnSnapshot: ...

    def take_steering(self, session_id: str, close_if_empty: bool) -> list[tuple[str, str]]: ...

    def begin_background(self, session_id: str) -> TurnSnapshot | None: ...

    def finish(
        self,
        session_id: str,
        user_message: str,
        assistant_message: str,
        proposal: tuple[str, str] | None = None,
        *,
        snapshot: TurnSnapshot,
        turn_messages: Sequence[ChatMessage] = (),
    ) -> TurnCompletion: ...

    def abort(self, session_id: str, snapshot: TurnSnapshot) -> None: ...


@dataclass(frozen=True)
class SessionEvent:
    """One replayable event from an assistant turn initiated by background work."""

    id: int
    type: str
    data: dict[str, object]


class SessionEventBroker:
    """Process-local replay for background turns and independent optimizer progress."""

    def __init__(
        self,
        max_events_per_session: int = 1000,
        max_sessions: int = 1000,
        max_progress_events_per_session: int = 100,
    ) -> None:
        self._max_events_per_session = max_events_per_session
        self._max_progress_events_per_session = max_progress_events_per_session
        self._max_sessions = max_sessions
        self._events: dict[str, list[SessionEvent]] = {}
        self._progress_events: dict[str, list[SessionEvent]] = {}
        self._last_ids: dict[str, int] = {}
        self._signals: dict[str, asyncio.Event] = {}

    def publish(self, session_id: str, event_type: str, data: dict[str, object]) -> None:
        if session_id not in self._events and len(self._events) >= self._max_sessions:
            oldest_session_id = next(iter(self._events))
            self.forget_session(oldest_session_id)
        self._events.setdefault(session_id, [])
        events = (
            self._progress_events.setdefault(session_id, [])
            if event_type == "optimization_progress"
            else self._events[session_id]
        )
        event_id = self._last_ids.get(session_id, 0) + 1
        self._last_ids[session_id] = event_id
        events.append(SessionEvent(event_id, event_type, data))
        limit = (
            self._max_progress_events_per_session
            if event_type == "optimization_progress"
            else self._max_events_per_session
        )
        del events[:-limit]
        self._signals.setdefault(session_id, asyncio.Event()).set()

    def forget_session(self, session_id: str) -> None:
        self._events.pop(session_id, None)
        self._progress_events.pop(session_id, None)
        self._last_ids.pop(session_id, None)
        # Wake an open stream so it observes the dropped signal and ends, instead of
        # recreating the entry this pop removes and waiting on a retired session.
        signal = self._signals.pop(session_id, None)
        if signal is not None:
            signal.set()

    def events_after(self, session_id: str, after_id: int = 0) -> tuple[SessionEvent, ...]:
        """Return retained events after a cursor for replay and diagnostics."""
        retained = (*self._events.get(session_id, ()), *self._progress_events.get(session_id, ()))
        return tuple(sorted((event for event in retained if event.id > after_id), key=lambda event: event.id))

    async def stream(self, session_id: str, after_id: int) -> AsyncIterator[SessionEvent | None]:
        signal = self._signals.setdefault(session_id, asyncio.Event())
        while True:
            pending = self.events_after(session_id, after_id)
            if pending:
                for event in pending:
                    after_id = event.id
                    yield event
                continue
            if self._signals.get(session_id) is not signal:
                return
            signal.clear()
            try:
                await asyncio.wait_for(signal.wait(), timeout=15)
            except TimeoutError:
                yield None


def recent_history(history: list[ChatMessage], max_chars: int) -> list[ChatMessage]:
    """Keep the newest retained messages that fit the prompt budget, oldest first.

    Retention bounds how much of a conversation the session holds, not how much a
    provider can accept. A long session would otherwise grow every later prompt past
    the model context window and fail the request outright.
    """
    kept: list[ChatMessage] = []
    remaining = max_chars
    for message in reversed(history):
        remaining -= len(json.dumps(message, ensure_ascii=False))
        if remaining < 0:
            break
        kept.append(message)
    kept.reverse()
    return kept


def build_provider_messages(
    history: list[ChatMessage],
    schedule_yaml: str,
    question: str,
    attachments: Sequence[SandboxAttachment] = (),
    *,
    system_prompt: str = SANDBOX_SYSTEM_PROMPT,
    pending_proposal: bool = False,
    optimizer_result_available: bool = False,
    max_history_chars: int = DEFAULT_MAX_HISTORY_CHARS,
) -> list[ChatMessage]:
    """Build a provider prompt that keeps schedule data separate from instructions."""
    system_content = f"{system_prompt}\n\nCurrent schedule summary:\n{describe_schedule(schedule_yaml)}"
    if pending_proposal:
        system_content += (
            "\nA validated proposal is pending. Its exact candidate and diff are available in the trusted workspace "
            "files described above."
        )
    if attachments:
        system_content += f"\nAttached files: {len(attachments)}. Manifest: /workspace/attachments/manifest.json."
    if optimizer_result_available:
        system_content += f"\nOptimization result: {WORKSPACE_OPTIMIZER_RESULT}."
    return [
        ChatMessage(role="system", content=system_content),
        *recent_history(history, max_history_chars),
        ChatMessage(role="user", content=question),
    ]


async def run_turn(
    turn: Turn,
    session_id: str,
    question: str,
    *,
    settings: AiSettings,
    store: BackgroundSessionStore,
    emit: Callable[[str, dict[str, object]], Awaitable[None]],
    concurrency_limit: asyncio.Semaphore,
    history_log: ChatHistory | None,
    provider: ToolCapableChatProvider,
    sandbox_factory: SandboxFactory,
    session_optimizer: SessionOptimizer,
    background: bool = False,
    owner: str | None = None,
    credential_id: str | None = None,
    attachments: Sequence[SandboxAttachment] = (),
    artifact: OptimizerArtifact | None = None,
) -> None:
    """Own every turn phase and finalize once, regardless of trigger or transport."""
    snapshot = store.begin_background(session_id) if background else store.begin(session_id, owner)
    if snapshot is None:
        return
    history, schedule_yaml = snapshot.history, snapshot.schedule_yaml
    proposal_yaml, proposal_diff = snapshot.proposal_yaml, snapshot.proposal_diff
    history_question = question
    if attachments:
        filenames = json.dumps([attachment.filename for attachment in attachments], ensure_ascii=False)
        history_question += f"\n[Files were attached: {filenames}.]"
    assistant_parts: list[str] = []
    assistant_segment: list[str] = []
    turn_messages = [ChatMessage(role="user", content=history_question)]
    pending_proposal: AgentProposal | None = None
    completed = False
    logged = False
    outcome = "cancelled"
    error_code = None
    usage = None

    async def write_history(operation: str, *args) -> bool:
        # asyncio cancellation and ASGI cancel scopes both wait for the audit write.
        task = asyncio.create_task(history_log.write(operation, *args))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise

    try:
        if background:
            await emit("turn_start", {"message_id": turn.id, "trigger": "optimizer"})
        if history_log is not None:
            logged = True
            logged = await write_history(
                "start_turn", turn.id, session_id, credential_id, question, settings.provider_model, len(attachments)
            )
            if not logged:
                raise HTTPException(status_code=503, detail="AI chat history is temporarily unavailable.")
        turn.ready.set_result(True)
        if not background:
            artifact = await session_optimizer.latest_result_artifact(session_id)
            await turn.streaming.wait()
        retained_history = recent_history(history, settings.max_history_chars)
        if len(retained_history) < len(history):
            await emit("history_trimmed", {"dropped": len(history) - len(retained_history)})
        messages = build_provider_messages(
            retained_history,
            schedule_yaml,
            question,
            attachments,
            pending_proposal=bool(proposal_yaml),
            optimizer_result_available=artifact is not None,
            max_history_chars=settings.max_history_chars,
        )
        async with concurrency_limit:
            agent_events = run_sandbox_agent(
                provider,
                sandbox_factory,
                schedule_yaml,
                messages,
                SandboxAgentLimits.from_settings(settings),
                take_steering=None if background else lambda close: store.take_steering(session_id, close),
                pending_proposal_yaml=proposal_yaml,
                pending_proposal_diff=proposal_diff,
                execute_optimizer=lambda current_yaml, arguments: session_optimizer.execute(
                    session_id, current_yaml, arguments
                ),
                attachments=attachments,
                optimizer_result=artifact.content if artifact is not None else None,
            )
            async with aclosing(agent_events):
                async for event in agent_events:
                    if isinstance(event, AgentText):
                        assistant_parts.append(event.text)
                        assistant_segment.append(event.text)
                        await emit("delta", {"text": event.text})
                    elif isinstance(event, AgentReasoning):
                        await emit("reasoning", {"text": event.text})
                    elif isinstance(event, TokenUsage):
                        usage = event if usage is None else usage + event
                    elif isinstance(event, AgentToolStart):
                        await emit("tool_start", {"name": event.name, "arguments": event.arguments})
                    elif isinstance(event, AgentToolUse):
                        await emit(
                            "tool",
                            {
                                "name": event.name,
                                "arguments": event.arguments,
                                "result": event.result,
                                "ok": event.ok,
                            },
                        )
                    elif isinstance(event, AgentSteering):
                        if assistant_segment:
                            turn_messages.append(ChatMessage(role="assistant", content="".join(assistant_segment)))
                        turn_messages.append(ChatMessage(role="user", content=event.text))
                        assistant_segment.clear()
                        await emit("steering", {"message_id": event.message_id, "message": event.text})
                    elif isinstance(event, AgentScheduleChange):
                        await emit("schedule_change", {"schedule_yaml": event.schedule_yaml})
                    elif isinstance(event, AgentProposal):
                        pending_proposal = event
        turn_messages.append(ChatMessage(role="assistant", content="".join(assistant_segment)))
        completion = store.finish(
            session_id,
            history_question,
            "".join(assistant_parts),
            (pending_proposal.text, pending_proposal.diff) if pending_proposal is not None else None,
            snapshot=snapshot,
            turn_messages=turn_messages,
        )
        completed = True
        outcome = "completed" if completion.turn_saved else "stale"
        history_saved = None
        if logged:
            # The audit result is part of foreground done. Do not write it again in finally.
            logged = False
            history_saved = await write_history("finish_turn", turn.id, "".join(assistant_parts), outcome, None, usage)
        if not completion.turn_saved:
            await emit("stale", {"message": STALE_TURN_ERROR})
            return
        if completion.proposal_saved and pending_proposal is not None:
            await emit("proposal", {"diff": pending_proposal.diff})
        done = {"message_id": turn.id}
        if history_saved is not None and not background:
            done["history_saved"] = history_saved
        await emit("done", done)
    except asyncio.CancelledError:
        if background:
            await emit("stopped", {"message_id": turn.id})
        raise
    except HTTPException:
        if not background:
            raise
        outcome, error_code = "failed", "history_unavailable"
        await emit("error", {"message": "AI chat history is unavailable, so the optimizer result was not reviewed."})
    except (ProviderError, SandboxTurnTimeoutError, SandboxCandidateError, SandboxError) as exc:
        outcome = "failed"
        if isinstance(exc, ProviderError):
            error_code, message = "provider_error", PROVIDER_ERROR
        elif isinstance(exc, SandboxTurnTimeoutError):
            error_code, message = "sandbox_timeout", SANDBOX_TURN_TIMEOUT_ERROR
        elif isinstance(exc, SandboxCandidateError):
            error_code, message = "candidate_validation", CANDIDATE_VALIDATION_ERROR
        else:
            error_code, message = "sandbox_error", "The temporary AI sandbox failed. Please try again."
            logger.exception("AI sandbox turn failed session_id=%s", session_id)
        await emit("error", {"message": message})
    except Exception:
        outcome, error_code = "failed", "internal_error"
        logger.exception("Unexpected AI turn failure session_id=%s", session_id)
        await emit("error", {"message": "The AI response failed unexpectedly."})
    finally:
        turn.finishing = True
        if not completed:
            store.abort(session_id, snapshot)
        if logged:
            await write_history("finish_turn", turn.id, "".join(assistant_parts), outcome, error_code, usage)

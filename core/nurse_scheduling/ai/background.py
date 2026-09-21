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
import logging
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from .agent import AgentProposal, AgentReasoning, AgentText, AgentToolStart, AgentToolUse
from .config import AiSettings
from .history import ChatHistory
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

    def begin_background(self, session_id: str) -> tuple[list[ChatMessage], str, str, str, str] | None: ...

    def finish(
        self,
        session_id: str,
        user_message: str,
        assistant_message: str,
        proposal: tuple[str, str] | None = None,
        *,
        base_revision: str,
        turn_messages: Sequence[ChatMessage] = (),
    ) -> TurnCompletion: ...

    def abort(self, session_id: str) -> None: ...


@dataclass(frozen=True)
class SessionEvent:
    """One replayable event from an assistant turn initiated by background work."""

    id: int
    type: str
    data: dict[str, object]


class SessionEventBroker:
    """Process-local replay and notification for background assistant turns."""

    def __init__(self, max_events_per_session: int = 200, max_sessions: int = 1000) -> None:
        self._max_events_per_session = max_events_per_session
        self._max_sessions = max_sessions
        self._events: dict[str, list[SessionEvent]] = {}
        self._signals: dict[str, asyncio.Event] = {}

    def publish(self, session_id: str, event_type: str, data: dict[str, object]) -> None:
        if session_id not in self._events and len(self._events) >= self._max_sessions:
            oldest_session_id = next(iter(self._events))
            self._events.pop(oldest_session_id, None)
            self._signals.pop(oldest_session_id, None)
        events = self._events.setdefault(session_id, [])
        event_id = events[-1].id + 1 if events else 1
        events.append(SessionEvent(event_id, event_type, data))
        del events[: -self._max_events_per_session]
        self._signals.setdefault(session_id, asyncio.Event()).set()

    def events_after(self, session_id: str, after_id: int = 0) -> tuple[SessionEvent, ...]:
        """Return retained events after a cursor for replay and diagnostics."""
        return tuple(event for event in self._events.get(session_id, ()) if event.id > after_id)

    async def stream(self, session_id: str, after_id: int) -> AsyncIterator[SessionEvent | None]:
        while True:
            pending = self.events_after(session_id, after_id)
            if pending:
                for event in pending:
                    after_id = event.id
                    yield event
                continue
            signal = self._signals.setdefault(session_id, asyncio.Event())
            signal.clear()
            try:
                await asyncio.wait_for(signal.wait(), timeout=15)
            except TimeoutError:
                yield None


def build_provider_messages(
    history: list[ChatMessage],
    schedule_yaml: str,
    question: str,
    attachments: Sequence[SandboxAttachment] = (),
    *,
    system_prompt: str = SANDBOX_SYSTEM_PROMPT,
    pending_proposal: bool = False,
    optimizer_result_available: bool = False,
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
        *history,
        ChatMessage(role="user", content=question),
    ]


async def run_background_turn(
    session_id: str,
    question: str,
    artifact: OptimizerArtifact | None,
    *,
    settings: AiSettings,
    store: BackgroundSessionStore,
    event_broker: SessionEventBroker,
    turn_locks: dict[str, asyncio.Lock],
    track_active_turn: Callable[[str], AbstractAsyncContextManager[None]],
    concurrency_limit: asyncio.Semaphore,
    history_log: ChatHistory | None,
    provider: ToolCapableChatProvider,
    sandbox_factory: SandboxFactory,
    session_optimizer: SessionOptimizer,
) -> None:
    """Wake an idle agent after a background optimizer job reaches a terminal state."""
    turn_lock = turn_locks.setdefault(session_id, asyncio.Lock())
    async with turn_lock, track_active_turn(session_id):
        snapshot = store.begin_background(session_id)
        if snapshot is None:
            return
        history, schedule_yaml, base_revision, proposal_yaml, proposal_diff = snapshot
        turn_id = str(uuid4())
        event_broker.publish(session_id, "turn_start", {"message_id": turn_id, "trigger": "optimizer"})
        if history_log is not None:
            try:
                logged = await history_log.write(
                    "start_turn",
                    turn_id,
                    session_id,
                    None,
                    question,
                    settings.provider_model,
                    0,
                )
            except Exception:
                logger.exception("Background AI history start failed session_id=%s", session_id)
                logged = False
            if not logged:
                store.abort(session_id)
                event_broker.publish(
                    session_id,
                    "error",
                    {"message": "AI chat history is unavailable, so the optimizer result was not reviewed."},
                )
                return
        messages = build_provider_messages(
            history,
            schedule_yaml,
            question,
            system_prompt=SANDBOX_SYSTEM_PROMPT,
            pending_proposal=bool(proposal_yaml),
            optimizer_result_available=artifact is not None,
        )
        assistant_parts: list[str] = []
        pending_proposal: AgentProposal | None = None
        completed = False
        outcome = "failed"
        error_code: str | None = "internal_error"
        usage: TokenUsage | None = None
        try:
            async with concurrency_limit:
                agent_events = run_sandbox_agent(
                    provider,
                    sandbox_factory,
                    schedule_yaml,
                    messages,
                    SandboxAgentLimits.from_settings(settings),
                    pending_proposal_yaml=proposal_yaml,
                    pending_proposal_diff=proposal_diff,
                    execute_optimizer=(
                        lambda current_yaml, arguments: session_optimizer.execute(session_id, current_yaml, arguments)
                    ),
                    optimizer_result=artifact.content if artifact is not None else None,
                )
                async for event in agent_events:
                    if isinstance(event, AgentText):
                        assistant_parts.append(event.text)
                        event_broker.publish(session_id, "delta", {"text": event.text})
                    elif isinstance(event, AgentReasoning):
                        event_broker.publish(session_id, "reasoning", {"text": event.text})
                    elif isinstance(event, TokenUsage):
                        usage = event if usage is None else usage + event
                    elif isinstance(event, AgentToolStart):
                        event_broker.publish(
                            session_id,
                            "tool_start",
                            {"name": event.name, "arguments": event.arguments},
                        )
                    elif isinstance(event, AgentToolUse):
                        event_broker.publish(
                            session_id,
                            "tool",
                            {
                                "name": event.name,
                                "arguments": event.arguments,
                                "result": event.result,
                                "ok": event.ok,
                            },
                        )
                    elif isinstance(event, AgentScheduleChange):
                        event_broker.publish(
                            session_id,
                            "schedule_change",
                            {"schedule_yaml": event.schedule_yaml},
                        )
                    elif isinstance(event, AgentProposal):
                        pending_proposal = event
            proposal = None
            if pending_proposal is not None:
                proposal = (pending_proposal.text, pending_proposal.diff)
            completion = store.finish(
                session_id,
                question,
                "".join(assistant_parts),
                proposal,
                base_revision=base_revision,
            )
            completed = True
            if not completion.turn_saved:
                outcome, error_code = "stale", None
                event_broker.publish(session_id, "stale", {"message": STALE_TURN_ERROR})
                return
            outcome, error_code = "completed", None
            if completion.proposal_saved and pending_proposal is not None:
                event_broker.publish(session_id, "proposal", {"diff": pending_proposal.diff})
            event_broker.publish(session_id, "done", {"message_id": turn_id})
        except asyncio.CancelledError:
            outcome, error_code = "cancelled", None
            event_broker.publish(session_id, "stopped", {"message_id": turn_id})
            raise
        except ProviderError:
            error_code = "provider_error"
            event_broker.publish(session_id, "error", {"message": PROVIDER_ERROR})
        except SandboxTurnTimeoutError:
            error_code = "sandbox_timeout"
            event_broker.publish(session_id, "error", {"message": SANDBOX_TURN_TIMEOUT_ERROR})
        except SandboxCandidateError:
            error_code = "candidate_validation"
            event_broker.publish(session_id, "error", {"message": CANDIDATE_VALIDATION_ERROR})
        except SandboxError:
            error_code = "sandbox_error"
            logger.exception("Background AI sandbox turn failed session_id=%s", session_id)
            event_broker.publish(
                session_id,
                "error",
                {"message": "The temporary AI sandbox failed while reviewing optimizer results."},
            )
        except Exception:
            logger.exception("Unexpected background AI turn failure session_id=%s", session_id)
            event_broker.publish(
                session_id,
                "error",
                {"message": "The AI could not review the optimizer result."},
            )
        finally:
            if not completed:
                store.abort(session_id)
            if history_log is not None:
                await history_log.write(
                    "finish_turn",
                    turn_id,
                    "".join(assistant_parts),
                    outcome,
                    error_code,
                    usage,
                )
